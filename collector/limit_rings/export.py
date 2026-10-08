"""`run.py --export [--json]`: the daily token counts of all kept days (up to 400) as CSV or JSON.

Only reads ~/.cache/limit-rings: state.json for the main logins and, for the additional accounts that
stats.json lists, their own state files. No request, no log or login read, nothing written. The JSON
format is versioned (export_version); version 1 only ever gains fields.
"""

import csv
import json
import sys
from pathlib import Path

from .accounts import account_paths, parse_accounts
from .aggregate import FIELDS
from .state import load_state

EXPORT_VERSION = 1
COLUMNS = ("date", "provider", "account", *FIELDS, "total")


def _days(buckets, provider: str, account: str | None) -> list[dict]:
    out = []
    for day, bucket in buckets.items():
        counts = {f: int(bucket.get(f, 0)) for f in FIELDS}
        out.append({"date": day, "provider": provider, "account": account, **counts,
                    "total": sum(counts.values())})
    return out


def _accounts(cache: Path, home: Path):
    try:
        stats = json.loads((cache / "stats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = stats.get("accounts") if isinstance(stats, dict) else None
    if not isinstance(entries, dict):
        return []
    listed = [{"id": key, "provider": e.get("provider"), "dir": e.get("dir"), "name": e.get("name")}
              for key, e in entries.items() if isinstance(e, dict)]
    return [a for a in parse_accounts(json.dumps(listed), home) if a.error is None]


def rows(home: Path) -> list[dict]:
    """All days with counts, oldest first; account is None for the main login."""
    cache = home / ".cache" / "limit-rings"
    out = []
    if (cache / "state.json").is_file():
        state = load_state(cache / "state.json")
        for provider in ("claude", "codex"):
            out += _days(state[provider]["buckets"], provider, None)
    for account in _accounts(cache, home):
        state_file = account_paths(account, cache).state_file
        if state_file.is_file():
            out += _days(load_state(state_file)[account.provider]["buckets"], account.provider, account.name)
    return sorted(out, key=lambda r: (r["date"], r["provider"], r["account"] or ""))


def main(argv: list[str], home: Path | None = None) -> int:
    days = rows(home or Path.home())
    if "--json" in argv:
        sys.stdout.write(json.dumps({"export_version": EXPORT_VERSION, "days": days}, ensure_ascii=False) + "\n")
        return 0
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(COLUMNS)
    for day in days:
        writer.writerow([{**day, "account": day["account"] or ""}[c] for c in COLUMNS])
    return 0
