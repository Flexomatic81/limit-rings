"""tools/build_plasmoid.py: one package for the store and for install.sh, built without gettext or zip."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import build_plasmoid as bp

ID = bp.PLUGIN_ID


@pytest.fixture
def tree(tmp_path):
    return bp.build_tree(tmp_path / ID, "store")


def test_package_contains_widget_collector_and_translations(tree):
    for rel in ("metadata.json", "contents/ui/main.qml", "contents/code/format.js",
                "contents/collector/run.py", "contents/collector/limit_rings/widget.py",
                f"contents/locale/de/LC_MESSAGES/plasma_applet_{ID}.mo",
                "contents/locale/de/LC_MESSAGES/limit-rings.mo"):
        assert (tree / rel).is_file(), rel
    assert not list(tree.rglob("__pycache__")) and not list(tree.rglob("*.pyc"))


def test_build_js_tells_where_the_package_came_from(tmp_path):
    ver = bp.version()
    store = (bp.build_tree(tmp_path / "s", "store") / "contents/code/build.js").read_text()
    git = (bp.build_tree(tmp_path / "g", "git", "/src/limit rings") / "contents/code/build.js").read_text()
    assert 'const installSource = "store"' in store and f'const version = "{ver}"' in store
    assert f'const storeId = "{bp.STORE_ID}"' in store
    assert 'const installSource = "git"' in git and 'const repoDir = "/src/limit rings"' in git


def test_repo_holds_the_dev_defaults():
    committed = bp.ROOT / "plasmoid" / ID / "contents/code/build.js"
    assert committed.read_text() == bp.build_js("dev")


def test_git_build_needs_the_repo_dir(tmp_path):
    with pytest.raises(ValueError, match="repo-dir"):
        bp.build_tree(tmp_path / ID, "git")


def test_archive_has_metadata_at_the_root_and_is_reproducible(tmp_path):
    a = bp.build_archive(tmp_path / "a.plasmoid", "store")
    b = bp.build_archive(tmp_path / "b.plasmoid", "store")
    assert a.read_bytes() == b.read_bytes()
    names = zipfile.ZipFile(a).namelist()
    assert "metadata.json" in names and "contents/collector/run.py" in names


def test_packaged_collector_speaks_german_from_the_package_locale(tree):
    code = "from limit_rings.i18n import _; print(_('5-hour limit'))"
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(tree / "contents/collector"),
           "LANGUAGE": "de", "LANG": "de_DE.UTF-8"}
    # cwd outside the checkout: "-c" puts the cwd first on sys.path, which would shadow the packaged limit_rings
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=tree, capture_output=True, text=True,
                         check=True).stdout
    assert out.strip() == "5-h-Limit"


def test_cli_builds_without_gettext_or_zip(tmp_path):
    env = {"PATH": str(tmp_path / "empty"), "HOME": str(tmp_path)}   # no msgfmt, no zip on PATH
    subprocess.run([sys.executable, str(bp.ROOT / "tools/build_plasmoid.py"), "--source", "store",
                    "--out", str(tmp_path / "dist")], env=env, check=True, capture_output=True)
    assert (tmp_path / "dist" / f"limit-rings-{bp.version()}.plasmoid").is_file()
