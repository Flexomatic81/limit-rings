"""Shared data types."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TokenEvent:
    """Token usage of a single model call."""

    ts: datetime  # tz-aware
    input: int
    output: int
    cache_read: int
    cache_write: int
    model: str | None = None    # model ID (Claude only)
    project: str | None = None  # working directory (Claude only)


def parse_ts(value: str) -> datetime:
    """ISO 8601 timestamp (with 'Z' or offset) → tz-aware datetime."""
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("timestamp without time zone")
    return ts
