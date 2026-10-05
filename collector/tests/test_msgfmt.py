"""tools/msgfmt.py compiles the catalogs like GNU msgfmt, so that no gettext is needed to install."""

import gettext
import shutil
import subprocess
from pathlib import Path

import pytest

import msgfmt

ROOT = Path(__file__).resolve().parents[2]
HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'


def load(tmp_path: Path, po_text: str) -> gettext.GNUTranslations:
    po = tmp_path / "x.po"
    po.write_text(po_text, encoding="utf-8")
    mo = tmp_path / "out" / "x.mo"
    msgfmt.compile_file(po, mo)
    with mo.open("rb") as f:
        return gettext.GNUTranslations(f)


def test_context_plural_and_multiline_strings(tmp_path):
    t = load(tmp_path, HEADER + (
        'msgctxt "time ago"\nmsgid "%1 h ago"\nmsgstr "vor %1 h"\n\n'
        'msgid "%1 file"\nmsgid_plural "%1 files"\nmsgstr[0] "%1 Datei"\nmsgstr[1] "%1 Dateien"\n\n'
        'msgid ""\n"Long "\n"text"\nmsgstr ""\n"Langer "\n"Text"\n'))
    assert t.pgettext("time ago", "%1 h ago") == "vor %1 h"
    assert t.ngettext("%1 file", "%1 files", 1) == "%1 Datei"
    assert t.ngettext("%1 file", "%1 files", 5) == "%1 Dateien"
    assert t.gettext("Long text") == "Langer Text"


def test_escapes_and_umlauts(tmp_path):
    t = load(tmp_path, HEADER + 'msgid "a\\tb \\"q\\" \\\\ c\\n"\nmsgstr "ä\\tö \\"q\\" \\\\ ü\\n"\n')
    assert t.gettext('a\tb "q" \\ c\n') == 'ä\tö "q" \\ ü\n'


def test_fuzzy_obsolete_and_untranslated_entries_are_left_out(tmp_path):
    t = load(tmp_path, HEADER + (
        '#, kde-format, fuzzy\nmsgid "Fuzzy"\nmsgstr "Unsicher"\n\n'
        'msgid "Empty"\nmsgstr ""\n\n'
        '#~ msgid "Old"\n#~ msgstr "Alt"\n\n'
        '#, kde-format\nmsgid "Kept"\nmsgstr "Bleibt"\n'))
    assert t.gettext("Fuzzy") == "Fuzzy"
    assert t.gettext("Empty") == "Empty"
    assert t.gettext("Old") == "Old"
    assert t.gettext("Kept") == "Bleibt"


def test_non_utf8_catalog_is_rejected(tmp_path):
    with pytest.raises(msgfmt.PoError, match="UTF-8"):
        load(tmp_path, HEADER.replace("UTF-8", "ISO-8859-1") + 'msgid "a"\nmsgstr "b"\n')


def test_unknown_keyword_names_the_line(tmp_path):
    with pytest.raises(msgfmt.PoError, match="line 7"):
        load(tmp_path, HEADER + 'msgid "a"\nmsgstrx "b"\n')


@pytest.mark.skipif(not shutil.which("msgfmt"), reason="gettext missing")
@pytest.mark.parametrize("po", sorted((ROOT / "po").glob("*/*.po")), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_same_catalog_as_gnu_msgfmt(po, tmp_path):
    gnu = tmp_path / "gnu.mo"
    subprocess.run(["msgfmt", "-o", str(gnu), str(po)], check=True)
    ours = tmp_path / "ours.mo"
    msgfmt.compile_file(po, ours)
    with gnu.open("rb") as a, ours.open("rb") as b:
        gnu_t, ours_t = gettext.GNUTranslations(a), gettext.GNUTranslations(b)
    # GNU msgfmt drops POT-Creation-Date from the header; every message and the plural rule must match.
    assert {k: v for k, v in ours_t._catalog.items() if k != ""} == {k: v for k, v in gnu_t._catalog.items() if k != ""}
    assert ours_t.plural(1) == gnu_t.plural(1) and ours_t.plural(5) == gnu_t.plural(5)
