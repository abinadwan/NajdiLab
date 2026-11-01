from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "localization.js").read_text(encoding="utf-8")
THEME = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")


def test_english_localization_layer_is_loaded_before_application():
    assert '<html lang="en" dir="ltr">' in INDEX
    assert INDEX.index('/localization.js') < INDEX.index('/app.js')
    for status in ("READY", "WARNING", "BLOCKED", "NOT_CONFIGURED", "NOT_CHECKED", "RUNNING", "FAILED", "COMPLETED"):
        assert status in I18N
    assert "global.NajdiI18n" in I18N



def test_dataset_first_chat_controls_are_english_and_training_controls_are_absent():
    for label in ('Connected provider','Context budget','Reserved reply tokens','New conversation','Collect future completed pairs'):
        assert label in INDEX
    assert 'id="training-setup-form"' not in INDEX
    assert 'id="model-register-form"' not in INDEX
    assert 'id="acquire-model"' not in INDEX
    assert 'startFull' not in APP


def test_accessibility_and_long_identifier_contracts():
    assert 'aria-live="polite"' in INDEX
    assert 'prefers-contrast:more' in THEME
    assert 'overflow-wrap:anywhere' in THEME
    assert ':focus-visible' in THEME
    assert 'aria-label' in APP
