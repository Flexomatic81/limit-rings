"""Token usage and limits from Codex session logs (~/.codex/sessions/**/*.jsonl)."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..limits import normalize_codex
from ..models import JsonDict, TokenEvent, parse_ts
from .jsonl import list_jsonl, prune_missing, read_new_lines

log = logging.getLogger(__name__)


@dataclass
class CodexResult:
    events: list[TokenEvent] = field(default_factory=list)
    invalid: int = 0
    unreadable: int = 0
    limits: list[JsonDict] | None = None
    plan: str | None = None
    limits_ts: datetime | None = None


def _int(d: JsonDict, key: str) -> int:
    value = d.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} is not an integer")
    return value


@dataclass
class _Context:
    """What the following lines of a log belong to – the session, working directory and model of the last
    session_meta / turn_context line. Remembered per file, since a pass reads only the new lines."""

    session: Any = None
    cwd: str | None = None
    model: str | None = None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _note_context(kind: object, payload: JsonDict, ctx: _Context) -> bool:
    """A session_meta or turn_context line updates the context; True if the line was one of them."""
    if kind == "session_meta":
        ctx.session = payload.get("id") or payload.get("session_id") or ctx.session
        ctx.cwd = _text(payload.get("cwd")) or ctx.cwd
        return True
    if kind == "turn_context":
        ctx.cwd = _text(payload.get("cwd")) or ctx.cwd
        ctx.model = _text(payload.get("model")) or ctx.model
        return True
    return False


def _event_from_usage(ts: datetime, last: JsonDict, ctx: _Context) -> TokenEvent:
    inp = _int(last, "input_tokens")
    cached = _int(last, "cached_input_tokens")
    return TokenEvent(
        ts=ts,
        input=max(0, inp - cached),
        output=_int(last, "output_tokens"),
        cache_read=cached,
        cache_write=_int(last, "cache_write_input_tokens"),
        model=ctx.model,
        project=ctx.cwd,
    )


def read_events(root: Path, files: JsonDict, sessions: JsonDict) -> CodexResult:
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
        # Reuse the remembered context; when re-reading from 0, its lines set it again.
        ctx = _Context(*((old or {}).get(k) for k in ("session", "cwd", "model")))
        for line in lines:
            try:
                _read_line(line, ctx, name, sessions, res)
            except Exception:  # a broken line (RecursionError, OverflowError …) must not block the provider
                res.invalid += 1
        entry.update(session=ctx.session, cwd=ctx.cwd, model=ctx.model)
        files[name] = entry
    prune_missing(files, present, failed)
    return res


def _read_line(line: str, ctx: _Context, name: str, sessions: JsonDict, res: CodexResult) -> None:
    """One log line: session_meta / turn_context lines set the context, a token_count event adds usage (attributed
    to the context's directory and model) and limits."""
    d = json.loads(line)
    payload = d.get("payload") if isinstance(d, dict) else None
    if not isinstance(payload, dict) or _note_context(d.get("type"), payload, ctx):
        return
    if d.get("type") != "event_msg" or payload.get("type") != "token_count":
        return
    ts = parse_ts(d.get("timestamp"))
    info = payload.get("info")
    if isinstance(info, dict):
        total = _int(info.get("total_token_usage") or {}, "total_tokens")
        key = ctx.session or name
        if total > sessions.get(key, {}).get("total", 0):
            res.events.append(_event_from_usage(ts, info.get("last_token_usage") or {}, ctx))
            sessions[key] = {"total": total, "day": ts.date().isoformat()}
    rl = payload.get("rate_limits")
    if isinstance(rl, dict) and (res.limits_ts is None or ts > res.limits_ts):
        res.limits = normalize_codex(rl)
        res.plan = rl.get("plan_type")
        res.limits_ts = ts
