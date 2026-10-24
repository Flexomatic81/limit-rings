"""Reading each provider's logs and limits into the state."""

import copy
import logging
from collections.abc import Callable, Iterable
from datetime import tzinfo
from typing import Any

from . import aggregate, breakdown
from .models import JsonDict, TokenEvent
from .paths import Paths
from .sources import claude_limits, claude_logs, codex_limits, codex_logs

log = logging.getLogger("limit_rings")


Fetch = Callable[..., Any]  # usage endpoint request: (token, [account,] timeout=…) → the raw JSON response


def unreadable_error(count: int) -> JsonDict:
    return {"code": "logs_unreadable", "count": count}


LOGS_FAILED = {"code": "logs_failed"}


LIMITS_UNAVAILABLE = {"code": "limits_unavailable"}


def add_breakdown(
    hourly: JsonDict, events: Iterable[TokenEvent], resolver: breakdown.ProjectResolver, since: float
) -> None:
    for ev in events:
        if ev.ts.timestamp() >= since:
            breakdown.add_event(hourly, ev, resolver.name(ev.project), breakdown.model_label(ev.model))


def backfill_hourly(
    section: JsonDict, events: Iterable[TokenEvent], now_ts: float, resolver: breakdown.ProjectResolver
) -> None:
    """Once after the update: backfill the hourly counts from the logs.

    events come from reading the logs with fresh state, so that daily totals and deduplication stay untouched.
    """
    add_breakdown(section["hourly"], events, resolver, now_ts - breakdown.KEEP_SECONDS)
    section["hourly_backfill"] = False


def process_claude(
    state: JsonDict, paths: Paths, now_ts: float, tz: tzinfo, fetch: Fetch, use_login: bool = True
) -> tuple[list[JsonDict], str | None]:
    section = state["claude"]
    errors = []
    resolver = breakdown.ProjectResolver()
    snapshot = copy.deepcopy({k: section[k] for k in ("files", "seen", "buckets", "hourly", "hourly_backfill")})
    try:
        if section["hourly_backfill"]:
            backfill_hourly(section, claude_logs.read_events(paths.claude_root, {}, {}).events, now_ts, resolver)
        res = claude_logs.read_events(paths.claude_root, section["files"], section["seen"])
        add_breakdown(section["hourly"], res.events, resolver, now_ts - breakdown.KEEP_SECONDS)
        breakdown.prune_hourly(section["hourly"], now_ts)
        for ev in res.events:
            aggregate.add_event(section["buckets"], ev, tz)
        if res.unreadable:
            errors.append(unreadable_error(res.unreadable))
    except Exception:
        log.exception("Claude logs: unexpected error")
        section.update(snapshot)
        errors.append(dict(LOGS_FAILED))

    if not use_login:  # neither the login file nor the endpoint; the throttle state stays as it is
        section["limits"] = claude_limits.resolve_local(section["limits"], paths.statusline_cache)
        return errors, None
    plan = None
    try:
        rec, attempt, plan = claude_limits.resolve(
            section["limits"],
            section["oauth_last_attempt"],
            now_ts,
            paths.credentials,
            paths.statusline_cache,
            fetch=fetch,
            pause=section["oauth_pause"],
        )
        section["limits"], section["oauth_last_attempt"] = rec, attempt
    except Exception as e:
        log.error("Claude limits: unexpected error: %s", type(e).__name__)
        section["oauth_last_attempt"] = now_ts  # throttle here too, otherwise it queries on every run
        errors.append(dict(LIMITS_UNAVAILABLE))
    return errors, plan


def process_codex(
    state: JsonDict, paths: Paths, now_ts: float, tz: tzinfo, fetch: Fetch, use_login: bool = True
) -> list[JsonDict]:
    section = state["codex"]
    if not use_login:
        # Without login only the session logs count; a record from the endpoint goes, before the logs are read,
        # so that a new log line of this pass can take its place.
        if section["limits"] and section["limits"].get("source") == "oauth":
            section["limits"] = None
        return process_codex_logs(state, paths, now_ts, tz)
    errors = process_codex_logs(state, paths, now_ts, tz)
    section = state["codex"]  # process_codex_logs may have restored a snapshot
    try:
        # The Claude Code plugin writes no session logs: also query the limits directly.
        section["limits"], section["oauth_last_attempt"] = codex_limits.resolve(
            section["limits"],
            section["oauth_last_attempt"],
            now_ts,
            paths.codex_auth,
            fetch=fetch,
            pause=section["oauth_pause"],
        )
    except Exception as e:
        log.error("Codex limits: unexpected error: %s", type(e).__name__)
        section["oauth_last_attempt"] = now_ts
    return errors


def process_codex_logs(state: JsonDict, paths: Paths, now_ts: float, tz: tzinfo) -> list[JsonDict]:
    section = state["codex"]
    snapshot = copy.deepcopy(section)
    resolver = breakdown.ProjectResolver()
    try:
        if section["hourly_backfill"]:
            backfill_hourly(section, codex_logs.read_events(paths.codex_root, {}, {}).events, now_ts, resolver)
        res = codex_logs.read_events(paths.codex_root, section["files"], section["sessions"])
        add_breakdown(section["hourly"], res.events, resolver, now_ts - breakdown.KEEP_SECONDS)
        breakdown.prune_hourly(section["hourly"], now_ts)
        for ev in res.events:
            aggregate.add_event(section["buckets"], ev, tz)
        if res.limits_ts is not None:
            ts = res.limits_ts.timestamp()
            prev = section["limits"]
            if prev is None or ts > prev["updated_at"]:
                section["limits"] = {"limits": res.limits, "plan": res.plan, "updated_at": ts, "source": "session_log"}
        return [unreadable_error(res.unreadable)] if res.unreadable else []
    except Exception:
        log.exception("Codex logs: unexpected error")
        state["codex"] = snapshot
        return [dict(LOGS_FAILED)]
