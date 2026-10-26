from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "localization.js").read_text(encoding="utf-8")
THEME = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")


def test_arabic_localization_layer_is_loaded_before_application():
    assert '<html lang="ar" dir="rtl">' in INDEX
    assert INDEX.index('/localization.js') < INDEX.index('/app.js')
    for status in ("READY", "WARNING", "BLOCKED", "NOT_CONFIGURED", "NOT_CHECKED", "RUNNING", "FAILED", "COMPLETED"):
        assert status in I18N
    assert "global.NajdiI18n" in I18N


def test_training_setup_is_arabic_first_and_keeps_technical_terms():
    for label in ("النموذج الأساسي", "إصدار البيانات", "طريقة التدريب", "معدل التعلّم", "حجم الدفعة", "فحص الجاهزية"):
        assert label in INDEX
    for technical in ("QLoRA", "LoRA", "BF16", "FP16", "VRAM"):
        assert technical in INDEX or technical in APP
    assert ">Training Setup / Preflight<" not in INDEX
    assert ">Check Runtime<" not in INDEX


def test_candidate_model_registration_is_wired_without_download_action():
    assert 'id="model-register-form"' in INDEX
    assert 'name="source_type"' in INDEX
    assert 'value="ollama"' in INDEX
    assert 'name="revision"' in INDEX
    assert "registerModelCandidate" in APP
    assert "'/api/v1/training/models'" in APP
    assert "values.repository_id=values.path" in APP
    assert "/validate`" in APP
    assert "fetch(" not in I18N
    assert "لا ينزّل أوزانًا" in INDEX


def test_accessibility_and_long_identifier_contracts():
    assert 'aria-live="polite"' in INDEX
    assert "prefers-contrast:more" in THEME
    assert "overflow-wrap:anywhere" in THEME
    assert ":focus-visible" in THEME
    assert "aria-label" in APP[APP.index("async function loadTrainingJobs"):]


def test_official_model_acquisition_is_reviewable_and_never_implicit():
    assert 'id="model-acquisition-card"' in INDEX
    assert 'التحقق وإعداد خطة التنزيل' in INDEX
    assert 'id="acquire-model"' in INDEX
    assert 'disabled>تنزيل checkpoint المعتمد والتحقق منه' in INDEX
    assert '/api/v1/training/model-acquisition/catalog' in APP
    assert '/api/v1/training/model-acquisition/prepare' in APP
    assert '/api/v1/training/model-acquisition/acquire' in APP
    assert 'gemma4-e2b-it-official' in APP
    assert 'state.modelAcquisitionApproval=data.approval_text' in APP


def test_model_or_config_change_invalidates_stale_preflight():
    assert "state.trainingPreflight=null" in APP
    assert "$('#create-training-job').disabled=true" in APP
    assert "لم يُفحص" in APP
