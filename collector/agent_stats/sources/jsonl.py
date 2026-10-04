"""Inkrementelles Lesen wachsender JSONL-Dateien."""

import os
from pathlib import Path


def read_new_lines(path: Path, file_state: dict | None) -> tuple[list[str], dict]:
    """Liest vollständige Zeilen ab dem gespeicherten Offset.

    Eine unvollständige letzte Zeile bleibt für den nächsten Aufruf liegen.
    Ist die Datei kürzer als der Offset oder ersetzt worden (andere Inode),
    wird von vorn gelesen.
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
    """Alle *.jsonl unter root plus Verzeichnisse, die nicht gelesen werden konnten.

    Path.rglob verschluckt Lesefehler von Verzeichnissen still; os.walk meldet sie.
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
    """Entfernt Einträge verschwundener Dateien – außer unter nicht lesbaren Verzeichnissen."""
    prefixes = tuple(str(d) + os.sep for d in failed)
    for gone in set(files) - present:
        if not gone.startswith(prefixes):
            del files[gone]
