"""Translations of user-facing collector texts (desktop notifications), following the system language."""

import gettext
from pathlib import Path

DOMAIN = "agent-stats"
LOCALEDIR = Path(__file__).resolve().parent / "locale"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def install(languages: list[str] | None = None, localedir: Path = LOCALEDIR) -> None:
    """Load the catalog for languages (None: LANGUAGE, LC_ALL, LC_MESSAGES, LANG); English if none fits."""
    global _translation
    _translation = gettext.translation(DOMAIN, localedir, languages=languages, fallback=True)


def _(message: str) -> str:
    return _translation.gettext(message)


install()
