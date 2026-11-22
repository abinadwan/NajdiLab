"""Synthetic Gold health regressions for versions without conversation diagnostics."""
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app import dataset_platform as platform
from app import server
from app.db import apply_migrations
from app.service import add_direct_text, add_manual_sft, create_export, prepare_check
from app.review_integrity import ExportReadinessError


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    db = tmp_path / 'fixture.db'
    apply_migrations(db)
    exports = tmp_path / 'exports'
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    monkeypatch.setattr(platform, 'DATASETS_ROOT', tmp_path / 'datasets')
    return db, exports


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir()}


def add_direct(db, text='اااا بببب تتتت'):
    return add_direct_text({'text': text, 'source_type': 'human_written',
                            'language': 'ar', 'training_eligible': True}, db)


def add_sft(db, number=0, *, multi=False, evaluation=False):
    messages = [{'role': 'user', 'content': f'Question about synthetic topic {number}'},
                {'role': 'assistant', 'content': f'Approved answer for case {number}'}]
    if multi:
        messages += [{'role': 'user', 'content': f'Follow-up for case {number}'},
                     {'role': 'assistant', 'content': f'Final approved answer for case {number}'}]
    return add_manual_sft({'messages': messages, 'language': 'en',
                           'training_eligible': not evaluation, 'evaluation_only': evaluation}, db)


@pytest.fixture
def http_base(workspace):
    # These GET routes need only the temporary catalog. No runtime manager is constructed.
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    assert http.server_port not in {8770, 8870, 8871}
    thread = threading.Thread(target=http.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}'
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)


def read_routes(base, version, status=200):
    results = {}
    for suffix in ('/health', '/balance', ''):
        try:
            response = urlopen(f'{base}/api/v1/dataset-versions/{version}{suffix}', timeout=10)
        except HTTPError as error:
            response = error
        with response:
            body = json.load(response)
            assert response.status == status, (suffix, response.status, body)
            results[suffix] = body
    return results


def test_direct_only_gold_health_preserves_unavailable_conversation_statistics(workspace):
    db, exports = workspace
    add_direct(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    health = platform.dataset_health(export['version'])
    assert health['conversation_count'] == 0
    for field in ('highest_record_share', 'highest_context_word_share', 'highest_target_word_share'):
        assert health[field] is None
    assert not {'conversation_concentration', 'context_concentration'} & {w['code'] for w in health['warnings']}
    assert health['readiness']['evaluation']['status'] == 'NO_EVALUATION_DATA'
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize('case', ['direct_one', 'direct_two', 'single_sft', 'multi_sft', 'mixed',
                                  'direct_and_evaluation', 'evaluation_only', 'concentrated'])
def test_supported_gold_compositions_work_through_all_three_http_routes(workspace, http_base, case):
    db, exports = workspace
    if case in {'direct_one', 'direct_two', 'mixed', 'direct_and_evaluation'}:
        add_direct(db)
    if case == 'direct_two':
        add_direct(db, 'ثثثث جججج حححح')
    if case in {'single_sft', 'multi_sft', 'mixed'}:
        add_sft(db, multi=case == 'multi_sft')
    if case in {'direct_and_evaluation', 'evaluation_only'}:
        add_sft(db, evaluation=True)
    if case == 'concentrated':
        for number in range(3):
            add_sft(db, number)
    export = create_export(db, exports)
    directory = Path(export['path'])
    before = snapshot(directory)
    responses = read_routes(http_base, export['version'])
    health = responses['/health']
    codes = {w['code'] for w in health['warnings']}
    has_conversations = case in {'single_sft', 'multi_sft', 'mixed', 'concentrated'}
    assert ('conversation_concentration' in codes) == has_conversations
    assert ('context_concentration' in codes) == has_conversations
    if has_conversations:
        assert health['highest_record_share'][1]['record_share'] > .15
    else:
        assert health['highest_record_share'] is None
        assert health['highest_context_word_share'] is None
    assert health['evaluation_integrity']['status'] == 'CLEAN'
    manifest = responses['']['manifest']
    hashes = {item['name']: item['sha256'] for item in responses['']['files']}
    for name, digest in manifest['sha256'].items():
        assert hashes[name] == digest
    assert snapshot(directory) == before


def test_empty_selection_is_rejected_before_a_gold_version_is_published(workspace):
    db, exports = workspace
    assert prepare_check([], db)['status'] != 'ready'
    with pytest.raises(ExportReadinessError) as caught:
        create_export(db, exports)
    assert any(f['code'] == 'NO_EXPORTABLE_DATA' for f in caught.value.readiness['blocking_findings'])
    assert not list(exports.glob('gold-*'))


def replace_balance_fixture(directory, value):
    """Construct synthetic historical/corrupt diagnostics before taking the read-only snapshot."""
    path = directory / 'balancing_report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    report['conversation_balance'] = value
    replace_report_fixture(directory, report)


def replace_report_fixture(directory, report):
    path = directory / 'balancing_report.json'
    path.write_text(json.dumps(report), encoding='utf-8')
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    digest = platform._sha256(path)
    manifest['sha256'][path.name] = digest
    manifest['diagnostics']['artifacts'][path.name] = digest
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')


@pytest.mark.parametrize('balance', [None, {}, {'conversation_count': None},
    {'highest_record_share': None, 'highest_context_word_share': None, 'highest_target_word_share': None},
    {'highest_record_share': ['c', {}], 'highest_context_word_share': ['c', {'context_word_share': None}]}])
def test_missing_or_null_statistics_stay_unavailable(workspace, http_base, balance):
    db, exports = workspace
    add_direct(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    replace_balance_fixture(directory, balance)
    before = snapshot(directory)
    health = read_routes(http_base, export['version'])['/health']
    assert health['highest_record_share'] is None
    assert health['highest_context_word_share'] is None
    assert health['highest_target_word_share'] is None
    assert not {'conversation_concentration', 'context_concentration'} & {w['code'] for w in health['warnings']}
    assert snapshot(directory) == before


@pytest.mark.parametrize('report', [None, [], 'invalid'])
def test_malformed_balance_report_remains_a_validation_error_in_balancer(workspace, http_base, report):
    db, exports = workspace
    add_direct(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    replace_report_fixture(directory, report)
    before = snapshot(directory)
    responses = read_routes(http_base, export['version'], status=422)
    assert all(result['code'] == 'INVALID_MANIFEST' for result in responses.values())
    assert snapshot(directory) == before


@pytest.mark.parametrize('balance', [[], 'invalid', {'conversation_count': 'many'},
    {'highest_record_share': []}, {'highest_record_share': ['c', None]},
    {'highest_record_share': ['c', {'record_share': '0.8'}]},
    {'highest_record_share': ['c', {'record_share': True}]},
    {'highest_record_share': ['c', {'record_share': -1}]},
    {'highest_record_share': ['c', {'record_share': float('nan')}]},
    {'highest_record_share': ['c', {'record_share': 10 ** 1000}]},
    {'highest_context_word_share': ['c', {'context_word_share': 2}]},
    {'highest_target_word_share': ['c', {'target_word_share': float('inf')}]}])
def test_malformed_statistics_are_explicit_validation_errors_on_all_routes(workspace, http_base, balance):
    db, exports = workspace
    add_direct(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    replace_balance_fixture(directory, balance)
    before = snapshot(directory)
    responses = read_routes(http_base, export['version'], status=422)
    assert all(result['code'] == 'INVALID_DIAGNOSTICS' for result in responses.values())
    assert snapshot(directory) == before


@pytest.mark.parametrize(('record_share', 'context_share', 'warn'), [(0, 0, False), (.15, .30, False), (.1501, .3001, True)])
def test_concentration_thresholds_and_measured_zero_keep_their_meaning(workspace, http_base, record_share, context_share, warn):
    db, exports = workspace
    add_sft(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    replace_balance_fixture(directory, {'conversation_count': 1,
        'highest_record_share': ['source', {'record_share': record_share}],
        'highest_context_word_share': ['source', {'context_word_share': context_share}]})
    health = read_routes(http_base, export['version'])['/health']
    codes = {w['code'] for w in health['warnings']}
    assert ('conversation_concentration' in codes) == warn
    assert ('context_concentration' in codes) == warn
    assert health['highest_record_share'][1]['record_share'] == record_share


def test_legacy_direct_only_gold_is_diagnosed_without_writing_frozen_files(workspace, http_base):
    db, exports = workspace
    add_direct(db)
    export = create_export(db, exports)
    directory = Path(export['path'])
    path = directory / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest.pop('diagnostics')
    manifest.pop('loss_mask_validation')
    path.write_text(json.dumps(manifest), encoding='utf-8')
    before = snapshot(directory)
    health = read_routes(http_base, export['version'])['/health']
    assert health['diagnostics']['source'] == 'computed_on_read'
    assert health['highest_record_share'] is None
    assert snapshot(directory) == before
