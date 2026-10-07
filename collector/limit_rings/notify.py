"""When to warn about a limit (two thresholds, 80 % and 95 % by default, once per window).

The widget shows the notifications."""

from dataclasses import dataclass

from .i18n import _
from .limits import public_limit, same_limit_window, window_text

THRESHOLDS = (80, 95)  # default; the second one is urgent
EARLY_LEVEL = 0  # level of the forecast-based early warning (below all thresholds)
RESET_LEVEL = -1  # level of the notice that a warned window has reset
# Early warning when the forecast sees a limit full within this span (window length → seconds)
EARLY_WARNING_SPANS = {300: 30 * 60, 10080: 24 * 3600}


@dataclass(frozen=True)
class Notice:
    key: str
    level: int
    summary: str
    body: str
    urgent: bool

    def to_json(self) -> dict:
        return {"key": self.key, "summary": self.summary, "body": self.body, "urgent": self.urgent}


def _limit_name(limit: dict) -> str:
    limit = public_limit(limit)
    minutes, model = limit.get("window_minutes"), limit.get("model")
    if minutes == 10080:
        return _("weekly %(model)s limit") % {"model": model} if model else _("weekly limit")
    if minutes == 300 and not model:
        return _("5-hour limit")
    window = window_text(minutes) if minutes else limit["id"]
    if model:  # same naming as the plasmoid: "2 d Opus"
        window = f"{window} {model}"
    return _("%(window)s limit") % {"window": window}


def _duration(seconds: float) -> str:
    total_min = max(1, -(-int(seconds) // 60))
    d, h, m = total_min // 1440, (total_min % 1440) // 60, total_min % 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{m} min"


def _countdown(resets_at, now: float) -> str:
    if resets_at is None or resets_at <= now:
        return ""
    return _("Reset in %(duration)s") % {"duration": _duration(resets_at - now)}


def _early_warning_due(limit: dict, now: float) -> bool:
    fc = limit.get("forecast")
    span = EARLY_WARNING_SPANS.get(limit.get("window_minutes"))
    return (span is not None and isinstance(fc, dict)
            and fc.get("status") == "full" and fc["eta"] - now <= span)


def _reset_notice(key: str, name: str, limit: dict) -> Notice:
    summary = _("%(provider)s: %(limit)s reset") % {"provider": name, "limit": _limit_name(limit)}
    return Notice(key=key, level=RESET_LEVEL, summary=summary, body="", urgent=False)


def _early_notice(key: str, name: str, limit: dict, pct: float, now: float) -> Notice:
    eta = limit["forecast"]["eta"]
    args = {"provider": name, "limit": _limit_name(limit), "duration": _duration(eta - now)}
    summary = (_("%(provider)s: %(limit)s full in ~%(duration)s") if eta > now
               else _("%(provider)s: %(limit)s almost full")) % args
    reset = _countdown(limit.get("resets_at"), now)
    body = _("Now %(percent)d %%") % {"percent": round(pct)} + (f" · {reset}" if reset else "")
    return Notice(key=key, level=EARLY_LEVEL, summary=summary, body=body, urgent=False)


def update_notices(providers: dict[str, list[dict]], notified: dict, now: float,
                   thresholds: tuple[int, int] = THRESHOLDS, reset_notice: bool = False) -> list[Notice]:
    """Determine due notifications and record them in notified (key → level + window).

    providers maps the display name to its limits in stats.json format (with forecast, if any).
    A window whose reset has passed counts as 0 %. Below the first threshold, a limit gets an early
    warning if the forecast sees it full soon (5 h: within 30 minutes, week: within 24 hours).
    Entries for vanished or expired windows are dropped so that the next window notifies again;
    with reset_notice, a window that had warned says so when it resets.
    """
    notices = []
    current = set()
    for name, limits in providers.items():
        for limit in limits:
            key = f"{name.lower()}:{limit['id']}"
            resets_at = limit.get("resets_at")
            minutes = limit.get("window_minutes")
            expired = resets_at is not None and resets_at <= now
            pct = 0.0 if expired else limit["used_percent"]
            level = max((t for t in thresholds if pct >= t), default=None)
            entry = notified.get(key)
            if entry is not None and not same_limit_window(entry, limit):
                if reset_notice:
                    notices.append(_reset_notice(key, name, limit))
                entry = None  # new window
            if expired:
                if entry is not None and reset_notice:
                    notices.append(_reset_notice(key, name, limit))
                notified.pop(key, None)
                continue
            current.add(key)
            if level is None:
                if entry is not None:
                    entry.update(resets_at=resets_at, minutes=minutes)
                elif _early_warning_due(limit, now):
                    notified[key] = {"level": EARLY_LEVEL, "resets_at": resets_at, "minutes": minutes}
                    notices.append(_early_notice(key, name, limit, pct, now))
                else:
                    current.discard(key)
                continue
            if entry is not None and entry["level"] >= level:
                entry.update(resets_at=resets_at, minutes=minutes)
                continue
            notified[key] = {"level": level, "resets_at": resets_at, "minutes": minutes}
            summary = _("%(provider)s: %(limit)s at %(percent)d %%") % {
                "provider": name, "limit": _limit_name(limit), "percent": round(pct)}
            notices.append(Notice(key=key, level=level, summary=summary,
                                  body=_countdown(resets_at, now), urgent=level >= thresholds[-1]))
    for gone in set(notified) - current:
        del notified[gone]
    return notices
