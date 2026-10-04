"""Normalizes limit data from the various sources to the stats.json format."""

from datetime import datetime


RESET_TOLERANCE = 300  # seconds; the API rounds resets_at sometimes up, sometimes down


def same_window(resets_a, resets_b) -> bool:
    """Do two reset times belong to the same window? Small API deviations are ignored."""
    if resets_a is None or resets_b is None:
        return resets_a is None and resets_b is None
    return abs(resets_a - resets_b) <= RESET_TOLERANCE


def window_label(minutes: int) -> str:
    if minutes == 300:
        return "5 h"
    if minutes == 10080:
        return "Week"
    if minutes % 1440 == 0:
        return f"{minutes // 1440} d"
    if minutes % 60 == 0:
        return f"{minutes // 60} h"
    return f"{minutes} min"


def make_limit(limit_id: str, label: str, used_percent, resets_at, window_minutes) -> dict:
    if isinstance(used_percent, bool) or not isinstance(used_percent, (int, float)):
        raise ValueError(f"{limit_id}: utilization missing")
    return {
        "id": limit_id,
        "label": label,
        "used_percent": float(used_percent),
        "resets_at": int(resets_at) if resets_at is not None else None,
        "window_minutes": int(window_minutes) if window_minutes is not None else None,
    }


def normalize_codex(rate_limits: dict) -> list[dict]:
    out = []
    for key in ("primary", "secondary"):
        w = rate_limits.get(key)
        if not isinstance(w, dict):
            continue
        minutes = w.get("window_minutes")
        label = window_label(int(minutes)) if minutes is not None else key
        out.append(make_limit(key, label, w.get("used_percent"), w.get("resets_at"), minutes))
    return out


OAUTH_WINDOWS = (
    ("five_hour", 300, "5 h"),
    ("seven_day", 10080, "Week"),
    ("seven_day_opus", 10080, "Week Opus"),
    ("seven_day_sonnet", 10080, "Week Sonnet"),
)


def _iso_to_epoch(value) -> int | None:
    if value is None:
        return None
    return round(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())


def normalize_oauth(resp: dict) -> list[dict]:
    if not isinstance(resp, dict):
        raise ValueError("response is not an object")
    if not any(isinstance(resp.get(key), dict) for key, _, _ in OAUTH_WINDOWS):
        raise ValueError("none of the known windows present")
    out = []
    for key, minutes, label in OAUTH_WINDOWS:
        w = resp.get(key)
        if not isinstance(w, dict) or w.get("utilization") is None:
            continue
        out.append(make_limit(key, label, w["utilization"], _iso_to_epoch(w.get("resets_at")), minutes))
    if not out:
        raise ValueError("no usable window")
    labels = {l["label"] for l in out}
    for limit in _scoped_limits(resp.get("limits")):
        if limit["label"] not in labels:
            labels.add(limit["label"])
            out.append(limit)
    return out


def _scoped_limits(entries) -> list[dict]:
    """Model-scoped weekly limits from the newer limits list; broken entries are dropped."""
    out = []
    for entry in entries if isinstance(entries, list) else []:
        try:
            if entry.get("kind") != "weekly_scoped":
                continue
            name = entry["scope"]["model"]["display_name"]
            if not isinstance(name, str) or not name:
                continue
            out.append(make_limit(f"weekly_scoped:{name.lower()}", f"Week {name}", entry.get("percent"),
                                  _iso_to_epoch(entry.get("resets_at")), 10080))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return out


def normalize_statusline(rate_limits: dict) -> list[dict]:
    out = []
    for key, minutes, label in OAUTH_WINDOWS[:2]:
        w = rate_limits.get(key)
        if not isinstance(w, dict) or w.get("used_percentage") is None:
            continue
        out.append(make_limit(key, label, w["used_percentage"], w.get("resets_at"), minutes))
    return out


def normalize_codex_usage(resp: dict) -> tuple[list[dict], str | None]:
    """Codex usage endpoint response → (limits, plan). No usable window: ValueError."""
    if not isinstance(resp, dict) or not isinstance(resp.get("rate_limit"), dict):
        raise ValueError("rate_limit missing")
    out = []
    for key in ("primary", "secondary"):
        w = resp["rate_limit"].get(f"{key}_window")
        if not isinstance(w, dict):
            continue
        seconds = w.get("limit_window_seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError(f"{key}: window length missing")
        minutes = seconds // 60
        out.append(make_limit(key, window_label(minutes), w.get("used_percent"), w.get("reset_at"), minutes))
    if not out:
        raise ValueError("no usable window")
    return out, resp.get("plan_type")
