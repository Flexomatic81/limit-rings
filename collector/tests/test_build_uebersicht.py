"""tools/build_uebersicht.py: the macOS widget folder and its zip, built with the standard library only."""

import json
import zipfile

import build_uebersicht as bu
import pytest
from build_plasmoid import ROOT


def test_catalog_json_has_contexts_and_plural_forms():
    cat = bu.catalog_json(ROOT / "po" / "plasmoid" / "de.po")
    assert cat["limit name: weekly window\u0004Week"] == "Woche"
    forms = cat["%1 file unreadable – numbers incomplete"]
    assert forms == ["%1 Datei nicht lesbar – Zahlen unvollständig", "%1 Dateien nicht lesbar – Zahlen unvollständig"]
    assert "" not in cat


def test_tree_has_widget_core_collector_and_catalog(tmp_path):
    tree = bu.build_tree(tmp_path / bu.WIDGET)
    for rel in ("index.jsx", "lib/card.mjs", "lib/i18n.mjs", "run.sh", "lib/core.mjs", "lib/de.json",
                "collector/run.py", "collector/limit_rings/widget.py", "collector/limit_rings/sources/keychain.py"):
        assert (tree / rel).is_file(), rel
    assert not list(tree.rglob("__pycache__"))
    assert json.loads((tree / "lib" / "de.json").read_text(encoding="utf-8"))["limit name: weekly window\u0004Week"] == "Woche"
    assert f'VERSION = "{bu.version()}"' in (tree / "collector/limit_rings/version.py").read_text()
    assert (tree / "run.sh").stat().st_mode & 0o111
    card = (tree / "lib" / "card.mjs").read_text(encoding="utf-8")
    widgets = [p.relative_to(tree).as_posix() for p in tree.rglob("*")
               if p.suffix in (".js", ".jsx", ".coffee") and "lib" not in p.relative_to(tree).parts]
    assert widgets == ["index.jsx"]   # exactly one widget for Übersicht
    assert 'from "./core.mjs"' in card and "plasmoid/" not in card


def test_never_builds_into_the_sources_or_over_foreign_folders(tmp_path):
    source = ROOT / "macos" / bu.WIDGET
    before = sorted(p.name for p in source.iterdir())
    for target in (source, ROOT / "macos", ROOT):
        with pytest.raises(ValueError):
            bu.build_tree(target)
    assert sorted(p.name for p in source.iterdir()) == before
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "index.jsx").write_text("keep")
    with pytest.raises(ValueError):
        bu.build_tree(foreign)
    assert (foreign / "index.jsx").read_text() == "keep"
    bu.build_tree(tmp_path / "out")
    bu.build_tree(tmp_path / "out")   # an earlier build is replaced


def test_archive_has_the_folder_at_the_root_and_is_reproducible(tmp_path):
    a = bu.build_archive(tmp_path / "a.zip")
    b = bu.build_archive(tmp_path / "b.zip")
    assert a.read_bytes() == b.read_bytes()
    with zipfile.ZipFile(a) as zf:
        names = zf.namelist()
        assert "limit-rings.widget/index.jsx" in names and all(n.startswith("limit-rings.widget/") for n in names)
        assert (zf.getinfo("limit-rings.widget/run.sh").external_attr >> 16) & 0o777 == 0o755


def test_cli_names_the_zip_by_version(tmp_path):
    assert bu.main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / f"limit-rings-macos-{bu.version()}.zip").is_file()
