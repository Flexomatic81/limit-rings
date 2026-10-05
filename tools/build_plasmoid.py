"""Builds the Limit Rings widget package: the plasmoid plus its collector, compiled translations and build info.

    python3 tools/build_plasmoid.py --source store [--out dist]          → dist/limit-rings-<version>.plasmoid
    python3 tools/build_plasmoid.py --source git --repo-dir DIR --dir OUT → unpacked package in OUT (install.sh)

Standard library only: neither gettext nor zip is needed.
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import msgfmt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "io.github.flexomatic81.limitrings"
STORE_ID = ""  # content ID of the entry on store.kde.org – set after the first upload
SOURCES = ("store", "git", "dev")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # fixed, so that the same sources give the same archive


def version(root: Path = ROOT) -> str:
    meta = json.loads((root / "plasmoid" / PLUGIN_ID / "metadata.json").read_text(encoding="utf-8"))
    return meta["KPlugin"]["Version"]


def build_js(source: str, repo_dir: str = "", ver: str = "") -> str:
    store_id = STORE_ID if source == "store" else ""
    return (".pragma library\n\n"
            "// Written by tools/build_plasmoid.py: how this copy of the widget was installed.\n"
            "// The copy in the repository holds the defaults for running the widget from the checkout.\n"
            f"const installSource = {json.dumps(source)}\n"
            f"const storeId = {json.dumps(store_id)}\n"
            f"const repoDir = {json.dumps(repo_dir)}\n"
            f"const version = {json.dumps(ver)}\n")


def _ignore(directory, names):
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]


def build_tree(out: Path, source: str, repo_dir: str = "", root: Path = ROOT) -> Path:
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    if source == "git" and not repo_dir:
        raise ValueError("--repo-dir is required for --source git")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "plasmoid" / PLUGIN_ID, out, ignore=_ignore)
    contents = out / "contents"
    shutil.copytree(root / "collector" / "limit_rings", contents / "collector" / "limit_rings", ignore=_ignore)
    shutil.copy2(root / "collector" / "run.py", contents / "collector" / "run.py")
    for part, domain in (("plasmoid", f"plasma_applet_{PLUGIN_ID}"), ("collector", "limit-rings")):
        for po in sorted((root / "po" / part).glob("*.po")):
            msgfmt.compile_file(po, contents / "locale" / po.stem / "LC_MESSAGES" / f"{domain}.mo")
    (contents / "code" / "build.js").write_text(build_js(source, repo_dir, version(root)), encoding="utf-8")
    return out


def build_archive(dest: Path, source: str, repo_dir: str = "", root: Path = ROOT) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        tree = build_tree(Path(tmp) / PLUGIN_ID, source, repo_dir, root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as zf:
            for path in sorted(p for p in tree.rglob("*") if p.is_file()):
                info = zipfile.ZipInfo(path.relative_to(tree).as_posix(), ZIP_DATE)
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Limit Rings widget package.")
    parser.add_argument("--source", choices=SOURCES, required=True, help="how the package will be installed")
    parser.add_argument("--repo-dir", default="", help="checkout the package is built from (for --source git)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--dir", type=Path, help="write the unpacked package to this directory")
    target.add_argument("--out", type=Path, default=ROOT / "dist", help="directory for the .plasmoid archive")
    args = parser.parse_args(argv)
    try:
        if args.dir:
            print(build_tree(args.dir, args.source, args.repo_dir))
        else:
            print(build_archive(args.out / f"limit-rings-{version()}.plasmoid", args.source, args.repo_dir))
    except (OSError, ValueError) as e:  # msgfmt.PoError is a ValueError
        print(f"build_plasmoid.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
