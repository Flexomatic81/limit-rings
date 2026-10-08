"""CI check: the collector output of a built package (run.py in an empty HOME) and the version baked into it.

Usage: check_package.py <package dir> <collector output file>
"""

import json
import sys
from pathlib import Path


def main(pkg: str, output: str) -> int:
    out = json.loads(Path(output).read_text(encoding="utf-8"))
    assert out.get("envelope") == 1 and "stats" in out, out
    meta = json.loads(Path(pkg, "metadata.json").read_text(encoding="utf-8"))["KPlugin"]["Version"]
    built = Path(pkg, "contents/collector/limit_rings/version.py").read_text(encoding="utf-8")
    assert f'VERSION = "{meta}"' in built, built
    print(f"package {meta}: collector ran")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
