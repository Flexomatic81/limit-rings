"""Incremental reading of growing JSONL files."""

import os
from pathlib import Path


def read_new_lines(path: Path, file_state: dict | None) -> tuple[list[str], dict]:
    """Read complete lines from the stored offset.

    An incomplete last line is left for the next call.
    If the file is shorter than the offset or has been replaced (different inode),
    it is read from the start.
    """
    st = os.stat(path)
    offset = 0
    if file_state and file_state.get("inode") == st.st_ino and file_state.get("offset", 0) <= st.st_size:
        offset = file_state["offset"]

    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()

    end = data.rfind(b"\n")
    if end < 0:
        return [], {"offset": offset, "inode": st.st_ino}

    lines = [
        raw.decode("utf-8", errors="replace")
        for raw in data[: end + 1].split(b"\n")
        if raw.strip()
    ]
    return lines, {"offset": offset + end + 1, "inode": st.st_ino}


def list_jsonl(root: Path) -> tuple[list[Path], list[Path]]:
    """All *.jsonl under root, plus directories that could not be read.

    Path.rglob silently swallows directory read errors; os.walk reports them.
    """
    if not root.is_dir():
        return [], []
    failed: list[Path] = []

    def onerror(err: OSError) -> None:
        if not isinstance(err, FileNotFoundError):
            failed.append(Path(err.filename))

    found = []
    for dirpath, _dirs, names in os.walk(root, onerror=onerror):
        found.extend(Path(dirpath) / n for n in names if n.endswith(".jsonl"))
    return sorted(found), sorted(failed)


def prune_missing(files: dict, present: set[str], failed: list[Path]) -> None:
    """Remove entries of vanished files – except under unreadable directories."""
    prefixes = tuple(str(d) + os.sep for d in failed)
    for gone in set(files) - present:
        if not gone.startswith(prefixes):
            del files[gone]
