"""Pause the usage requests after the provider answered 429/503, as long as it asks for.

Requests during a rate limit can extend it, so a limited source stays quiet until the pause is over:
as long as Retry-After says, otherwise growing with every further refusal. The pause state lives in
the collector state ({"until": epoch | None, "failures": int}) and so survives between runs.
"""

from email.utils import parsedate_to_datetime

MIN_PAUSE = 300           # never shorter than the regular request interval
MAX_PAUSE = 6 * 3600      # a strange header must not silence the widget for days
_GROWING = (600, 1200, 2400, 3600)   # without Retry-After: 10, 20, 40, then 60 minutes


def new() -> dict:
    return {"until": None, "failures": 0}


def is_rate_limit(status: int) -> bool:
    return status in (429, 503)


def retry_after(value, now: float) -> float | None:
    """Retry-After (seconds or HTTP date) → seconds from now; None if missing or unreadable."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if moment is None or moment.tzinfo is None:
        return None
    return max(0.0, moment.timestamp() - now)


def record_rate_limit(state: dict, now: float, header) -> None:
    wait = retry_after(header, now)
    if wait is None:
        wait = _GROWING[min(state["failures"], len(_GROWING) - 1)]
    state["failures"] += 1
    state["until"] = now + min(max(wait, MIN_PAUSE), MAX_PAUSE)


def record_success(state: dict) -> None:
    state.update(new())


def blocked_until(state: dict, now: float) -> float | None:
    """End of the running pause, or None. A pause too far ahead (clock set back) no longer counts."""
    until = state.get("until")
    if until is None or until <= now or until - now > MAX_PAUSE:
        return None
    return until
