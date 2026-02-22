from __future__ import annotations

import json
from pathlib import Path

_LOCALES: dict[str, dict[str, str]] = {}

SUPPORTED_LANGUAGES = [
    {"code": "en", "name": "English"},
    {"code": "ru", "name": "Русский"},
]


def load_locales(locales_dir: Path | None = None) -> dict[str, dict[str, str]]:
    global _LOCALES
    if locales_dir is None:
        locales_dir = Path(__file__).resolve().parent.parent.parent / "locales"
    _LOCALES = {}
    for filepath in locales_dir.glob("*.json"):
        lang_code = filepath.stem
        with open(filepath, encoding="utf-8") as f:
            _LOCALES[lang_code] = json.load(f)
    return _LOCALES


def get_locales() -> dict[str, dict[str, str]]:
    return _LOCALES


def translate_error(error_code: str, language: str, **kwargs: object) -> str:
    locale = _LOCALES.get(language) or _LOCALES.get("en")
    if not locale:
        return error_code
    template = locale.get(error_code)
    if not template:
        return error_code
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
