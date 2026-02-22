import json
import tempfile
from pathlib import Path

from aimg.common.i18n import load_locales, translate_error


def test_load_locales_from_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {
            "UNAUTHORIZED": "Invalid key",
            "INSUFFICIENT_CREDITS": "Need {required}, have {available}",
        }
        ru = {
            "UNAUTHORIZED": "Неверный ключ",
            "INSUFFICIENT_CREDITS": "Нужно {required}, есть {available}",
        }
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        (Path(tmpdir) / "ru.json").write_text(json.dumps(ru))

        result = load_locales(Path(tmpdir))
        assert "en" in result
        assert "ru" in result
        assert result["en"]["UNAUTHORIZED"] == "Invalid key"


def test_translate_error_en():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {"INSUFFICIENT_CREDITS": "Need {required}, have {available}"}
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        load_locales(Path(tmpdir))

        msg = translate_error("INSUFFICIENT_CREDITS", "en", required=5, available=0)
        assert msg == "Need 5, have 0"


def test_translate_error_ru():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {"INSUFFICIENT_CREDITS": "Need {required}, have {available}"}
        ru = {"INSUFFICIENT_CREDITS": "Нужно {required}, есть {available}"}
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        (Path(tmpdir) / "ru.json").write_text(json.dumps(ru))
        load_locales(Path(tmpdir))

        msg = translate_error("INSUFFICIENT_CREDITS", "ru", required=5, available=0)
        assert msg == "Нужно 5, есть 0"


def test_translate_error_fallback_to_en():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {"UNAUTHORIZED": "Invalid key"}
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        load_locales(Path(tmpdir))

        msg = translate_error("UNAUTHORIZED", "fr")
        assert msg == "Invalid key"


def test_translate_error_missing_key():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {"UNAUTHORIZED": "Invalid key"}
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        load_locales(Path(tmpdir))

        msg = translate_error("NONEXISTENT_CODE", "en")
        assert msg == "NONEXISTENT_CODE"


def test_translate_error_missing_placeholder_graceful():
    with tempfile.TemporaryDirectory() as tmpdir:
        en = {"INSUFFICIENT_CREDITS": "Need {required}, have {available}"}
        (Path(tmpdir) / "en.json").write_text(json.dumps(en))
        load_locales(Path(tmpdir))

        # Missing kwargs → returns template as-is
        msg = translate_error("INSUFFICIENT_CREDITS", "en")
        assert msg == "Need {required}, have {available}"
