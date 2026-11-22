"""QA P1 (independent review at 34284c3): the preview passed 20-30 selected manual SFT records, then the build
failed with HTTP 400 ("evaluation size is outside the target range of 10% to 15%"). Manual records have no
conversation, so no automatic hold-out could be formed. Preview and build now share one planning function, the
evaluation policy is declared, and a check is invalidated when the chosen records change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import apply_migrations
from app.service import ValidationError, add_manual_sft, create_export, prepare_check, update_manual_data


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'najdilab.db'
    apply_migrations(path)
    return path


def _manual(db, n, start=0, **extra):
    topics = ['network segmentation', 'password managers', 'phishing reports', 'data minimisation', 'refund policy', 'shipping delays',
              'summarising a memo', 'rephrasing politely', 'logic puzzles', 'unit conversion']
    return [add_manual_sft({'messages': [{'role': 'user', 'content': f'Question {i} about {topics[i % len(topics)]}, case {i // len(topics)}'},
                                         {'role': 'assistant', 'content': f'A distinct approved answer {i} on {topics[i % len(topics)]}.'}],
                            'origin': 'manual', 'training_eligible': True, 'language': 'en', **extra}, db)['id'] for i in range(start, start + n)]


@pytest.mark.parametrize('count', [1, 2, 10, 20, 30])
def test_preview_and_build_agree_for_manual_records(db, tmp_path, count):
    ids = [f'manual_sft_items:{i}' for i in _manual(db, count)]
    check = prepare_check(ids, db)
    assert check['status'] == 'ready', check['readiness']['blocking_findings']
    assert check['summary']['evaluation_policy'] == 'training_only' and check['summary']['evaluation'] == 0
    export = create_export(db, tmp_path / 'exports', selection=ids, expected_fingerprint=check['fingerprint'])
    manifest = json.loads((Path(export['path']) / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['training_record_count'] == check['summary']['training'] == count
    assert manifest['evaluation_split']['evaluation_policy'] == 'training_only'


def test_records_marked_evaluation_only_are_held_out_by_both(db, tmp_path):
    train = [f'manual_sft_items:{i}' for i in _manual(db, 20)]
    held = [f'manual_sft_items:{i}' for i in _manual(db, 3, start=1000, training_eligible=False, evaluation_only=True)]
    check = prepare_check(train + held, db)
    assert check['status'] == 'ready' and check['summary']['evaluation'] == 3
    assert check['summary']['evaluation_policy'] == 'explicit_evaluation_only'
    export = create_export(db, tmp_path / 'exports', selection=train + held, expected_fingerprint=check['fingerprint'])
    rows = (Path(export['path']) / 'evaluation_holdout.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(rows) == 3


def test_a_check_is_invalid_once_a_chosen_record_changes(db, tmp_path):
    ids = _manual(db, 3)
    chosen = [f'manual_sft_items:{i}' for i in ids]
    check = prepare_check(chosen, db)
    update_manual_data('sft', ids[0], {'notes': 'edited after the check'}, db)
    with pytest.raises(ValidationError, match='changed after the check'):
        create_export(db, tmp_path / 'exports', selection=chosen, expected_fingerprint=check['fingerprint'])
    fresh = prepare_check(chosen, db)
    assert fresh['fingerprint'] != check['fingerprint']
    create_export(db, tmp_path / 'exports', selection=chosen, expected_fingerprint=fresh['fingerprint'])


def test_when_the_build_would_refuse_the_preview_refuses_with_the_same_reason(db, tmp_path, monkeypatch):
    import app.service as service
    ids = [f'manual_sft_items:{i}' for i in _manual(db, 4)]

    def refuse(*args, **kwargs):
        raise ValidationError('Export failed: synthetic build rule')
    monkeypatch.setattr(service, '_validate_export_records', refuse)
    check = prepare_check(ids, db)
    assert check['status'] == 'needs_attention' and check['fingerprint'] is None
    assert [f['reason'] for f in check['readiness']['blocking_findings']] == ['Export failed: synthetic build rule']
    with pytest.raises(ValidationError, match='synthetic build rule'):
        create_export(db, tmp_path / 'exports', selection=ids)


def _collected(db, n):
    from app.service import add_message, approve_review, create_conversation, get_conversation
    ids = []
    for i in range(n):
        cid = create_conversation({'title': f'Collected {i}', 'source': 'manual'}, db)['id']
        add_message({'conversation_id': cid, 'role': 'user', 'content': f'Collected question {i} about secure backups and restores'}, db)
        add_message({'conversation_id': cid, 'role': 'assistant', 'content': f'Collected approved answer {i}: keep one copy offline and test the restore.'}, db)
        review = [m['review_id'] for m in get_conversation(cid, db)['messages'] if m['role'] == 'assistant'][0]
        approve_review(review, {'training_eligible': True}, db)
        ids.append(f'review:{review}')
    return ids


def test_evaluation_only_records_are_the_evaluation_set_even_with_collected_conversations(db, tmp_path):
    """Acceptance run (80 records): ten "evaluation only" records plus collected conversations were refused, because
    the automatic hold-out still forced three whole conversations into evaluation and pushed it past 15%."""
    train = [f'manual_sft_items:{i}' for i in _manual(db, 60)] + _collected(db, 10)
    held = [f'manual_sft_items:{i}' for i in _manual(db, 10, start=1000, training_eligible=False, evaluation_only=True)]
    check = prepare_check(train + held, db)
    assert check['status'] == 'ready', check['readiness']['blocking_findings']
    assert check['summary']['evaluation_policy'] == 'explicit_evaluation_only'
    assert check['summary']['evaluation'] == 10 and check['summary']['training'] == 70
    export = create_export(db, tmp_path / 'exports', selection=train + held, expected_fingerprint=check['fingerprint'])
    held_ids = {json.loads(line)['id'] for line in (Path(export['path']) / 'evaluation_holdout.jsonl').read_text(encoding='utf-8').splitlines()}
    assert held_ids == set(held), 'no collected conversation is moved into evaluation behind the user'


def test_without_evaluation_only_records_the_automatic_hold_out_keeps_its_rules(db, tmp_path):
    ids = [f'manual_sft_items:{i}' for i in _manual(db, 20)] + _collected(db, 10)
    check = prepare_check(ids, db)
    assert check['status'] == 'ready', check['readiness']['blocking_findings']
    assert check['summary']['evaluation_policy'] == 'automatic_holdout'
    assert check['summary']['evaluation_conversations'] >= 3 and 3 <= check['summary']['evaluation'] <= 5


def test_an_explicit_evaluation_share_outside_ten_to_fifteen_percent_is_explained_not_blocked(db):
    train = [f'manual_sft_items:{i}' for i in _manual(db, 20)]
    held = [f'manual_sft_items:{i}' for i in _manual(db, 1, start=1000, training_eligible=False, evaluation_only=True)]
    check = prepare_check(train + held, db)
    assert check['status'] == 'ready' and 'under 10%' in check['summary']['evaluation_note']


def test_an_evaluation_answer_that_is_also_a_training_answer_is_refused_on_that_record(db, tmp_path):
    """Acceptance run: an "evaluation only" record with the same answer as a training record reached both sides of
    the Gold version (train/eval leakage by content; present at 34284c3). Manual records have no conversation, so
    conversation isolation alone cannot catch it."""
    train = [f'manual_sft_items:{i}' for i in _manual(db, 5)]
    copy = add_manual_sft({'messages': [{'role': 'user', 'content': 'A rephrased question about network segmentation'},
                                        {'role': 'assistant', 'content': '  a DISTINCT approved answer 0 on network segmentation. '}],
                           'origin': 'manual', 'training_eligible': False, 'evaluation_only': True}, db)['id']
    held = f'manual_sft_items:{copy}'
    check = prepare_check(train + [held], db)
    assert check['status'] == 'needs_attention' and check['fingerprint'] is None
    assert [(f['code'], f['sample_id']) for f in check['readiness']['blocking_findings']] == [('EVALUATION_DUPLICATES_ANOTHER_RECORD', held)]
    with pytest.raises(ValidationError, match='same answer'):
        create_export(db, tmp_path / 'exports', selection=train + [held])
    assert prepare_check(train, db)['status'] == 'ready', 'leaving the evaluation record out resolves it'


def test_a_few_evaluation_only_records_are_topped_up_by_conversation(db, tmp_path):
    """Below the lower bound, the user's evaluation records are kept and whole conversations are added, as before."""
    train = _collected(db, 24)
    held = [f'manual_sft_items:{i}' for i in _manual(db, 1, start=1000, training_eligible=False, evaluation_only=True)]
    check = prepare_check(train + held, db)
    assert check['status'] == 'ready', check['readiness']['blocking_findings']
    assert check['summary']['evaluation_policy'] == 'explicit_plus_automatic'
    assert check['summary']['evaluation_conversations'] >= 3 and 3 <= check['summary']['evaluation'] <= 4
    export = create_export(db, tmp_path / 'exports', selection=train + held, expected_fingerprint=check['fingerprint'])
    rows = (Path(export['path']) / 'evaluation_holdout.jsonl').read_text(encoding='utf-8')
    assert held[0] in rows
