"""Persistenter Zustand des Collectors (Leseposition, Deduplizierung, Buckets, letzte Limits)."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .aggregate import prune_buckets
from .fsutil import write_json_atomic

log = logging.getLogger(__name__)

STATE_VERSION = 1
SEEN_KEEP_DAYS = 35
SESSION_KEEP_DAYS = 400


def new_state() -> dict:
    return {
        "version": STATE_VERSION,
        "claude": {"files": {}, "seen": {}, "buckets": {}, "limits": None, "oauth_last_attempt": None,
                   "hourly": {}, "hourly_backfill": False},
        "codex": {"files": {}, "sessions": {}, "buckets": {}, "limits": None, "oauth_last_attempt": None},
        "notified": {},
        "history": {},
    }


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _limits_ok(rec) -> bool:
    return rec is None or (isinstance(rec, dict) and _num(rec.get("updated_at"))
                           and isinstance(rec.get("limits"), list))


def _shape_ok(data: dict) -> bool:
    """Prüft nur die Form (nicht den Inhalt), die prune_state und run voraussetzen."""
    claude, codex = data["claude"], data["codex"]
    for section, dicts in ((claude, ("files", "seen", "buckets", "hourly")), (codex, ("files", "sessions", "buckets"))):
        if not all(isinstance(section[k], dict) for k in dicts):
            return False
        if not _limits_ok(section["limits"]):
            return False
    if not all(isinstance(v, dict) and isinstance(v.get("ts"), str) and isinstance(v.get("u"), list)
               and len(v["u"]) == 4 and all(_int(n) for n in v["u"]) for v in claude["seen"].values()):
        return False
    if not all(isinstance(v, dict) and _int(v.get("total")) and isinstance(v.get("day"), str)
               for v in codex["sessions"].values()):
        return False
    if not isinstance(claude["hourly_backfill"], bool) or not all(
            isinstance(b, dict) and all(isinstance(b.get(k), dict) and all(_int(v) for v in b[k].values())
                                        for k in ("p", "m"))
            for b in claude["hourly"].values()):
        return False
    notified = data["notified"]
    if not isinstance(notified, dict) or not all(
            isinstance(v, dict) and _int(v.get("level")) and (v.get("resets_at") is None or _int(v["resets_at"]))
            for v in notified.values()):
        return False
    history = data["history"]
    if not isinstance(history, dict) or not all(
            isinstance(v, dict) and (v.get("resets_at") is None or _int(v["resets_at"]))
            and isinstance(v.get("points"), list)
            and all(isinstance(pt, list) and len(pt) == 2 and _num(pt[0]) and _num(pt[1]) for pt in v["points"])
            for v in history.values()):
        return False
    return all(s["oauth_last_attempt"] is None or _num(s["oauth_last_attempt"]) for s in (claude, codex))


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return new_state()
    except (OSError, ValueError) as e:
        log.warning("Zustand unlesbar (%s), lese alles neu ein", type(e).__name__)
        return new_state()
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        log.warning("Zustand hat unbekanntes Format, lese alles neu ein")
        return new_state()
    fresh = new_state()
    claude = data.get("claude")
    if isinstance(claude, dict) and "hourly" not in claude:
        # Stand vor der Aufschlüsselung nach Projekt/Modell: stündliche Zählung einmal nachladen –
        # nur, wenn schon Dateien gelesen wurden (sonst liest der nächste Lauf ohnehin alles neu ein)
        claude["hourly"], claude["hourly_backfill"] = {}, bool(claude.get("files"))
    for provider in ("claude", "codex"):
        section = data.get(provider)
        if not isinstance(section, dict):
            return fresh
        for key, default in fresh[provider].items():
            section.setdefault(key, default)
    data.setdefault("notified", {})
    data.setdefault("history", {})
    if not _shape_ok(data):
        log.warning("Zustand hat unerwartete Form, lese alles neu ein")
        return fresh
    return data


def save_state(path: Path, state: dict) -> None:
    write_json_atomic(path, state)


def prune_state(state: dict, today: date) -> None:
    cutoff = (today - timedelta(days=SEEN_KEEP_DAYS)).isoformat()
    seen = state["claude"]["seen"]
    for key in [k for k, v in seen.items() if v["ts"][:10] < cutoff]:
        del seen[key]
    session_cutoff = (today - timedelta(days=SESSION_KEEP_DAYS)).isoformat()
    sessions = state["codex"]["sessions"]
    for key in [k for k, v in sessions.items() if v["day"] < session_cutoff]:
        del sessions[key]
    for provider in ("claude", "codex"):
        prune_buckets(state[provider]["buckets"], today)
