"""Forecast for 5-hour and weekly limits: when will the limit be full at the current pace?

It is based on the percentages the collector sees on each run. The pace is the increase over a
span suited to the window type: 30 minutes for the 5-hour window, 24 hours for the week.
Because the values only come in whole percent, the data points need a minimum distance.
"""

from dataclasses import dataclass

from .limits import same_limit_window


@dataclass(frozen=True)
class Profile:
    rate_span: int  # span the pace is computed from
    min_span: int   # minimum span of the data points for a forecast
    keep: int       # how long points are kept
    max_age: int    # maximum age of the newest point
    min_gap: int    # minimum gap between stored points


PROFILES = {
    300: Profile(rate_span=30 * 60, min_span=10 * 60, keep=60 * 60, max_age=30 * 60, min_gap=0),
    10080: Profile(rate_span=24 * 3600, min_span=2 * 3600, keep=24 * 3600, max_age=6 * 3600, min_gap=10 * 60),
}


def update_history(history: dict, providers: dict[str, tuple[list[dict], float | None]]) -> None:
    """Extend the history of each 5-hour and weekly limit (key "provider:limit-id").

    providers maps the display name to (limits, time of the data). A new point is only added
    if the data is newer than the last point (and, for the week, at least 10 minutes later);
    a new window restarts the history.
    """
    current = set()
    for name, (limits, updated_at) in providers.items():
        for limit in limits:
            profile = PROFILES.get(limit.get("window_minutes"))
            if profile is None:
                continue
            key = f"{name.lower()}:{limit['id']}"
            current.add(key)
            entry = history.get(key)
            if entry is None or not same_limit_window(entry, limit):
                entry = history[key] = {"resets_at": limit.get("resets_at"), "points": []}
            entry["resets_at"] = limit.get("resets_at")
            entry["minutes"] = limit.get("window_minutes")
            points = entry["points"]
            newer = updated_at is not None and (
                not points or (updated_at > points[-1][0] and updated_at - points[-1][0] >= profile.min_gap))
            if newer:
                points.append([updated_at, limit["used_percent"]])
            if points:
                entry["points"] = [p for p in points if p[0] >= points[-1][0] - profile.keep]
    for gone in set(history) - current:
        del history[gone]


def forecast(entry: dict, resets_at, now: float, window_minutes: int = 300) -> dict | None:
    """{"status": "full", "eta": epoch} | {"status": "enough"} | None (too little or stale data)."""
    profile = PROFILES.get(window_minutes)
    points = entry["points"]
    if profile is None or not points or (resets_at is not None and resets_at <= now):
        return None
    newest_ts, newest_pct = points[-1]
    if newest_ts < now - profile.max_age:
        return None
    ref_ts, ref_pct = next(p for p in points if p[0] >= newest_ts - profile.rate_span)
    span = newest_ts - ref_ts
    if span < profile.min_span:
        return None
    rate = (newest_pct - ref_pct) / span
    if rate <= 0:
        return {"status": "enough"}
    eta = newest_ts + (100.0 - newest_pct) / rate
    if resets_at is not None and eta >= resets_at:
        return {"status": "enough"}
    return {"status": "full", "eta": int(eta)}
