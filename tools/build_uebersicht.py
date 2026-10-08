"""Builds the macOS widget for Übersicht: the widget folder with the shared display logic, a copy of the collector
and the German texts as JSON.

Usage:
    python3 tools/build_uebersicht.py --out dist      zip of the widget folder, named by version
    python3 tools/build_uebersicht.py --dir DIR       the unpacked widget folder, as DIR/limit-rings.widget

Standard library only.
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
from build_plasmoid import PLUGIN_ID, ROOT, ZIP_DATE, _ignore, version, version_py  # noqa: E402

WIDGET = "limit-rings.widget"


def catalog_json(po: Path) -> dict:
    """msgctxt\\x04msgid (or msgid) → translation; plural entries by their singular → list of forms."""
    out = {}
    for key, value in msgfmt.parse(po.read_text(encoding="utf-8")).items():
        if not key:
            continue
        msgid = key.decode("utf-8").split("\x00")[0]
        forms = value.decode("utf-8").split("\x00")
        out[msgid] = forms if b"\x00" in key else forms[0]
    return out


MARKER = ".limit-rings-build"   # written into every build: only such a folder is ever replaced
# card.mjs imports the shared module from its place in the plasmoid; the build puts a copy beside it
CORE_IMPORT = '"../../../plasmoid/io.github.flexomatic81.limitrings/contents/code/core.mjs"'


def build_tree(out: Path, root: Path = ROOT) -> Path:
    target = out.resolve()
    if target == root.resolve() or (root / "macos").resolve() in (target, *target.parents):
        raise ValueError(f"{out} is inside the sources – refusing to build there")
    if out.exists() or out.is_symlink():
        if not (out.is_dir() and (not any(out.iterdir()) or (out / MARKER).is_file())):
            raise ValueError(f"{out} exists and is not an earlier build – refusing to overwrite it")
        shutil.rmtree(out)
    shutil.copytree(root / "macos" / WIDGET, out, ignore=_ignore)
    (out / MARKER).write_text("", encoding="utf-8")
    # Helpers live in lib/: Übersicht takes every .js/.jsx/.coffee file as a widget, except under lib/.
    shutil.copy2(root / "plasmoid" / PLUGIN_ID / "contents" / "code" / "core.mjs", out / "lib" / "core.mjs")
    card = out / "lib" / "card.mjs"
    text = card.read_text(encoding="utf-8")
    if CORE_IMPORT not in text:
        raise ValueError("card.mjs does not import the shared module from the plasmoid")
    card.write_text(text.replace(CORE_IMPORT, '"./core.mjs"'), encoding="utf-8")
    shutil.copytree(root / "collector" / "limit_rings", out / "collector" / "limit_rings", ignore=_ignore)
    shutil.copy2(root / "collector" / "run.py", out / "collector" / "run.py")
    (out / "collector" / "limit_rings" / "version.py").write_text(version_py(version(root)), encoding="utf-8")
    catalog = catalog_json(root / "po" / "plasmoid" / "de.po")
    (out / "lib" / "de.json").write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (out / "run.sh").chmod(0o755)
    return out


def build_archive(dest: Path, root: Path = ROOT) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        tree = build_tree(Path(tmp) / WIDGET, root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as zf:
            for path in sorted(p for p in tree.rglob("*") if p.is_file() and p.name != MARKER):
                info = zipfile.ZipInfo(f"{WIDGET}/{path.relative_to(tree).as_posix()}", ZIP_DATE)
                info.external_attr = (0o755 if path.name == "run.sh" else 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Limit Rings widget for Übersicht (macOS).")
    parser.add_argument("--out", default="dist", help="directory for the zip")
    parser.add_argument("--dir", help="build the unpacked widget folder as DIR/limit-rings.widget instead")
    args = parser.parse_args(argv)
    if args.dir:
        Path(args.dir).mkdir(parents=True, exist_ok=True)
        print(build_tree(Path(args.dir) / WIDGET))
    else:
        print(build_archive(Path(args.out) / f"limit-rings-macos-{version()}.zip"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
