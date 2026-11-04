"""Gold diagnostics lifecycle and separated readiness states (V2.2.0 P0).

The first gold version used to be published Frozen without diagnostics; Dataset Health then reported
"diagnostics have not been generated", and regeneration is (correctly) refused for Frozen versions, so the
only way out was a derived copy. New versions now carry diagnostics from creation; older Frozen versions are
diagnosed read-only from their hash-verified files and are never modified.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import dataset_platform as platform
from app.db import apply_migrations
from app.service import add_manual_sft, create_export


def _sft(db, question, answer):
    add_manual_sft({'messages': [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer}],
                    'language_layer': 'msa', 'origin': 'manual', 'training_eligible': True}, db)


@pytest.fixture
def gold(tmp_path, monkeypatch):
    db = tmp_path / 'najdilab.db'
    apply_migrations(db)
    for i in range(3):
        _sft(db, f'سؤال {i}', f'جواب معتمد {i}')
    exports = tmp_path / 'exports'
    export = create_export(db, exports)
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    return Path(export['path']), export


def _snapshot(directory):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def test_first_gold_version_has_current_diagnostics_without_a_derived_copy(gold):
    directory, export = gold
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['state'] == 'Frozen'
    assert manifest['diagnostics']['version'] == manifest['version']
    assert set(manifest['diagnostics']['artifacts']) == {'loss-mask-validation.json', 'balancing_report.json'}
    assert all(manifest['sha256'][n] == manifest['diagnostics']['artifacts'][n] for n in manifest['diagnostics']['artifacts']), 'hashed like data files'
    before = _snapshot(directory)
    health = platform.dataset_health(manifest['version'])
    assert health['diagnostics'] == {**health['diagnostics'], 'valid': True, 'error': None, 'source': 'stored'}
    assert not [w for w in health['warnings'] if w['code'] == 'stale_diagnostics']
    assert health['training_readiness']['status'] == 'READY'
    assert health['loss_mask_validation']['passed'] == health['loss_mask_validation']['total'] == health['training_count']
    assert _snapshot(directory) == before, 'reading health never writes a frozen version'


def test_readiness_states_are_separate_and_no_evaluation_data_is_never_evaluation_ready(gold):
    directory, export = gold
    version = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['version']
    readiness = platform.dataset_health(version)['readiness']
    assert readiness['structural']['status'] == 'VALID'
    assert readiness['training_compatibility']['status'] == 'STRUCTURE_CHECKED'
    assert 'not verified by NajdiLab' in readiness['training_compatibility']['token_level']
    if readiness['evaluation']['samples'] == 0:
        assert readiness['evaluation']['status'] == 'NO_EVALUATION_DATA'
    for name in platform.EVAL_FILES:
        (directory / name).unlink(missing_ok=True)
    health = platform.dataset_health(version)
    assert health['readiness']['evaluation'] == {**health['readiness']['evaluation'], 'status': 'NO_EVALUATION_DATA', 'samples': 0}
    assert any(w['code'] == 'no_evaluation_data' for w in health['warnings'])
    assert health['readiness']['structural']['status'] == 'VALID', 'a trainable version can still lack evaluation data'


def _legacy(directory):
    """Rewrite the version as a pre-V2.2.0 export: Frozen, no stored diagnostics."""
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    manifest.pop('diagnostics'); manifest.pop('loss_mask_validation')
    for name in ('loss-mask-validation.json', 'balancing_report.json'):
        (directory / name).unlink()
        manifest['sha256'].pop(name)
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    return manifest['version']


def test_legacy_frozen_version_is_diagnosed_read_only(gold):
    directory, _ = gold
    version = _legacy(directory)
    before = _snapshot(directory)
    health = platform.dataset_health(version)
    assert (health['diagnostics']['valid'], health['diagnostics']['source']) == (True, 'computed_on_read')
    assert health['training_readiness']['status'] == 'READY'
    assert health['loss_mask_validation']['passed'] == health['training_count'] > 0
    assert health['conversation_count'] == 3
    assert _snapshot(directory) == before, 'no file is added to or changed in the frozen version'


def test_legacy_frozen_version_with_changed_files_is_not_diagnosed(gold):
    directory, _ = gold
    version = _legacy(directory)
    sft = directory / 'sft.jsonl'
    sft.write_text(sft.read_text(encoding='utf-8').replace('جواب معتمد 0', 'جواب مُبدّل'), encoding='utf-8')
    health = platform.dataset_health(version)
    assert health['diagnostics']['valid'] is False and 'manifest hashes' in health['diagnostics']['error']
    assert health['training_readiness']['status'] == 'NOT_READY'
    assert health['readiness']['structural']['status'] == 'INVALID'


def test_stored_diagnostics_that_no_longer_match_stay_an_error(gold):
    directory, _ = gold
    version = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['version']
    sft = directory / 'sft.jsonl'
    sft.write_text(sft.read_text(encoding='utf-8').replace('جواب معتمد 1', 'جواب آخر'), encoding='utf-8')
    health = platform.dataset_health(version)
    assert health['diagnostics']['valid'] is False and 'stale' in health['diagnostics']['error']
    assert any(w['code'] == 'stale_diagnostics' for w in health['warnings'])
    assert health['readiness']['structural']['status'] == 'INVALID'
