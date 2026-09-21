import json
import os
from pathlib import Path

SUPPORTED_LANGS = {"es", "en", "fr", "pt", "it", "de"}
DEFAULT_LANG = "es"
LOCALES_DIR = Path(__file__).parent.parent / "locales"


def load_translations(lang: str = None) -> dict:
    lang = (lang or os.getenv("SILO_LANG", DEFAULT_LANG)).lower().strip()
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    path = LOCALES_DIR / f"{lang}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Load once at startup
_lang = (os.getenv("SILO_LANG", DEFAULT_LANG)).lower().strip()
if _lang not in SUPPORTED_LANGS:
    _lang = DEFAULT_LANG

translations = load_translations(_lang)
