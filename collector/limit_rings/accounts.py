"""Additional accounts (own CLAUDE_CONFIG_DIR / CODEX_HOME) from the widget settings.

The widget passes the shown ones as LIMIT_RINGS_ACCOUNTS (JSON). Each valid account is collected like
the main account, from its own directory and with its own state file; nothing else is read.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .collect import Paths

log = logging.getLogger(__name__)

MAX_ACCOUNTS = 8
PROVIDER_NAMES = {"claude": "Claude", "codex": "Codex"}
MAIN_DIRS = {"claude": ".claude", "codex": ".codex"}
_ID = re.compile(r"[a-z0-9]{1,16}")


@dataclass(frozen=True)
class Account:
    id: str
    provider: str | None
    dir: Path | None
    dir_text: str
    name: str
    error: str | None = None

    @property
    def label(self) -> str:
        return f"{PROVIDER_NAMES.get(self.provider or '', '?')} ({self.name})"

    @property
    def state_key(self) -> str:
        """State file name from provider and directory only: a changed directory starts afresh, and widgets
        that list the same directory under different ids share one state (interval, pause, notices)."""
        digest = hashlib.sha256(f"{self.provider}:{self.dir}".encode()).hexdigest()[:12]
        return f"{self.provider}-{digest}"


def _resolve(text: str, home: Path) -> Path | None:
    """Absolute, canonical directory (".." and symlinks resolved) or None."""
    if text == "~" or text.startswith("~/"):
        text = str(home) + text[1:]
    try:
        if not text or not Path(text).is_absolute():
            return None
        return Path(text).resolve()
    except (OSError, RuntimeError, ValueError):  # e.g. a symlink loop or a NUL character
        return None


def parse_accounts(text: str | None, home: Path) -> list[Account]:
    """LIMIT_RINGS_ACCOUNTS → accounts; invalid entries with a usable id come back with error set."""
    try:
        entries = json.loads(text) if text else []
    except ValueError:
        log.warning("LIMIT_RINGS_ACCOUNTS is not valid JSON – no additional accounts")
        return []
    if not isinstance(entries, list):
        return []
    out: list[Account] = []
    ids: set[str] = set()
    dirs: set[tuple[str, Path]] = set()
    for item in entries:
        if len(out) >= MAX_ACCOUNTS:
            log.warning("more than %d additional accounts – the rest is ignored", MAX_ACCOUNTS)
            break
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not _ID.fullmatch(item["id"])
            or item["id"] in ids
        ):
            continue
        ids.add(item["id"])
        raw_provider, raw_dir, raw_name = item.get("provider"), item.get("dir"), item.get("name")
        provider = raw_provider if isinstance(raw_provider, str) and raw_provider in PROVIDER_NAMES else None
        dir_text = raw_dir if isinstance(raw_dir, str) else ""
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            name = f"{PROVIDER_NAMES.get(provider or '', 'Account')} 2"
        path = _resolve(dir_text, home)
        main = _resolve(str(home / MAIN_DIRS[provider]), home) if provider else None
        if provider is not None and path is not None and path != main and (provider, path) not in dirs:
            dirs.add((provider, path))
            out.append(Account(item["id"], provider, path, dir_text, name))
        else:
            out.append(Account(item["id"], provider, None, dir_text, name, "account_invalid"))
    return out


def account_paths(account: Account, cache: Path) -> Paths:
    d = account.dir
    if d is None:
        raise ValueError(f"account {account.id} has no valid directory")
    return Paths(
        claude_root=d / "projects",
        codex_root=d / "sessions",
        credentials=d / ".credentials.json",
        statusline_cache=None,
        state_file=cache / "accounts" / f"{account.state_key}.json",
        stats_file=cache / "stats.json",
        codex_auth=d / "auth.json",
    )


def prune_account_states(cache: Path, keep_keys: set[str], now: float | None = None, keep_days: int = 30) -> None:
    """Remove state files (by state_key) of accounts that are not shown and were not touched for keep_days."""
    folder = cache / "accounts"
    now = time.time() if now is None else now
    try:
        files = list(folder.iterdir())
    except OSError:
        return
    for f in files:
        key = f.name.split(".", 1)[0]
        if not (f.name.endswith(".json") or f.name.endswith(".json.corrupt")) or key in keep_keys:
            continue
        try:
            if now - f.stat().st_mtime >= keep_days * 86400:
                f.unlink()
        except OSError:
            pass
