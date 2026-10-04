"""Desktop-Benachrichtigungen, wenn ein Limit 80 % bzw. 95 % erreicht – einmal pro Zeitfenster."""

import logging
import subprocess
from dataclasses import dataclass

from .limits import same_window

log = logging.getLogger(__name__)

THRESHOLDS = (80, 95)
URGENT_LEVEL = 95
EARLY_LEVEL = 0  # Stufe der Frühwarnung aus der Prognose (unterhalb aller Schwellen)
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
        return "5-h-Limit"
    if label == "Woche":
        return "Wochenlimit"
    if label.startswith("Woche "):
        return "Wochenlimit " + label[len("Woche "):]
    return f"Limit {label}"


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
    when = f"in ~{_duration(eta - now)} voll" if eta > now else "gleich voll"
    reset = _countdown(limit.get("resets_at"), now)
    return Notice(key=key, level=EARLY_LEVEL, summary=f"{name}: {_limit_name(limit['label'])} {when}",
                  body=f"Jetzt {round(pct)} %" + (f" · {reset}" if reset else ""), urgent=False)


def update_notices(providers: dict[str, list[dict]], notified: dict, now: float) -> list[Notice]:
    """Ermittelt fällige Benachrichtigungen und merkt sie in notified (Schlüssel → Stufe + Fenster).

    providers bildet den Anzeigenamen auf die Limits im stats.json-Format ab (ggf. mit Prognose).
    Ein Fenster, dessen Reset vorbei ist, zählt als 0 %. Unterhalb von 80 % gibt es beim 5-h-Limit
    eine Frühwarnung, wenn die Prognose es in höchstens 30 Minuten voll sieht. Einträge für
    verschwundene oder abgelaufene Fenster entfallen, damit das nächste wieder benachrichtigt.
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
                entry = None  # neues Fenster
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
                                  summary=f"{name}: {_limit_name(limit['label'])} bei {round(pct)} %",
                                  body=_countdown(resets_at, now), urgent=level >= URGENT_LEVEL))
    for gone in set(notified) - current:
        del notified[gone]
    return notices


def send(notice: Notice) -> bool:
    """Zeigt die Benachrichtigung über notify-send. Fehler werden geloggt, nie weitergereicht."""
    try:
        subprocess.run(["notify-send", "-a", "Agent Stats", "-i", "utilities-system-monitor",
                        "-u", "critical" if notice.urgent else "normal", notice.summary, notice.body],
                       check=True, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Benachrichtigung fehlgeschlagen: %s", type(e).__name__)
        return False
