"""Normalizes limit data from the various sources to the stats.json format."""

import math
import re
from datetime import datetime


RESET_TOLERANCE = 300  # seconds; the API rounds resets_at sometimes up, sometimes down


def same_window(resets_a, resets_b) -> bool:
    """Do two reset times belong to the same window? Small API deviations are ignored."""
    if resets_a is None or resets_b is None:
        return resets_a is None and resets_b is None
    return abs(resets_a - resets_b) <= RESET_TOLERANCE


def window_text(minutes: int) -> str:
    """Language-neutral window length ("5 h", "7 d", "45 min"); the plasmoid names the windows."""
    if minutes % 1440 == 0:
        return f"{minutes // 1440} d"
    if minutes % 60 == 0:
        return f"{minutes // 60} h"
    return f"{minutes} min"


def make_limit(limit_id: str, used_percent, resets_at, window_minutes, model: str | None = None) -> dict:
    if isinstance(used_percent, bool) or not isinstance(used_percent, (int, float)):
        raise ValueError(f"{limit_id}: utilization missing")
    out = {
        "id": limit_id,
        # Display text of collector versions before schema 2; kept only in state.json so that an
        # older collector still works after a rollback. stats.json gets it removed (public_limit).
        "label": _legacy_label(limit_id, window_minutes, model),
        "used_percent": float(used_percent),
        "resets_at": int(resets_at) if resets_at is not None else None,
        "window_minutes": int(window_minutes) if window_minutes is not None else None,
    }
    if model:
        out["model"] = model
    return out


def _legacy_label(limit_id: str, window_minutes, model: str | None) -> str:
    if window_minutes is None:
        return limit_id
    if window_minutes == 300:
        return "5 h"
    if window_minutes == 10080:
        return f"Week {model}" if model else "Week"
    return window_text(int(window_minutes))


_LEGACY_SCOPED = re.compile(r"^(?:Week|Woche) (.+)$")


def public_limit(limit: dict) -> dict:
    """Limit as written to stats.json: no display label; model-scoped limits carry "model".

    Records saved before schema 2 still have a label ("Woche Opus", "Week Opus") and no model.
    """
    out = {k: v for k, v in limit.items() if k not in ("label", "model")}
    model = limit.get("model")
    if not model:
        m = _LEGACY_SCOPED.match(limit.get("label") or "")
        model = m.group(1) if m else None
    if model:
        out["model"] = model
    return out


def normalize_codex(rate_limits: dict) -> list[dict]:
    out = []
    for key in ("primary", "secondary"):
        w = rate_limits.get(key)
        if not isinstance(w, dict):
            continue
        out.append(make_limit(key, w.get("used_percent"), w.get("resets_at"), w.get("window_minutes")))
    return out


OAUTH_WINDOWS = (
    ("five_hour", 300, None),
    ("seven_day", 10080, None),
    ("seven_day_opus", 10080, "Opus"),
    ("seven_day_sonnet", 10080, "Sonnet"),
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
    for key, minutes, model in OAUTH_WINDOWS:
        w = resp.get(key)
        if not isinstance(w, dict) or w.get("utilization") is None:
            continue
        out.append(make_limit(key, w["utilization"], _iso_to_epoch(w.get("resets_at")), minutes, model))
    if not out:
        raise ValueError("no usable window")
    models = {l.get("model") for l in out}
    for limit in _scoped_limits(resp.get("limits")):
        if limit["model"] not in models:
            models.add(limit["model"])
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
            out.append(make_limit(f"weekly_scoped:{name.lower()}", entry.get("percent"),
                                  _iso_to_epoch(entry.get("resets_at")), 10080, name))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return out


def normalize_statusline(rate_limits: dict) -> list[dict]:
    out = []
    for key, minutes, _model in OAUTH_WINDOWS[:2]:
        w = rate_limits.get(key)
        if not isinstance(w, dict) or w.get("used_percentage") is None:
            continue
        out.append(make_limit(key, w["used_percentage"], w.get("resets_at"), minutes))
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
        out.append(make_limit(key, w.get("used_percent"), w.get("reset_at"), minutes))
    if not out:
        raise ValueError("no usable window")
    return out, resp.get("plan_type")


def _amount(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def normalize_extra_usage(resp) -> dict | None:
    """Claude's paid extra usage (amounts in minor units → currency units); None if off or unusable."""
    extra = resp.get("extra_usage") if isinstance(resp, dict) else None
    if not isinstance(extra, dict) or extra.get("is_enabled") is not True or not _amount(extra.get("used_credits")):
        return None
    limit = extra.get("monthly_limit")
    if limit is not None and not _amount(limit):
        return None
    percent = extra.get("utilization")
    if not _amount(percent):
        percent = min(100.0, extra["used_credits"] / limit * 100) if limit else None
    currency = extra.get("currency")
    return {"kind": "extra_usage", "used": extra["used_credits"] / 100,
            "limit": limit / 100 if limit is not None else None,
            "percent": float(percent) if percent is not None else None,
            "currency": currency if isinstance(currency, str) and currency else "USD"}


def normalize_codex_credits(resp) -> dict | None:
    """Codex credit balance; None without a balance (and not unlimited) or if unusable."""
    credits = resp.get("credits") if isinstance(resp, dict) else None
    if not isinstance(credits, dict):
        return None
    unlimited = credits.get("unlimited") is True
    try:
        balance = float(credits.get("balance"))
    except (TypeError, ValueError):
        balance = None
    if not _amount(balance):
        if not unlimited:
            return None
        balance = 0.0
    if balance <= 0 and not unlimited:
        return None
    return {"kind": "credits", "balance": balance, "unlimited": unlimited}
