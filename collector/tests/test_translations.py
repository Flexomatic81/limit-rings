"""The translation catalogs are complete, compile and keep the placeholders of the source texts."""

import gettext
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from limit_rings import i18n
from limit_rings.notify import update_notices

ROOT = Path(__file__).resolve().parents[2]
PO = ROOT / "po"
TOOLS = ("xgettext", "msgfmt", "msgcmp", "msgmerge")
pytestmark = pytest.mark.skipif(not all(shutil.which(t) for t in TOOLS), reason="gettext tools missing")

CATALOGS = sorted(PO.glob("*/*.po"))
PLACEHOLDER = re.compile(r"%\d|%\(\w+\)[sd]")


@pytest.fixture(scope="module")
def templates(tmp_path_factory):
    out = tmp_path_factory.mktemp("pot")
    subprocess.run([str(PO / "update.sh"), "--extract", str(out)], check=True)
    return out


def _compile(po: Path, mo: Path) -> Path:
    mo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["msgfmt", "--check-format", "-o", str(mo), str(po)], check=True)
    return mo


def test_plasmoid_template_marks_kde_format_strings(templates):
    # with KDE format flags, msgfmt --check-format also checks the %1 placeholders of the widget
    assert "#, kde-format" in (templates / "plasmoid.pot").read_text()


def test_there_is_a_german_catalog_for_both_parts():
    assert {p.relative_to(PO).as_posix() for p in CATALOGS} >= {"plasmoid/de.po", "collector/de.po"}


@pytest.mark.parametrize("po", CATALOGS, ids=lambda p: p.relative_to(PO).as_posix())
def test_catalog_covers_every_source_text(po, templates):
    # msgcmp treats untranslated and fuzzy entries as missing
    result = subprocess.run(["msgcmp", str(po), str(templates / f"{po.parent.name}.pot")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("po", CATALOGS, ids=lambda p: p.relative_to(PO).as_posix())
def test_translations_keep_placeholders(po, tmp_path):
    with _compile(po, tmp_path / "x.mo").open("rb") as f:
        catalog = gettext.GNUTranslations(f)._catalog
    for key, translated in catalog.items():
        if key == "":
            continue
        source = (key[0] if isinstance(key, tuple) else key).split("\x04")[-1]
        expected = set(PLACEHOLDER.findall(source))
        assert set(PLACEHOLDER.findall(translated)) <= expected | {"%1"}, (source, translated)
        if not isinstance(key, tuple) or key[1] > 0:
            assert set(PLACEHOLDER.findall(translated)) == expected, (source, translated)


def test_german_notifications(tmp_path):
    _compile(PO / "collector" / "de.po", tmp_path / "de" / "LC_MESSAGES" / "limit-rings.mo")
    i18n.install(["de"], tmp_path)
    now = 1_791_100_000.0
    five = {"id": "five_hour", "used_percent": 82.0, "resets_at": int(now) + 4380, "window_minutes": 300}
    opus = {"id": "seven_day_opus", "used_percent": 96.0, "resets_at": None, "window_minutes": 10080,
            "model": "Opus"}
    notices = update_notices({"Claude": [five, opus]}, {}, now)
    assert [(n.summary, n.body) for n in notices] == [
        ("Claude: 5-h-Limit bei 82 %", "Reset in 1 h 13 min"),
        ("Claude: Wochenlimit Opus bei 96 %", "")]


def test_german_early_warnings(tmp_path):
    _compile(PO / "collector" / "de.po", tmp_path / "de" / "LC_MESSAGES" / "limit-rings.mo")
    i18n.install(["de"], tmp_path)
    now = 1_791_100_000.0

    def five(eta):
        return {"id": "five_hour", "used_percent": 62.0, "resets_at": int(now) + 4380, "window_minutes": 300,
                "forecast": {"status": "full", "eta": eta}}

    soon = update_notices({"Claude": [five(now + 25 * 60)]}, {}, now)
    assert [(n.summary, n.body) for n in soon] == [
        ("Claude: 5-h-Limit in ~25 min voll", "Jetzt 62 % · Reset in 1 h 13 min")]
    reached = update_notices({"Claude": [five(now - 60)]}, {}, now)
    assert [n.summary for n in reached] == ["Claude: 5-h-Limit gleich voll"]
