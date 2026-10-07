"""One collector run: read logs, fetch limits, write stats.json."""

import copy
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import aggregate, breakdown, forecast, notify
from .fsutil import write_json_atomic
from .limits import public_limit
from .sources import backoff, claude_limits, claude_logs, codex_limits, codex_logs
from .state import load_state, prune_state, save_state

log = logging.getLogger("limit_rings")

SCHEMA = 2


@dataclass(frozen=True)
class Paths:
    claude_root: Path
    codex_root: Path
    credentials: Path
    statusline_cache: Path | None
    state_file: Path
    stats_file: Path
    codex_auth: Path | None = None

    @classmethod
    def default(cls, home: Path) -> "Paths":
        cache = home / ".cache" / "limit-rings"
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


def _next_request(section: dict, interval: float, now_ts: float) -> float | None:
    """When the usage endpoint will be asked next: after the regular interval and any running pause."""
    last = section["oauth_last_attempt"]
    if last is None:
        return None
    candidates = [last + interval, backoff.blocked_until(section["oauth_pause"], now_ts) or 0]
    return max(candidates)


def _provider(section: dict, today, tz, now_ts, limits_source, plan, errors, interval) -> dict:
    rec = section["limits"]
    return {
        "limits": rec["limits"] if rec else [],
        "limits_source": limits_source if rec else None,
        "limits_updated_at": _iso(rec["updated_at"], tz) if rec else None,
        "limits_paused_until": _iso(backoff.blocked_until(section["oauth_pause"], now_ts), tz),
        "limits_next_request_at": _iso(_next_request(section, interval, now_ts), tz),
        "extra": rec.get("extra") if rec else None,
        "plan": plan,
        "tokens": aggregate.summarize(section["buckets"], today),
        "daily": aggregate.daily_series(section["buckets"], today),
        "errors": errors,
    }


def _auth(credentials: Path, now_ts: float, tz: tzinfo) -> dict:
    status, expires_at = claude_limits.credential_status(credentials, now_ts)
    return {"status": status, "expires_at": _iso(expires_at, tz)}


def _notify(state: dict, providers: dict[str, list[dict]], now_ts: float, notifier, thresholds, reset_notice,
            labels=None) -> None:
    if notifier is None:  # notifications off: leave them due, another widget instance may show them
        return
    for notice in notify.update_notices(providers, state["notified"], now_ts, thresholds, reset_notice,
                                       labels):
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
            paths.credentials, paths.statusline_cache, fetch=fetch, pause=section["oauth_pause"])
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
            section["limits"], section["oauth_last_attempt"], now_ts, paths.codex_auth, fetch=fetch,
            pause=section["oauth_pause"])
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


PROVIDERS = frozenset({"claude", "codex"})


def _pass(paths: Paths, now: datetime, tz: tzinfo, fetch, codex_fetch, notifier, providers, thresholds,
          reset_notice, labels=None) -> dict:
    """Collect one account from its paths and state file; return its provider entries for stats.json.

    A provider missing from providers (hidden in the widget) is neither read nor queried: no logs,
    no login, no request, no notification – its card keeps the last known values.
    Saves the state, not stats.json."""
    state = load_state(paths.state_file)
    before = _fingerprint(state)
    today = now.astimezone(tz).date()

    claude_errors, claude_plan = [], None
    if "claude" in providers:
        claude_errors, claude_plan = _process_claude(state, paths, now.timestamp(), tz, fetch)
    codex_errors = _process_codex(state, paths, now.timestamp(), tz, codex_fetch) if "codex" in providers else []
    _update_history(state)
    with_forecasts = {
        key: _with_forecasts((state[key]["limits"] or {}).get("limits", []), name, state["history"], now.timestamp())
        for name, key in (("Claude", "claude"), ("Codex", "codex"))}
    shown = {name: with_forecasts[key] for name, key in (("Claude", "claude"), ("Codex", "codex"))
             if key in providers}
    _notify(state, shown, now.timestamp(), notifier, thresholds, reset_notice, labels)

    prune_state(state, today)
    if _fingerprint(state) != before:  # state.json is large: only write it if something changed
        save_state(paths.state_file, state)

    claude = state["claude"]
    codex = state["codex"]
    entries = {
        "claude": {**_provider(claude, today, tz, now.timestamp(),
                               claude["limits"]["source"] if claude["limits"] else None,
                               claude_plan, claude_errors, claude_limits.OAUTH_MIN_INTERVAL),
                   "auth": _auth(paths.credentials, now.timestamp(), tz) if "claude" in providers else None,
                   "breakdown": _breakdown(claude, now.timestamp(), tz)},
        "codex": _provider(codex, today, tz, now.timestamp(),
                           codex["limits"].get("source", "session_log") if codex["limits"] else None,
                           codex["limits"]["plan"] if codex["limits"] else None, codex_errors,
                           codex_limits.MIN_INTERVAL),
    }
    for key, limits in with_forecasts.items():
        entries[key]["limits"] = limits
    return entries


def _empty_entry(provider: str | None, today, errors: list[dict]) -> dict:
    """Card data for an account without results (invalid entry, failed pass)."""
    entry = {"limits": [], "limits_source": None, "limits_updated_at": None, "limits_paused_until": None,
             "limits_next_request_at": None, "extra": None, "plan": None,
             "tokens": aggregate.summarize({}, today), "daily": aggregate.daily_series({}, today),
             "errors": errors}
    if provider == "claude":
        entry.update(auth=None, breakdown=None)
    return entry


def _accounts(accounts, cache: Path, now: datetime, tz: tzinfo, fetch, codex_fetch, notifier, thresholds,
              reset_notice) -> dict:
    from . import accounts as accounts_mod   # accounts imports Paths from here
    out = {}
    today = now.astimezone(tz).date()
    for account in accounts:
        head = {"provider": account.provider, "name": account.name, "dir": account.dir_text}
        if account.error:
            out[account.id] = {**_empty_entry(account.provider, today, [{"code": account.error}]), **head}
            continue
        paths = accounts_mod.account_paths(account, cache)
        try:
            entry = _pass(paths, now, tz, fetch, codex_fetch, notifier, {account.provider}, thresholds,
                          reset_notice, labels={accounts_mod.PROVIDER_NAMES[account.provider]: account.label})
            entry = entry[account.provider]
        except Exception as e:
            log.error("account %s: run aborted: %s", account.id, type(e).__name__)
            try:
                os.replace(paths.state_file, paths.state_file.with_name(paths.state_file.name + ".corrupt"))
            except OSError:
                pass
            entry = _empty_entry(account.provider, today, [dict(LOGS_FAILED)])
        if account.provider == "codex":
            token, _ = codex_limits.read_auth(paths.codex_auth)
            entry["auth"] = {"status": "ok" if token else "missing", "expires_at": None}
        out[account.id] = {**entry, **head}
    accounts_mod.prune_account_states(cache, {a.state_key for a in accounts if not a.error}, now.timestamp())
    return out


def run(paths: Paths, now: datetime, tz: tzinfo, fetch=claude_limits.fetch_oauth_usage,
        notifier=None, codex_fetch=codex_limits.fetch_usage, providers=PROVIDERS,
        thresholds=notify.THRESHOLDS, reset_notice=False, accounts=()) -> dict:
    """One pass over the main account and each additional account (see _pass); writes stats.json."""
    stats = {"schema": SCHEMA, "generated_at": now.astimezone(tz).isoformat(timespec="seconds"),
             "providers": _pass(paths, now, tz, fetch, codex_fetch, notifier, providers, thresholds,
                                reset_notice),
             "accounts": _accounts(accounts, paths.state_file.parent, now, tz, fetch, codex_fetch, notifier,
                                   thresholds, reset_notice)}
    write_json_atomic(paths.stats_file, stats)
    return stats


def run_safely(paths: Paths, now: datetime, tz: tzinfo, notifier, providers=PROVIDERS,
               thresholds=notify.THRESHOLDS, reset_notice=False, accounts=()) -> dict | None:
    """One run that never raises: after an unexpected error, state.json and the additional accounts' state
    files are moved aside so the next run starts fresh (their due notices were not delivered)."""
    try:
        return run(paths, now, tz, notifier=notifier, providers=providers, thresholds=thresholds,
                   reset_notice=reset_notice, accounts=accounts)
    except Exception as e:
        log.error("run aborted: %s", type(e).__name__)
        from . import accounts as accounts_mod
        cache = paths.state_file.parent
        files = [paths.state_file] + [accounts_mod.account_paths(a, cache).state_file for a in accounts
                                      if not a.error]
        for f in files:
            try:
                os.replace(f, f.with_name(f.name + ".corrupt"))
            except OSError:
                pass
        return None
