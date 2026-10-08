"""`run.py --status [--waybar]`: the last collected limits for scripts, shell prompts and bars.

Only reads ~/.cache/limit-rings/stats.json, which the widget's collector writes: no request, no log or
login read, nothing written. The JSON format is versioned (status_version); version 1 only ever gains fields.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .collect import local_zone
from .i18n import _
from .notify import _duration, _limit_name

STATUS_VERSION = 1
STALE_AFTER = 300            # seconds without a collector pass (the widget runs it every 60 s)
WARN, CRIT = 70, 90          # the widget's default thresholds; its own settings are not known here
NAMES = {"claude": "Claude", "codex": "Codex"}
LETTERS = {"claude": "C", "codex": "X"}


def _iso(epoch) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, local_zone()).isoformat(timespec="seconds")


def _age(iso: str | None, now: float) -> float | None:
    try:
        return now - datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


def _limit(limit: dict, now: float) -> dict:
    resets = limit.get("resets_at")
    reset = resets is not None and resets <= now
    used = 0.0 if reset else float(limit.get("used_percent", 0.0))
    fc = limit.get("forecast") if not reset else None
    if isinstance(fc, dict) and fc.get("status") == "full":
        fc = {"status": "full", "eta": _iso(fc.get("eta"))}
    elif isinstance(fc, dict) and fc.get("status") == "enough":
        fc = {"status": "enough"}
    else:
        fc = None
    return {"id": limit.get("id"), "window_minutes": limit.get("window_minutes"), "model": limit.get("model"),
            "used_percent": used, "remaining_percent": max(0.0, 100.0 - used), "resets_at": _iso(resets),
            "reset": reset, "forecast": fc}


def _entry(entry_id: str, provider: str, entry: dict, now: float, account: dict | None) -> dict:
    name = NAMES.get(provider, provider)
    if account is not None:
        name = f"{name} ({account['name']})"
    limits = entry.get("limits") if isinstance(entry.get("limits"), list) else []
    return {"id": entry_id, "provider": provider, "name": name, "account": account, "plan": entry.get("plan"),
            "login": entry.get("login", True), "limits_source": entry.get("limits_source"),
            "limits_updated_at": entry.get("limits_updated_at"),
            "limits": [_limit(l, now) for l in limits if isinstance(l, dict)]}


def build(stats: dict | None, now: float) -> dict:
    """stats.json → status format version 1."""
    if not isinstance(stats, dict) or stats.get("schema") != 2:
        return {"status_version": STATUS_VERSION, "generated_at": None, "stale": True, "providers": []}
    entries = []
    for key, entry in (stats.get("providers") or {}).items():
        if isinstance(entry, dict):
            entries.append(_entry(key, key, entry, now, None))
    for key, entry in (stats.get("accounts") or {}).items():
        if isinstance(entry, dict) and entry.get("provider") in NAMES:
            account = {"name": str(entry.get("name") or ""), "dir": entry.get("dir")}
            entries.append(_entry(key, entry["provider"], entry, now, account))
    age = _age(stats.get("generated_at"), now)
    return {"status_version": STATUS_VERSION, "generated_at": stats.get("generated_at"),
            "stale": age is None or age > STALE_AFTER, "providers": entries}


def _line(name: str, limit: dict, now: float) -> str:
    named = {"id": limit["id"], "window_minutes": limit["window_minutes"], "model": limit["model"]}
    head = f"{name} · {_limit_name(named)}: "
    if limit["reset"]:
        return head + _("reset")
    parts = [f"{round(limit['used_percent'])} %"]
    resets = _age(limit["resets_at"], now)
    if resets is not None and resets < 0:
        parts.append(_("Reset in %(duration)s") % {"duration": _duration(-resets)})
    fc = limit["forecast"]
    if fc and fc["status"] == "full":
        eta = _age(fc["eta"], now)
        parts.append(_("full in ~%(duration)s") % {"duration": _duration(-eta)} if eta is not None and eta < 0
                     else _("full soon"))
    elif fc:
        parts.append(_("lasts until reset"))
    return head + " · ".join(parts)


def _letter(entry: dict) -> str:
    if entry["account"] and entry["account"]["name"]:
        return entry["account"]["name"][0].upper()
    return LETTERS.get(entry["provider"], entry["provider"][:1].upper())


def waybar(status: dict, now: float | None = None) -> dict:
    """Status → a Waybar custom module ("return-type": "json")."""
    now = time.time() if now is None else now
    if not status["providers"]:
        return {"text": "–", "tooltip": _("No data – is the Limit Rings widget running?"), "class": ["stale"],
                "percentage": 0}
    texts, lines, highest, warning = [], [], 0.0, False
    for entry in status["providers"]:
        used = [l["used_percent"] for l in entry["limits"]]
        texts.append(f"{_letter(entry)} {round(max(used))}%" if used else f"{_letter(entry)} –")
        highest = max([highest] + used)
        warning = warning or any(l["forecast"] and l["forecast"]["status"] == "full" for l in entry["limits"])
        lines += [_line(entry["name"], l, now) for l in entry["limits"]]
    level = "critical" if highest >= CRIT else "warning" if highest >= WARN or warning else "normal"
    return {"text": " · ".join(texts), "tooltip": "\n".join(lines),
            "class": [level] + (["stale"] if status["stale"] else []), "percentage": round(highest)}


def main(argv: list[str], home: Path | None = None, now: float | None = None) -> int:
    now = time.time() if now is None else now
    path = (home or Path.home()) / ".cache" / "limit-rings" / "stats.json"
    try:
        stats = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stats = None
    out = build(stats, now)
    if "--waybar" in argv:
        out = waybar(out, now)
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    return 0
