"""Release helper for CI: checks the tag against metadata.json and prints the CHANGELOG.md section of the version.

    python3 tools/release_notes.py v0.3.0 > notes.md
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_plasmoid import ROOT, version  # noqa: E402


def changelog_section(text: str, ver: str) -> str:
    match = re.search(rf"^## {re.escape(ver)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    body = match.group(1).strip() if match else ""
    if not body:
        raise ValueError(f"CHANGELOG.md has no entries for {ver}")
    return body + "\n"


def check_tag(tag: str, ver: str) -> None:
    if tag != f"v{ver}":
        raise ValueError(f"tag {tag} does not match the version {ver} in metadata.json")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py TAG", file=sys.stderr)
        return 2
    try:
        ver = version()
        check_tag(argv[0], ver)
        sys.stdout.write(changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), ver))
    except (OSError, ValueError) as e:
        print(f"release_notes.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
