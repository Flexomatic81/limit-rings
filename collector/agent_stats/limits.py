"""Vereinheitlichung der Limit-Angaben verschiedener Quellen auf das stats.json-Format."""

from datetime import datetime


RESET_TOLERANCE = 300  # Sekunden; die API rundet resets_at mal auf, mal ab


def same_window(resets_a, resets_b) -> bool:
    """Gehören zwei Reset-Zeitpunkte zum selben Fenster? Kleine Abweichungen der API zählen nicht."""
    if resets_a is None or resets_b is None:
        return resets_a is None and resets_b is None
    return abs(resets_a - resets_b) <= RESET_TOLERANCE


def window_label(minutes: int) -> str:
    if minutes == 300:
        return "5 h"
    if minutes == 10080:
        return "Woche"
    if minutes % 1440 == 0:
        return f"{minutes // 1440} d"
    if minutes % 60 == 0:
        return f"{minutes // 60} h"
    return f"{minutes} min"


def make_limit(limit_id: str, label: str, used_percent, resets_at, window_minutes) -> dict:
    if isinstance(used_percent, bool) or not isinstance(used_percent, (int, float)):
        raise ValueError(f"{limit_id}: Auslastung fehlt")
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
    ("seven_day", 10080, "Woche"),
    ("seven_day_opus", 10080, "Woche Opus"),
    ("seven_day_sonnet", 10080, "Woche Sonnet"),
)


def _iso_to_epoch(value) -> int | None:
    if value is None:
        return None
    return round(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())


def normalize_oauth(resp: dict) -> list[dict]:
    if not isinstance(resp, dict):
        raise ValueError("Antwort ist kein Objekt")
    if not any(isinstance(resp.get(key), dict) for key, _, _ in OAUTH_WINDOWS):
        raise ValueError("keines der bekannten Fenster vorhanden")
    out = []
    for key, minutes, label in OAUTH_WINDOWS:
        w = resp.get(key)
        if not isinstance(w, dict) or w.get("utilization") is None:
            continue
        out.append(make_limit(key, label, w["utilization"], _iso_to_epoch(w.get("resets_at")), minutes))
    if not out:
        raise ValueError("kein verwertbares Fenster")
    labels = {l["label"] for l in out}
    for limit in _scoped_limits(resp.get("limits")):
        if limit["label"] not in labels:
            labels.add(limit["label"])
            out.append(limit)
    return out


def _scoped_limits(entries) -> list[dict]:
    """Modellbezogene Wochenlimits aus der neueren limits-Liste; kaputte Einträge entfallen."""
    out = []
    for entry in entries if isinstance(entries, list) else []:
        try:
            if entry.get("kind") != "weekly_scoped":
                continue
            name = entry["scope"]["model"]["display_name"]
            if not isinstance(name, str) or not name:
                continue
            out.append(make_limit(f"weekly_scoped:{name.lower()}", f"Woche {name}", entry.get("percent"),
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
    """Antwort des Codex-Nutzungsendpunkts → (Limits, Plan). Ohne verwertbares Fenster: ValueError."""
    if not isinstance(resp, dict) or not isinstance(resp.get("rate_limit"), dict):
        raise ValueError("rate_limit fehlt")
    out = []
    for key in ("primary", "secondary"):
        w = resp["rate_limit"].get(f"{key}_window")
        if not isinstance(w, dict):
            continue
        seconds = w.get("limit_window_seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError(f"{key}: Fensterlänge fehlt")
        minutes = seconds // 60
        out.append(make_limit(key, window_label(minutes), w.get("used_percent"), w.get("reset_at"), minutes))
    if not out:
        raise ValueError("kein verwertbares Fenster")
    return out, resp.get("plan_type")
