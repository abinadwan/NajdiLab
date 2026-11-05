"""Gold selection (V2.2.0 UX completion): review integrity stays fail-closed for the whole database; privacy is
checked for the records a build exports, and a real problem in a chosen record or its context always blocks. Reproduces the reported case on synthetic data: old corrected
reviews ignored, two eligible manual SFT records kept, and the build refused with errors about the ignored
reviews ("17 problems")."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import apply_migrations
from app.review_integrity import ExportReadinessError, export_readiness
from app.service import (ValidationError, add_manual_sft, create_export, ignore_review, ingest_turn, save_review,
                         update_manual_data)


def _turn(db, conversation, user, assistant):
    return ingest_turn({'conversation_id': conversation, 'title': 'synthetic', 'source': 'api', 'channel': 'web', 'provider': 'local',
                        'model_name': 'fixture', 'user_message': user, 'assistant_response': assistant}, db)


def _manual(db, q, a, **extra):
    return add_manual_sft({'messages': [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}],
                           'origin': 'manual', 'training_eligible': True, **extra}, db)


@pytest.fixture
def reported(tmp_path):
    """Corrected old reviews that were later ignored, plus two eligible manual SFT records and one excluded."""
    db = tmp_path / 'najdilab.db'
    apply_migrations(db)
    for i in range(3):
        review = _turn(db, f'old-{i}', f'سؤال قديم {i}', f'جواب قديم خاطئ {i}')['review_id']
        save_review(review, {'review_status': 'FULL_CORRECTION', 'corrected_response': f'تصحيح {i}', 'training_eligible': True}, db)
        ignore_review(review, {'ignored_reason': 'excluded from this dataset'}, db)
    keep = [_manual(db, 'كيف أبدأ؟', 'ابدأ بخطوة صغيرة.')['id'], _manual(db, 'Say hello.', 'Hello!')['id']]
    dropped = _manual(db, 'excluded', 'excluded answer')['id']
    update_manual_data('sft', dropped, {'exclude_from_training': True}, db)
    return db, keep, dropped


def test_ignored_old_reviews_no_longer_block_two_eligible_manual_records(reported, tmp_path):
    db, keep, _ = reported
    readiness = export_readiness(db)
    assert readiness['ok'], [f['code'] for f in readiness['blocking_findings']]
    assert {f['code'] for f in readiness['findings']} >= {'REVIEW_PRESERVED_CORRECTION_INACTIVE'}
    assert all(not f['blocking'] for f in readiness['findings'] if f['code'] == 'REVIEW_PRESERVED_CORRECTION_INACTIVE')
    export = create_export(db, tmp_path / 'exports')
    manifest = json.loads((Path(export['path']) / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['training_record_count'] == 2 and manifest['diagnostics']['version'] == manifest['version']
    rows = (Path(export['path']) / 'sft.jsonl').read_text(encoding='utf-8')
    assert 'تصحيح' not in rows and 'excluded answer' not in rows, 'ignored and excluded records never enter the version'


def test_a_real_problem_in_a_selected_context_still_blocks(tmp_path):
    # A later turn whose earlier turn was ignored: its exported context would contain ignored text.
    db = tmp_path / 'najdilab.db'
    apply_migrations(db)
    first = _turn(db, 'conv', 'أول', 'رد أول')['review_id']
    ignore_review(first, {'ignored_reason': 'private'}, db)
    second = _turn(db, 'conv', 'ثاني', 'رد ثاني')['review_id']
    save_review(second, {'review_status': 'APPROVED', 'training_eligible': True}, db)
    readiness = export_readiness(db)
    assert not readiness['ok'] and {f['code'] for f in readiness['blocking_findings']} == {'EXPORT_PRIVATE_CONTEXT'}
    with pytest.raises(ExportReadinessError):
        create_export(db, tmp_path / 'exports')
    # Leaving that record out of this build is an explicit, recorded choice; nothing is trimmed silently.
    other = _manual(db, 'q', 'a')['id']
    readiness = export_readiness(db, selection=[f'manual_sft_items:{other}'])
    assert readiness['ok'] and readiness['selection'] == [f'manual_sft_items:{other}']
    export = create_export(db, tmp_path / 'exports', selection=[f'manual_sft_items:{other}'])
    manifest = json.loads((Path(export['path']) / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['selection'] == {'mode': 'explicit', 'records': [f'manual_sft_items:{other}']}


def test_only_eligible_records_can_be_selected(reported, tmp_path):
    db, keep, dropped = reported
    for bad in ([f'manual_sft_items:{dropped}'], ['review:1'], ['manual_sft_items:999'], 'manual_sft_items:1'):
        readiness = export_readiness(db, selection=bad)
        assert not readiness['ok'] and readiness['blocking_findings'][0]['code'] == 'SELECTION_INVALID'
    with pytest.raises((ExportReadinessError, ValidationError)):
        create_export(db, tmp_path / 'exports', selection=[f'manual_sft_items:{dropped}'])
    one = create_export(db, tmp_path / 'exports', selection=[f'manual_sft_items:{keep[0]}'])
    assert json.loads((Path(one['path']) / 'manifest.json').read_text(encoding='utf-8'))['training_record_count'] == 1
