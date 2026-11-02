from pathlib import Path

from tests.test_english_localization import run_browser_script

ROOT = Path(__file__).resolve().parents[1]


def test_current_navigation_has_chat_without_training_execution_controls():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    assert 'data-view="chat"' in html
    for marker in ('data-view="training"', 'id="training-setup-form"', 'id="acquire-model"',
                   'id="view-retired"', 'id="view-human-review"', 'id="phase3-filter"',
                   'id="phase3-blind"'):
        assert marker not in html
    for marker in ('startFull', 'loadPhase3Review', 'function renderPhase3(', 'renderPhase3=', 'phase3Filtered',
                   '/api/v1/phase3/', '/evaluation/human-review', '/training/',
                   '/api/v1/training-dataset', '/api/v1/training-data/'):
        assert marker not in js
    assert 'id="chat-collect"' in html and 'id="chat-stop"' in html
    # Chat V2 wording of the raw-chat disclosure (empty state and settings drawer).
    assert 'NajdiLab adds no system prompt, tools, retrieval or memory' in html
    assert 'no system or developer prompt from NajdiLab' in html


def test_dataset_forms_keep_persistent_flags_and_use_dataset_api_names():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    assert 'id="training-eligible"' in html
    assert 'id="exclude-training"' in html
    assert 'name="training_eligible"' in html
    for marker in ('training_eligible:', 'exclude_from_training:', '/api/v1/dataset-records',
                   '/api/v1/manual-data/sft', '/api/v1/manual-data/direct', '/api/v1/manual-data/preference'):
        assert marker in js
    for marker in ('Dataset records', 'Dataset eligible', 'Exclude from dataset selection'):
        assert marker in html
    for marker in ('Training data', 'Training eligible', 'Exclude from training'):
        assert marker not in html and marker not in js
    assert 'id="unsloth-create"' in html


def test_no_retired_comparison_or_training_styles_remain():
    css = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'static').glob('*.css'))
    for marker in ('.phase3-', '.training-', '.jobs-layout', '.job-status', '.execution-readiness',
                   '.model-register-panel', '.future-metrics', '.dry-run-result'):
        assert marker not in css
    assert '.gate-badge.blocked' in css  # Dataset remediation still uses these badges.


def test_only_dataset_remediation_review_routes_remain_registered():
    run_browser_script(r"""
const routes = vm.runInContext('({...pathViews})', context);
assert.equal(routes['/evaluation/remediation-review'], 'phase38-review');
assert.equal(routes['/evaluation/remediation-review-edits'], 'phase39-review');
for (const path of ['/training/setup', '/training/jobs', '/training/retired', '/evaluation/human-review']) {
    assert.equal(routes[path], undefined);
}
assert.equal(vm.runInContext('typeof loadPhase3Review', context), 'undefined');
assert.equal(vm.runInContext('typeof loadPhase38Review', context), 'function');
assert.equal(vm.runInContext('typeof loadPhase39Verification', context), 'function');
""")
