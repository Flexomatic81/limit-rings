"""Persistent collector state (read positions, deduplication, buckets, last limits)."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .aggregate import prune_buckets
from .fsutil import write_json_atomic
from .sources import backoff

log = logging.getLogger(__name__)

STATE_VERSION = 1
SEEN_KEEP_DAYS = 35
SESSION_KEEP_DAYS = 400


def new_state() -> dict:
    return {
        "version": STATE_VERSION,
        "claude": {"files": {}, "seen": {}, "buckets": {}, "limits": None, "oauth_last_attempt": None,
                   "oauth_pause": backoff.new(), "hourly": {}, "hourly_backfill": False, "structure": None,
                   "keychain_login": None},
        "codex": {"files": {}, "sessions": {}, "buckets": {}, "limits": None, "oauth_last_attempt": None,
                  "oauth_pause": backoff.new(), "structure": None},
        "notified": {},
        "history": {},
    }


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _limits_ok(rec) -> bool:
    return rec is None or (isinstance(rec, dict) and _num(rec.get("updated_at"))
                           and isinstance(rec.get("limits"), list)
                           and (rec.get("extra") is None or isinstance(rec["extra"], dict)))


def _shape_ok(data: dict) -> bool:
    """Check only the shape (not the content) that prune_state and run rely on."""
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
            and _minutes_ok(v) for v in notified.values()):
        return False
    history = data["history"]
    if not isinstance(history, dict) or not all(
            isinstance(v, dict) and (v.get("resets_at") is None or _int(v["resets_at"])) and _minutes_ok(v)
            and isinstance(v.get("points"), list)
            and all(isinstance(pt, list) and len(pt) == 2 and _num(pt[0]) and _num(pt[1]) for pt in v["points"])
            for v in history.values()):
        return False
    if not _keychain_login_ok(claude["keychain_login"]):
        return False
    return all((s["oauth_last_attempt"] is None or _num(s["oauth_last_attempt"])) and _pause_ok(s["oauth_pause"])
               for s in (claude, codex))


def _minutes_ok(entry: dict) -> bool:
    """Window length of a history/notified entry: missing in older states, otherwise int or None."""
    return entry.get("minutes") is None or _int(entry["minutes"])


_WINDOW_KEYS = frozenset({"minutes", "model", "resets_at", "used", "seen", "missing"})
_EVENT_KEYS = frozenset({"kind", "id", "minutes", "model", "at"})


def _structure_ok(s) -> bool:
    """Known windows and changes of a provider (see changes.py); None until the first limits.

    Every key changes.py reads directly must be present, otherwise the next run would fail as a whole."""
    if s is None:
        return True
    if not (isinstance(s, dict) and "source" in s and (s["source"] is None or isinstance(s["source"], str))
            and _num(s.get("updated_at")) and isinstance(s.get("windows"), dict)
            and isinstance(s.get("gone"), dict) and isinstance(s.get("events"), list)):
        return False
    windows_ok = all(
        isinstance(w, dict) and _WINDOW_KEYS <= w.keys() and (w["minutes"] is None or _int(w["minutes"]))
        and (w["model"] is None or isinstance(w["model"], str))
        and (w["resets_at"] is None or _int(w["resets_at"])) and _num(w["used"]) and _num(w["seen"])
        and (w["missing"] is None or _num(w["missing"])) for w in s["windows"].values())
    gone_ok = all(isinstance(g, dict) and _num(g.get("at")) for g in s["gone"].values())
    events_ok = all(
        isinstance(e, dict) and _EVENT_KEYS <= e.keys() and isinstance(e["kind"], str) and isinstance(e["id"], str)
        and _num(e["at"]) and (e["minutes"] is None or _int(e["minutes"]))
        and (e["model"] is None or isinstance(e["model"], str))
        and (e.get("previous_minutes") is None or _int(e["previous_minutes"]))
        and (e.get("source") is None or isinstance(e["source"], str)) for e in s["events"])
    return windows_ok and gone_ok and events_ok


def _keychain_login_ok(kept) -> bool:
    """Plan and expiry of the last keychain read (see collect._claude_login), None before the first."""
    return kept is None or (isinstance(kept, dict) and (kept.get("plan") is None or isinstance(kept["plan"], str))
                            and (kept.get("expires_at") is None or _num(kept["expires_at"])))


def _pause_ok(pause) -> bool:
    return (isinstance(pause, dict) and (pause.get("until") is None or _num(pause["until"]))
            and _int(pause.get("failures")) and pause["failures"] >= 0)


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return new_state()
    except (OSError, ValueError) as e:
        log.warning("state unreadable (%s), re-reading everything", type(e).__name__)
        return new_state()
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        log.warning("state has unknown format, re-reading everything")
        return new_state()
    fresh = new_state()
    claude = data.get("claude")
    if isinstance(claude, dict) and "hourly" not in claude:
        # State from before the project/model breakdown: backfill the hourly counts once –
        # only if files have already been read (otherwise the next run re-reads everything anyway)
        claude["hourly"], claude["hourly_backfill"] = {}, bool(claude.get("files"))
    for provider in ("claude", "codex"):
        section = data.get(provider)
        if not isinstance(section, dict):
            return fresh
        for key, default in fresh[provider].items():
            section.setdefault(key, default)
    data.setdefault("notified", {})
    data.setdefault("history", {})
    for provider in ("claude", "codex"):
        if not _structure_ok(data[provider]["structure"]):  # only a hint in the card: start it afresh
            log.warning("%s: limit structure has unexpected shape, starting it afresh", provider)
            data[provider]["structure"] = None
    if not _shape_ok(data):
        log.warning("state has unexpected shape, re-reading everything")
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
