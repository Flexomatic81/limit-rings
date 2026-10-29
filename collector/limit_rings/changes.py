"""Changes to the limit structure: windows that appear, vanish, come back, change length or reset early.

The collector compares each new set of limits of a provider with the windows it saw before and
records what changed; the card shows the recent changes for a few days.
"""

from datetime import datetime, tzinfo
from typing import Any

from .limits import RESET_TOLERANCE, public_limit, same_window
from .models import JsonDict

GONE_AFTER = 3600  # a window counts as gone once it has been missing for this long
KEEP_EVENTS = 30 * 86400  # how long changes stay in the state file
MAX_EVENTS = 20
RECENT = 3 * 86400  # how long the card shows a change
LOCAL_SOURCES = frozenset({"statusline", "session_log"})  # limits read without the login


def _event(kind: str, limit: JsonDict, at: float, source: str | None, **extra: Any) -> JsonDict:
    return {
        "kind": kind,
        "id": limit["id"],
        "minutes": limit.get("window_minutes"),
        "model": public_limit(limit).get("model"),
        "at": at,
        "source": source,
        **extra,
    }


def _window(limit: JsonDict, at: float) -> JsonDict:
    return {
        "minutes": limit.get("window_minutes"),
        "model": public_limit(limit).get("model"),
        "resets_at": limit.get("resets_at"),
        "used": limit["used_percent"],
        "seen": at,
        "missing": None,
    }


def _reset_early(prev: JsonDict, limit: JsonDict, at: float) -> bool:
    """A new window although the previous one still had more than the API's rounding to go."""
    resets = prev["resets_at"]
    return (
        resets is not None
        and not same_window(resets, limit.get("resets_at"))
        and at < resets - RESET_TOLERANCE
        and limit["used_percent"] < prev["used"]
    )


def update(
    structure: JsonDict | None, rec: JsonDict | None, source: str | None, now: float, plan: str | None = None
) -> JsonDict | None:
    """Compare the limits record of a provider with the known windows and note the changes.

    Only a newer record counts. Another source (the status line knows fewer windows than the usage
    endpoint) or another plan starts a new baseline: with another source only a changed window
    length is still noted, with another plan nothing – a new plan brings new limits. Returns the
    structure to store; without a record, the given one.
    """
    if rec is None:
        return structure
    at = rec["updated_at"]
    events = structure["events"] if structure else []
    known_plan = structure.get("plan") if structure else None
    new_plan = plan is not None and known_plan is not None and plan != known_plan
    if structure is None or structure["source"] != source or new_plan:
        if structure is not None and not new_plan:
            for limit in rec["limits"]:
                prev = structure["windows"].get(limit["id"])
                if prev is not None:
                    _note_length(events, prev["minutes"], limit, at, source)
        windows = {lim["id"]: _window(lim, at) for lim in rec["limits"]}
        structure = {"source": source, "updated_at": at, "windows": windows, "gone": {}, "events": events}
    elif at <= structure["updated_at"]:
        return structure
    else:
        present = {limit["id"] for limit in rec["limits"]}
        for limit in rec["limits"]:
            _note_present(structure, limit, at)
        _note_missing(structure, present, at)
        structure["updated_at"] = at
    structure["plan"] = plan if plan is not None else known_plan
    return _prune(structure, now)


def _note_length(events: list[JsonDict], previous: int | None, limit: JsonDict, at: float, source: str | None) -> bool:
    """Note a changed window length; a length that only returns to what it was undoes the earlier change.

    Returns whether the length changed at all."""
    minutes = limit.get("window_minutes")
    if previous is None or minutes in (None, previous):
        return False
    last = next((e for e in reversed(events) if e["id"] == limit["id"] and e["kind"] == "length"), None)
    if last is not None and last["minutes"] == previous and last.get("previous_minutes") == minutes:
        events.remove(last)
    else:
        events.append(_event("length", limit, at, source, previous_minutes=previous))
    return True


def _note_present(structure: JsonDict, limit: JsonDict, at: float) -> None:
    """A window in the record: note a changed length, an early reset, a return or a new window, then keep it."""
    windows, gone, events, source = structure["windows"], structure["gone"], structure["events"], structure["source"]
    lid = limit["id"]
    prev = windows.get(lid)
    if prev is not None:
        if not _note_length(events, prev["minutes"], limit, at, source) and _reset_early(prev, limit, at):
            events.append(_event("early_reset", limit, at, source))
    elif lid in gone:
        events.append(_event("back", limit, at, source))
        del gone[lid]
    else:
        events.append(_event("new", limit, at, source))
    windows[lid] = _window(limit, at)


def _note_missing(structure: JsonDict, present: set[str], at: float) -> None:
    """Windows missing from the record count as gone once they have been missing for GONE_AFTER."""
    windows, gone = structure["windows"], structure["gone"]
    for lid in [k for k in windows if k not in present]:
        win = windows[lid]
        if win["missing"] is None:
            win["missing"] = at
        if at - win["missing"] >= GONE_AFTER:
            structure["events"].append(
                {
                    "kind": "gone",
                    "id": lid,
                    "minutes": win["minutes"],
                    "model": win["model"],
                    "at": win["missing"],
                    "source": structure["source"],
                }
            )
            gone[lid] = {"at": win["missing"]}
            del windows[lid]


def _prune(structure: JsonDict, now: float) -> JsonDict:
    cutoff = now - KEEP_EVENTS
    structure["events"] = [e for e in structure["events"] if e["at"] >= cutoff][-MAX_EVENTS:]
    structure["gone"] = {k: v for k, v in structure["gone"].items() if v["at"] >= cutoff}
    return structure


def recent(structure: JsonDict | None, now: float, tz: tzinfo, local_only: bool = False) -> list[JsonDict]:
    """The changes of the last days in stats.json format.

    local_only: only changes noticed in local data (a provider without login); events of unknown source –
    written before events remembered it – count as endpoint data."""
    out = []
    for e in (structure or {}).get("events", []):
        if e["at"] < now - RECENT:
            continue
        if local_only and e.get("source") not in LOCAL_SOURCES:
            continue
        limit = {"id": e["id"], "window_minutes": e["minutes"]}
        if e.get("model"):
            limit["model"] = e["model"]
        entry = {"kind": e["kind"], "limit": limit}
        if e.get("previous_minutes") is not None:
            entry["previous_minutes"] = e["previous_minutes"]
        entry["at"] = datetime.fromtimestamp(e["at"], tz).isoformat(timespec="seconds")
        out.append(entry)
    return out
