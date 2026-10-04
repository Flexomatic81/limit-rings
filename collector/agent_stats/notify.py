"""Desktop notifications when a limit reaches 80 % or 95 % – once per window."""

import logging
import subprocess
from dataclasses import dataclass

from .limits import same_window

log = logging.getLogger(__name__)

THRESHOLDS = (80, 95)
URGENT_LEVEL = 95
EARLY_LEVEL = 0  # level of the forecast-based early warning (below all thresholds)
EARLY_WARNING_SPAN = 30 * 60
EARLY_WARNING_WINDOW_MINUTES = 300


@dataclass(frozen=True)
class Notice:
    key: str
    level: int
    summary: str
    body: str
    urgent: bool


def _limit_name(label: str) -> str:
    if label == "5 h":
        return "5-hour limit"
    if label == "Week":
        return "weekly limit"
    if label.startswith("Week "):
        return f"weekly {label[len('Week '):]} limit"
    return f"{label} limit"


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
    return "Reset in " + _duration(resets_at - now)


def _early_warning_due(limit: dict, now: float) -> bool:
    fc = limit.get("forecast")
    return (limit.get("window_minutes") == EARLY_WARNING_WINDOW_MINUTES and isinstance(fc, dict)
            and fc.get("status") == "full" and fc["eta"] - now <= EARLY_WARNING_SPAN)


def _early_notice(key: str, name: str, limit: dict, pct: float, now: float) -> Notice:
    eta = limit["forecast"]["eta"]
    when = f"full in ~{_duration(eta - now)}" if eta > now else "almost full"
    reset = _countdown(limit.get("resets_at"), now)
    return Notice(key=key, level=EARLY_LEVEL, summary=f"{name}: {_limit_name(limit['label'])} {when}",
                  body=f"Now {round(pct)} %" + (f" · {reset}" if reset else ""), urgent=False)


def update_notices(providers: dict[str, list[dict]], notified: dict, now: float) -> list[Notice]:
    """Determine due notifications and record them in notified (key → level + window).

    providers maps the display name to its limits in stats.json format (with forecast, if any).
    A window whose reset has passed counts as 0 %. Below 80 %, the 5-hour limit gets an early
    warning if the forecast sees it full within 30 minutes at most. Entries for vanished or
    expired windows are dropped so that the next window notifies again.
    """
    notices = []
    current = set()
    for name, limits in providers.items():
        for limit in limits:
            key = f"{name.lower()}:{limit['id']}"
            resets_at = limit.get("resets_at")
            expired = resets_at is not None and resets_at <= now
            pct = 0.0 if expired else limit["used_percent"]
            level = max((t for t in THRESHOLDS if pct >= t), default=None)
            entry = notified.get(key)
            if entry is not None and not same_window(entry["resets_at"], resets_at):
                entry = None  # new window
            if expired:
                notified.pop(key, None)
                continue
            current.add(key)
            if level is None:
                if entry is not None:
                    entry["resets_at"] = resets_at
                elif _early_warning_due(limit, now):
                    notified[key] = {"level": EARLY_LEVEL, "resets_at": resets_at}
                    notices.append(_early_notice(key, name, limit, pct, now))
                else:
                    current.discard(key)
                continue
            if entry is not None and entry["level"] >= level:
                entry["resets_at"] = resets_at
                continue
            notified[key] = {"level": level, "resets_at": resets_at}
            notices.append(Notice(key=key, level=level,
                                  summary=f"{name}: {_limit_name(limit['label'])} at {round(pct)} %",
                                  body=_countdown(resets_at, now), urgent=level >= URGENT_LEVEL))
    for gone in set(notified) - current:
        del notified[gone]
    return notices


def send(notice: Notice) -> bool:
    """Show the notification via notify-send. Errors are logged, never propagated."""
    try:
        subprocess.run(["notify-send", "-a", "Agent Stats", "-i", "utilities-system-monitor",
                        "-u", "critical" if notice.urgent else "normal", notice.summary, notice.body],
                       check=True, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("notification failed: %s", type(e).__name__)
        return False
