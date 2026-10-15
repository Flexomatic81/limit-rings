"""Where a collector pass reads and writes, and the local time zone."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Paths:
    claude_root: Path
    codex_root: Path
    credentials: Path
    statusline_cache: Path | None
    state_file: Path
    stats_file: Path
    codex_auth: Path | None = None

    @classmethod
    def default(cls, home: Path) -> "Paths":
        cache = home / ".cache" / "limit-rings"
        return cls(
            claude_root=home / ".claude" / "projects",
            codex_root=home / ".codex" / "sessions",
            credentials=home / ".claude" / ".credentials.json",
            statusline_cache=cache / "claude-statusline-limits.json",
            state_file=cache / "state.json",
            stats_file=cache / "stats.json",
            codex_auth=home / ".codex" / "auth.json",
        )


def local_zone() -> tzinfo:
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for key in candidates:
        if key:
            try:
                return ZoneInfo(key)
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return datetime.now().astimezone().tzinfo or timezone.utc
