"""Token usage and limits from Codex session logs (~/.codex/sessions/**/*.jsonl)."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..limits import normalize_codex
from ..models import TokenEvent, parse_ts
from .jsonl import list_jsonl, prune_missing, read_new_lines

log = logging.getLogger(__name__)


@dataclass
class CodexResult:
    events: list[TokenEvent] = field(default_factory=list)
    invalid: int = 0
    unreadable: int = 0
    limits: list[dict] | None = None
    plan: str | None = None
    limits_ts: datetime | None = None


def _int(d: dict, key: str) -> int:
    value = d.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} is not an integer")
    return value


def _event_from_usage(ts: datetime, last: dict) -> TokenEvent:
    inp = _int(last, "input_tokens")
    cached = _int(last, "cached_input_tokens")
    return TokenEvent(
        ts=ts,
        input=max(0, inp - cached),
        output=_int(last, "output_tokens"),
        cache_read=cached,
        cache_write=_int(last, "cache_write_input_tokens"),
    )


def read_events(root: Path, files: dict, sessions: dict) -> CodexResult:
    res = CodexResult()
    paths, failed = list_jsonl(root)
    for d in failed:
        log.warning("directory unreadable: %s", d)
    res.unreadable += len(failed)
    present = set()
    for path in paths:
        name = str(path)
        present.add(name)
        old = files.get(name)
        try:
            lines, entry = read_new_lines(path, old)
        except OSError as e:
            log.warning("Codex log unreadable: %s (%s)", name, type(e).__name__)
            res.unreadable += 1
            continue
        # Reuse the remembered ID; when re-reading from 0, the session_meta line sets it again.
        session = (old or {}).get("session")
        for line in lines:
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    continue
                payload = d.get("payload")
                if d.get("type") == "session_meta" and isinstance(payload, dict):
                    session = payload.get("id") or payload.get("session_id") or session
                    continue
                if d.get("type") != "event_msg":
                    continue
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                ts = parse_ts(d.get("timestamp"))
                info = payload.get("info")
                if isinstance(info, dict):
                    total = _int(info.get("total_token_usage") or {}, "total_tokens")
                    key = session or name
                    if total > sessions.get(key, {}).get("total", 0):
                        res.events.append(_event_from_usage(ts, info.get("last_token_usage") or {}))
                        sessions[key] = {"total": total, "day": ts.date().isoformat()}
                rl = payload.get("rate_limits")
                if isinstance(rl, dict) and (res.limits_ts is None or ts > res.limits_ts):
                    res.limits = normalize_codex(rl)
                    res.plan = rl.get("plan_type")
                    res.limits_ts = ts
            except Exception:  # a broken line (RecursionError, OverflowError …) must not block the provider
                res.invalid += 1
        entry["session"] = session
        files[name] = entry
    prune_missing(files, present, failed)
    return res
