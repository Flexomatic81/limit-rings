import pytest

import release_notes as rn

CHANGELOG = "# Changelog\n\n## 0.3.0\n\n- New thing.\n- Other thing.\n\n## 0.2.0\n\n- Old thing.\n"


def test_section_of_a_version():
    assert rn.changelog_section(CHANGELOG, "0.3.0") == "- New thing.\n- Other thing.\n"
    assert rn.changelog_section(CHANGELOG, "0.2.0") == "- Old thing.\n"


def test_missing_or_empty_section_is_an_error():
    with pytest.raises(ValueError, match="0.4.0"):
        rn.changelog_section(CHANGELOG, "0.4.0")
    with pytest.raises(ValueError):
        rn.changelog_section("## 0.3.0\n\n## 0.2.0\n- x\n", "0.3.0")


def test_prefix_versions_do_not_match():
    with pytest.raises(ValueError):
        rn.changelog_section("## 0.3.10\n\n- x\n", "0.3.1")


def test_tag_must_match_the_metadata_version():
    rn.check_tag("v0.3.0", "0.3.0")
    with pytest.raises(ValueError, match="v0.3.1"):
        rn.check_tag("v0.3.1", "0.3.0")


def test_the_repository_changelog_covers_the_current_version():
    from build_plasmoid import ROOT, version
    assert rn.changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version())
