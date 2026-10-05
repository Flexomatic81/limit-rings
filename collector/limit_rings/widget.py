"""Entry point for the widget: one locked collector pass, the result as one JSON line on stdout.

Several widget instances (panel and desktop) start passes independently; the lock makes the others
return the last stats.json without collecting, so notifications come from one instance only.
"""

import fcntl
import json
import logging
import logging.handlers
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, tzinfo
from pathlib import Path

from .collect import Paths, local_zone, run_safely

ENVELOPE = 1
LOG_BYTES = 256 * 1024
LOCK_WAIT = 45.0  # seconds; below the widget's 60 s interval
LEGACY_TIMER = Path(".config/systemd/user/limit-rings.timer")  # relative to HOME; removed by install.sh


def _setup_logging(cache: Path) -> None:
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(cache, 0o700)
    handler = logging.handlers.RotatingFileHandler(cache / "collector.log", maxBytes=LOG_BYTES, backupCount=1,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def _read_stats(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            stats = json.load(fh)
    except (OSError, ValueError):
        return None
    return stats if isinstance(stats, dict) else None


def _acquire(fd: int, wait: float) -> bool:
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.5)


def collect_once(paths: Paths, lock_file: Path, clock: Callable[[], datetime], tz: tzinfo, notify: bool = True,
                 wait: float = LOCK_WAIT) -> tuple[dict, int]:
    """Run one pass, after the pass of another instance if that one holds the lock; return envelope and exit code.

    Every instance gets its own pass: one that gave up on a busy lock would never see a notice while the other
    instance – perhaps one with notifications off – always got there first. A pass right after another one has
    little to read, and the limits are fetched at most every 5 minutes anyway. Only a pass that takes longer than
    `wait` (the very first one over all transcripts) makes the others return the last stats.json.

    notify=False (the widget has notifications off) leaves due notices for an instance that shows them."""
    notices = []
    code = 0
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if not _acquire(fd, wait):
            stats = _read_stats(paths.stats_file)
        else:
            stats = run_safely(paths, clock(), tz, notices.append if notify else None)
            if stats is None:
                code = 1
                notices.clear()  # state.json was not saved: they come again with the next pass
                stats = _read_stats(paths.stats_file)
    finally:
        os.close(fd)
    return {"envelope": ENVELOPE, "stats": stats, "notices": [n.to_json() for n in notices]}, code


def legacy_timer(home: Path) -> bool:
    """True while the systemd timer of a version ≤ 0.2 is installed: it collects without the lock."""
    return (home / LEGACY_TIMER).exists()


def main(home: Path | None = None) -> int:
    home = home or Path.home()
    paths = Paths.default(home)
    cache = paths.stats_file.parent
    _setup_logging(cache)
    if legacy_timer(home):
        # e.g. a store install over a git install of 0.2: two writers would overwrite each other's state.
        logging.getLogger("limit_rings").warning("legacy timer %s found – not collecting", LEGACY_TIMER)
        envelope = {"envelope": ENVELOPE, "error": "legacy-timer", "stats": _read_stats(paths.stats_file),
                    "notices": []}
        code = 0
    else:
        tz = local_zone()
        notify = os.environ.get("LIMIT_RINGS_NOTIFY", "1") != "0"  # set by the widget from its settings
        envelope, code = collect_once(paths, cache / ".lock", lambda: datetime.now(tz), tz, notify)
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code
