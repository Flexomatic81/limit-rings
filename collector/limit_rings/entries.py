"""The provider entries of stats.json, built from the state."""

from collections.abc import Collection
from datetime import date, datetime, tzinfo
from pathlib import Path

from . import aggregate, breakdown, forecast
from .limits import public_limit
from .models import JsonDict
from .sources import backoff, claude_limits


def iso(epoch: float | None, tz: tzinfo) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz).isoformat(timespec="seconds")


def next_request(section: JsonDict, interval: float, now_ts: float) -> float | None:
    """When the usage endpoint will be asked next: after the regular interval and any running pause."""
    last = section["oauth_last_attempt"]
    if last is None:
        return None
    candidates: list[float] = [last + interval, backoff.blocked_until(section["oauth_pause"], now_ts) or 0]
    return max(candidates)


def provider_entry(
    section: JsonDict,
    today: date,
    tz: tzinfo,
    now_ts: float,
    limits_source: str | None,
    plan: str | None,
    errors: list[JsonDict],
    interval: float,
) -> JsonDict:
    rec = section["limits"]
    return {
        "limits": rec["limits"] if rec else [],
        "limits_source": limits_source if rec else None,
        "limits_updated_at": iso(rec["updated_at"], tz) if rec else None,
        "limits_paused_until": iso(backoff.blocked_until(section["oauth_pause"], now_ts), tz),
        "limits_next_request_at": iso(next_request(section, interval, now_ts), tz),
        "extra": rec.get("extra") if rec else None,
        "plan": plan,
        "tokens": aggregate.summarize(section["buckets"], today),
        **series(section["buckets"], today),
        "errors": errors,
    }


def series(buckets: JsonDict, today: date) -> JsonDict:
    """The chart's three ranges: 30 days, 13 weeks and 12 months."""
    return {
        "daily": aggregate.daily_series(buckets, today),
        "weekly": aggregate.weekly_series(buckets, today),
        "monthly": aggregate.monthly_series(buckets, today),
    }


def auth_entry(credentials: Path, now_ts: float, tz: tzinfo) -> JsonDict:
    status, expires_at = claude_limits.credential_status(credentials, now_ts)
    return {"status": status, "expires_at": iso(expires_at, tz)}


def limits_source(key: str, rec: JsonDict | None) -> str | None:
    if rec is None:
        return None
    source: str | None = rec["source"] if key == "claude" else rec.get("source", "session_log")
    return source


def with_forecasts(limits: list[JsonDict], name: str, history: JsonDict, now_ts: float) -> list[JsonDict]:
    out = []
    for limit in map(public_limit, limits):
        entry = history.get(f"{name.lower()}:{limit['id']}")
        result = (
            forecast.forecast(entry, limit.get("resets_at"), now_ts, limit.get("window_minutes")) if entry else None
        )
        out.append({**limit, "forecast": result} if result else limit)
    return out


def _is_weekly(limit: JsonDict) -> bool:
    """The weekly limit of all models (Claude's seven_day, Codex's 7-day window), not a model-scoped one."""
    return limit.get("id") == "seven_day" or (limit.get("window_minutes") == 10080 and not limit.get("model"))


def breakdown_entry(section: JsonDict, now_ts: float, tz: tzinfo) -> JsonDict:
    """Breakdown since the start of the provider's weekly window (reset − 7 days), otherwise of the last 7 days."""
    rec = section["limits"]
    resets = next((lim.get("resets_at") for lim in (rec["limits"] if rec else []) if _is_weekly(lim)), None)
    if resets is not None and resets - 7 * 86400 <= now_ts:
        since, basis = resets - 7 * 86400, "window"
    else:
        since, basis = now_ts - 7 * 86400, "7d"
    return {"since": iso(since, tz), "basis": basis, **breakdown.summarize(section["hourly"], since)}


def strip_login_data(provider: str, entry: JsonDict) -> None:
    """Remove what came from the usage endpoint or the login file from a provider entry (not the changes)."""
    if entry.get("limits_source") == "oauth":
        entry.update(limits=[], limits_source=None, limits_updated_at=None, extra=None)
        entry["plan"] = None
    if provider == "claude":
        entry["plan"] = None  # the Claude plan name always comes from the login file
    if "auth" in entry:
        entry["auth"] = None
    entry["limits_next_request_at"] = entry["limits_paused_until"] = None  # no request will follow
    entry["login"] = False


def withhold_login_data(stats: JsonDict | None, login: Collection[str]) -> JsonDict | None:
    """A stats.json written by another pass, for a widget that has the login off for some providers.

    Their entries lose what came from the usage endpoint (limits, extra, plan), the login state and the changes;
    tokens, history and session-log limits stay."""
    if not isinstance(stats, dict):
        return stats
    providers, accounts = stats.get("providers"), stats.get("accounts")
    entries = list(providers.items()) if isinstance(providers, dict) else []
    if isinstance(accounts, dict):
        entries += [(e.get("provider"), e) for e in accounts.values() if isinstance(e, dict)]
    for provider, entry in entries:
        if provider in login or not isinstance(entry, dict):
            continue
        strip_login_data(provider, entry)
        entry["changes"] = []
    return stats


def empty_entry(provider: str | None, today: date, errors: list[JsonDict], login: bool = True) -> JsonDict:
    """Card data for an account without results (invalid entry, failed pass)."""
    entry = {
        "limits": [],
        "limits_source": None,
        "limits_updated_at": None,
        "limits_paused_until": None,
        "limits_next_request_at": None,
        "extra": None,
        "plan": None,
        "changes": [],
        "tokens": aggregate.summarize({}, today),
        **series({}, today),
        "errors": errors,
        "login": login,
    }
    entry["breakdown"] = None
    if provider == "claude":
        entry["auth"] = None
    return entry
