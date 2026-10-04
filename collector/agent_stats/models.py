"""Gemeinsame Datentypen."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TokenEvent:
    """Token-Verbrauch eines einzelnen Modellaufrufs."""

    ts: datetime  # tz-aware
    input: int
    output: int
    cache_read: int
    cache_write: int
    model: str | None = None    # Modell-ID (nur Claude)
    project: str | None = None  # Arbeitsverzeichnis (nur Claude)


def parse_ts(value: str) -> datetime:
    """ISO-8601-Zeitstempel (mit 'Z' oder Offset) → tz-aware datetime."""
    if not isinstance(value, str):
        raise ValueError("Zeitstempel fehlt")
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("Zeitstempel ohne Zeitzone")
    return ts
