from __future__ import annotations

import gettext
from pathlib import Path


DOMAIN = "android-camera-fetcher"
LOCALE_DIR = Path(__file__).with_name("locales")
_translation: gettext.NullTranslations = gettext.NullTranslations()


def configure(language: str) -> None:
    global _translation
    _translation = gettext.translation(DOMAIN, LOCALE_DIR, languages=[language], fallback=True)


def _(message: str) -> str:
    return _translation.gettext(message)
