"""Token-Verbrauch aus Claude-Code-Transkripten (~/.claude/projects/**/*.jsonl)."""

import json
import logging
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path

from ..models import TokenEvent, parse_ts
from .jsonl import list_jsonl, prune_missing, read_new_lines

log = logging.getLogger(__name__)


@dataclass
class ReadResult:
    events: list[TokenEvent] = field(default_factory=list)
    invalid: int = 0
    unreadable: int = 0


def _count(usage: dict, key: str) -> int:
    value = usage.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} ist keine Ganzzahl")
    return value


def parse_line(line: str) -> tuple[str, TokenEvent] | None:
    d = json.loads(line)  # ValueError bei ungültigem JSON
    if not isinstance(d, dict):
        raise ValueError("Zeile ist kein Objekt")
    msg = d.get("message")
    if not isinstance(msg, dict) or "usage" not in msg:
        return None
    usage = msg["usage"]
    if not isinstance(usage, dict):
        raise ValueError("usage ist kein Objekt")
    key = f"{msg.get('id') or d.get('uuid')}|{d.get('requestId')}"
    ev = TokenEvent(
        ts=parse_ts(d.get("timestamp")),
        input=_count(usage, "input_tokens"),
        output=_count(usage, "output_tokens"),
        cache_read=_count(usage, "cache_read_input_tokens"),
        cache_write=_count(usage, "cache_creation_input_tokens"),
        model=msg.get("model") if isinstance(msg.get("model"), str) else None,
        project=d.get("cwd") if isinstance(d.get("cwd"), str) else None,
    )
    return key, ev


def read_events(root: Path, files: dict, seen: dict) -> ReadResult:
    res = ReadResult()
    paths, failed = list_jsonl(root)
    for d in failed:
        log.warning("Verzeichnis nicht lesbar: %s", d)
    res.unreadable += len(failed)
    present = set()
    for path in paths:
        name = str(path)
        present.add(name)
        try:
            lines, files[name] = read_new_lines(path, files.get(name))
        except OSError as e:
            log.warning("Transkript nicht lesbar: %s (%s)", name, type(e).__name__)
            res.unreadable += 1
            continue
        for line in lines:
            try:
                parsed = parse_line(line)
            except Exception:  # eine kaputte Zeile (RecursionError, OverflowError …) darf den Anbieter nicht blockieren
                res.invalid += 1
                continue
            if parsed is None:
                continue
            key, ev = parsed
            usage = [ev.input, ev.output, ev.cache_read, ev.cache_write]
            known = seen.get(key)
            if known is None:
                seen[key] = {"ts": ev.ts.astimezone(timezone.utc).isoformat(), "u": usage}
                res.events.append(ev)
                continue
            # Streaming-Zwischenstände: nur den Zuwachs verbuchen, am Tag der ersten Zeile.
            delta = [max(0, new - old) for new, old in zip(usage, known["u"])]
            if any(delta):
                known["u"] = [max(new, old) for new, old in zip(usage, known["u"])]
                res.events.append(TokenEvent(parse_ts(known["ts"]), *delta, model=ev.model, project=ev.project))
    prune_missing(files, present, failed)
    if res.invalid:
        log.debug("%d ungültige Zeilen in Claude-Transkripten übersprungen", res.invalid)
    return res
