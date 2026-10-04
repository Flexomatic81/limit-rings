"""One collector run: read logs, fetch limits, write stats.json."""

import copy
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import aggregate, breakdown, forecast, notify
from .fsutil import write_json_atomic
from .limits import public_limit
from .sources import claude_limits, claude_logs, codex_limits, codex_logs
from .state import load_state, prune_state, save_state

log = logging.getLogger("agent_stats")

SCHEMA = 2


@dataclass(frozen=True)
class Paths:
    claude_root: Path
    codex_root: Path
    credentials: Path
    statusline_cache: Path
    state_file: Path
    stats_file: Path
    codex_auth: Path | None = None

    @classmethod
    def default(cls, home: Path) -> "Paths":
        cache = home / ".cache" / "agent-stats"
        return cls(
            claude_root=home / ".claude" / "projects",
            codex_root=home / ".codex" / "sessions",
            credentials=home / ".claude" / ".credentials.json",
            statusline_cache=cache / "claude-statusline-limits.json",
            state_file=cache / "state.json",
            stats_file=cache / "stats.json",
            codex_auth=home / ".codex" / "auth.json",
        )


def local_zone() -> tzinfo:
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for key in candidates:
        if key:
            try:
                return ZoneInfo(key)
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return datetime.now().astimezone().tzinfo


def _iso(epoch: float | None, tz: tzinfo) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz).isoformat(timespec="seconds")


def _provider(section: dict, today, tz, limits_source, plan, errors) -> dict:
    rec = section["limits"]
    return {
        "limits": rec["limits"] if rec else [],
        "limits_source": limits_source if rec else None,
        "limits_updated_at": _iso(rec["updated_at"], tz) if rec else None,
        "plan": plan,
        "tokens": aggregate.summarize(section["buckets"], today),
        "daily": aggregate.daily_series(section["buckets"], today),
        "errors": errors,
    }


def _auth(credentials: Path, now_ts: float, tz: tzinfo) -> dict:
    status, expires_at = claude_limits.credential_status(credentials, now_ts)
    return {"status": status, "expires_at": _iso(expires_at, tz)}


def _notify(state: dict, providers: dict[str, list[dict]], now_ts: float, notifier) -> None:
    for notice in notify.update_notices(providers, state["notified"], now_ts):
        try:
            notifier(notice)
        except Exception as e:  # a notification must never abort the run
            log.warning("notification failed: %s", type(e).__name__)


def _update_history(state: dict) -> None:
    providers = {}
    for name, key in (("Claude", "claude"), ("Codex", "codex")):
        rec = state[key]["limits"]
        providers[name] = (rec["limits"], rec["updated_at"]) if rec else ([], None)
    forecast.update_history(state["history"], providers)


def _with_forecasts(limits: list[dict], name: str, history: dict, now_ts: float) -> list[dict]:
    out = []
    for limit in map(public_limit, limits):
        entry = history.get(f"{name.lower()}:{limit['id']}")
        result = (forecast.forecast(entry, limit.get("resets_at"), now_ts, limit.get("window_minutes"))
                  if entry else None)
        out.append({**limit, "forecast": result} if result else limit)
    return out


def _breakdown(section: dict, now_ts: float, tz: tzinfo) -> dict:
    """Breakdown since the start of the Claude weekly window (reset − 7 days), otherwise of the last 7 days."""
    rec = section["limits"]
    resets = next((l.get("resets_at") for l in (rec["limits"] if rec else []) if l.get("id") == "seven_day"), None)
    if resets is not None and resets - 7 * 86400 <= now_ts:
        since, basis = resets - 7 * 86400, "window"
    else:
        since, basis = now_ts - 7 * 86400, "7d"
    return {"since": _iso(since, tz), "basis": basis, **breakdown.summarize(section["hourly"], since)}


def _unreadable_error(count: int) -> dict:
    return {"code": "logs_unreadable", "count": count}


LOGS_FAILED = {"code": "logs_failed"}
LIMITS_UNAVAILABLE = {"code": "limits_unavailable"}


def _add_breakdown(hourly: dict, events, resolver, since: float) -> None:
    for ev in events:
        if ev.ts.timestamp() >= since:
            breakdown.add_event(hourly, ev, resolver.name(ev.project), breakdown.model_label(ev.model))


def _backfill_hourly(section: dict, paths, now_ts: float, resolver) -> None:
    """Once after the update: backfill the hourly counts from the transcripts.

    Reads with fresh state so that daily totals and deduplication stay untouched.
    """
    res = claude_logs.read_events(paths.claude_root, {}, {})
    _add_breakdown(section["hourly"], res.events, resolver, now_ts - breakdown.KEEP_SECONDS)
    section["hourly_backfill"] = False


def _process_claude(state, paths, now_ts, tz, fetch) -> tuple[list[dict], str | None]:
    section = state["claude"]
    errors = []
    resolver = breakdown.ProjectResolver()
    snapshot = copy.deepcopy({k: section[k] for k in ("files", "seen", "buckets", "hourly", "hourly_backfill")})
    try:
        if section["hourly_backfill"]:
            _backfill_hourly(section, paths, now_ts, resolver)
        res = claude_logs.read_events(paths.claude_root, section["files"], section["seen"])
        _add_breakdown(section["hourly"], res.events, resolver, now_ts - breakdown.KEEP_SECONDS)
        breakdown.prune_hourly(section["hourly"], now_ts)
        for ev in res.events:
            aggregate.add_event(section["buckets"], ev, tz)
        if res.unreadable:
            errors.append(_unreadable_error(res.unreadable))
    except Exception:
        log.exception("Claude logs: unexpected error")
        section.update(snapshot)
        errors.append(dict(LOGS_FAILED))

    plan = None
    try:
        rec, attempt, plan = claude_limits.resolve(
            section["limits"], section["oauth_last_attempt"], now_ts,
            paths.credentials, paths.statusline_cache, fetch=fetch)
        section["limits"], section["oauth_last_attempt"] = rec, attempt
    except Exception as e:
        log.error("Claude limits: unexpected error: %s", type(e).__name__)
        section["oauth_last_attempt"] = now_ts  # throttle here too, otherwise it queries on every run
        errors.append(dict(LIMITS_UNAVAILABLE))
    return errors, plan


def _process_codex(state, paths, now_ts, tz, fetch) -> list[dict]:
    errors = _process_codex_logs(state, paths, tz)
    section = state["codex"]
    try:
        # The Claude Code plugin writes no session logs: also query the limits directly.
        section["limits"], section["oauth_last_attempt"] = codex_limits.resolve(
            section["limits"], section["oauth_last_attempt"], now_ts, paths.codex_auth, fetch=fetch)
    except Exception as e:
        log.error("Codex limits: unexpected error: %s", type(e).__name__)
        section["oauth_last_attempt"] = now_ts
    return errors


def _process_codex_logs(state, paths, tz) -> list[dict]:
    section = state["codex"]
    snapshot = copy.deepcopy(section)
    try:
        res = codex_logs.read_events(paths.codex_root, section["files"], section["sessions"])
        for ev in res.events:
            aggregate.add_event(section["buckets"], ev, tz)
        if res.limits_ts is not None:
            ts = res.limits_ts.timestamp()
            prev = section["limits"]
            if prev is None or ts > prev["updated_at"]:
                section["limits"] = {"limits": res.limits, "plan": res.plan, "updated_at": ts,
                                     "source": "session_log"}
        return [_unreadable_error(res.unreadable)] if res.unreadable else []
    except Exception:
        log.exception("Codex logs: unexpected error")
        state["codex"] = snapshot
        return [dict(LOGS_FAILED)]


def _fingerprint(state: dict) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def run(paths: Paths, now: datetime, tz: tzinfo, fetch=claude_limits.fetch_oauth_usage,
        notifier=notify.send, codex_fetch=codex_limits.fetch_usage) -> dict:
    state = load_state(paths.state_file)
    before = _fingerprint(state)
    today = now.astimezone(tz).date()

    claude_errors, claude_plan = _process_claude(state, paths, now.timestamp(), tz, fetch)
    codex_errors = _process_codex(state, paths, now.timestamp(), tz, codex_fetch)
    _update_history(state)
    with_forecasts = {
        key: _with_forecasts((state[key]["limits"] or {}).get("limits", []), name, state["history"], now.timestamp())
        for name, key in (("Claude", "claude"), ("Codex", "codex"))}
    _notify(state, {"Claude": with_forecasts["claude"], "Codex": with_forecasts["codex"]},
            now.timestamp(), notifier)

    prune_state(state, today)
    if _fingerprint(state) != before:  # state.json is large: only write it if something changed
        save_state(paths.state_file, state)

    claude = state["claude"]
    codex = state["codex"]
    stats = {
        "schema": SCHEMA,
        "generated_at": now.astimezone(tz).isoformat(timespec="seconds"),
        "providers": {
            "claude": {**_provider(claude, today, tz,
                                   claude["limits"]["source"] if claude["limits"] else None,
                                   claude_plan, claude_errors),
                       "auth": _auth(paths.credentials, now.timestamp(), tz),
                       "breakdown": _breakdown(claude, now.timestamp(), tz)},
            "codex": _provider(codex, today, tz,
                               codex["limits"].get("source", "session_log") if codex["limits"] else None,
                               codex["limits"]["plan"] if codex["limits"] else None, codex_errors),
        },
    }
    for key, limits in with_forecasts.items():
        stats["providers"][key]["limits"] = limits
    write_json_atomic(paths.stats_file, stats)
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    tz = local_zone()
    paths = Paths.default(Path.home())
    try:
        run(paths, datetime.now(tz), tz)
    except Exception as e:
        log.error("run aborted: %s", type(e).__name__)
        # Unexpected state shape: move it aside so the next run starts fresh.
        try:
            os.replace(paths.state_file, paths.state_file.with_name(paths.state_file.name + ".corrupt"))
        except OSError:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
