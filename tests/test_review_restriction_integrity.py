"""Review integrity regressions: real service/HTTP, disposable SQLite only."""
from contextlib import contextmanager, ExitStack
from functools import partial
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

import pytest

from app import server, service
from tests.http_client import urlopen
from tests.test_review_management import fixture_db, add_pending

FLAGS = ('exclude_from_training', 'evaluation_only', 'contains_sensitive_data',
         'contains_personal_data', 'needs_fact_check')


def seed(db, suffix='restricted', flags=None):
    rid = add_pending(db, suffix)
    values = flags or (1, 1, 1, 1, 1)
    with sqlite3.connect(db) as conn:
        for table in ('conversations', 'messages', 'reviews'):
            conn.execute(f"UPDATE {table} SET created_at='2026-11-01T09:00:00.000000Z'")
        conn.execute("UPDATE reviews SET updated_at='2026-11-01T09:00:00.000000Z' WHERE id=?", (rid,))
        conn.execute('UPDATE reviews SET '+','.join(f'{k}=?' for k in FLAGS)+
                     ',review_notes=? WHERE id=?', (*values, 'Saved synthetic note', rid))
        conn.execute('INSERT INTO review_tags VALUES(?,?)', (rid, 'dialect_issue'))
    return rid


def decision(db, rid, action, extra=None):
    data = dict(extra or {})
    if action == 'correct':
        data.update(review_status='CONTENT_CORRECTION', corrected_response='تصحيح اصطناعي')
    return getattr(service, action+'_review')(rid, data, db)


@pytest.mark.parametrize('action', ['approve', 'correct'])
def test_omitted_restrictions_and_tags_are_preserved(tmp_path, action):
    db = fixture_db(tmp_path)
    rid = seed(db)
    result = decision(db, rid, action)
    assert tuple(result[k] for k in FLAGS) == (1, 1, 1, 1, 1)
    assert result['tags'] == ['dialect_issue']
    assert result['review_notes'] == 'Saved synthetic note'
    assert result['training_eligible'] == 0
    assert result['original_response'] == 'الأصل restricted'


@pytest.mark.parametrize('action', ['approve', 'correct'])
def test_approval_or_correction_does_not_grant_eligibility(tmp_path, action):
    db = fixture_db(tmp_path)
    rid = add_pending(db, 'unrestricted')
    assert decision(db, rid, action)['training_eligible'] == 0


@pytest.mark.parametrize('flag', FLAGS)
def test_each_restriction_blocks_requested_eligibility(tmp_path, flag):
    db = fixture_db(tmp_path)
    rid = seed(db, flags=tuple(int(k == flag) for k in FLAGS))
    result = decision(db, rid, 'approve', {'training_eligible': True})
    assert result[flag] == 1
    assert result['training_eligible'] == 0
    assert service.training_dataset(db)['reviews'] == []


def test_explicit_changes_are_distinct_from_absence(tmp_path):
    db = fixture_db(tmp_path)
    rid = seed(db)
    result = decision(db, rid, 'approve', {'contains_personal_data': False, 'tags': []})
    assert result['contains_personal_data'] == 0
    assert result['contains_sensitive_data'] == 1
    assert result['tags'] == []
    clean = add_pending(db, 'explicit-eligible')
    assert decision(db, clean, 'approve', {'training_eligible': True})['training_eligible'] == 1


@pytest.mark.parametrize('extra', [{'contains_sensitive_data': None}, {'evaluation_only': 'false'},
                                  {'training_eligible': 2}, {'tags': None}, {'tags': 'other'}])
def test_invalid_changes_fail_without_mutation(tmp_path, extra):
    db = fixture_db(tmp_path)
    rid = seed(db)
    before = service.get_review(rid, db)
    with pytest.raises(service.ValidationError):
        decision(db, rid, 'approve', extra)
    assert service.get_review(rid, db) == before


@pytest.mark.parametrize('bulk', [False, True])
def test_restore_preserves_restrictions_corrections_and_reason_without_events(tmp_path, bulk):
    db = fixture_db(tmp_path)
    rid = seed(db)
    decision(db, rid, 'correct')
    service.exclude_review(rid, {'reason': 'Synthetic exclusion'}, db)
    data = {'reason': 'Human requested another review', 'training_eligible': True,
            'exclude_from_training': False, 'evaluation_only': False}
    if bulk:
        result = service.bulk_review_actions({**data, 'action': 'restore', 'review_ids': [rid]}, db)['items'][0]
    else:
        result = service.restore_review(rid, data, db)
    assert result['review_status'] == 'PENDING'
    assert result['training_eligible'] == 0
    assert tuple(result[k] for k in FLAGS) == (1, 1, 1, 1, 1)
    assert result['tags'] == ['dialect_issue']
    assert result['corrected_response'] == 'تصحيح اصطناعي'
    assert result['original_response'] == 'الأصل restricted'
    assert result['ignored_at'] is None and result['deleted_at'] is None
    assert result['ignored_reason'] == data['reason']


def test_bulk_restore_mixed_flags_and_failure_are_atomic(tmp_path):
    db = fixture_db(tmp_path, events=True)
    ids = [seed(db, str(i), flags) for i, flags in enumerate([(1,0,1,0,0), (0,1,0,1,1)])]
    for rid in ids:
        decision(db, rid, 'correct')
        service.delete_review(rid, {'reason': 'Synthetic soft delete'}, db)
    before = [service.get_review(rid, db) for rid in ids]
    with sqlite3.connect(db) as conn:
        events = conn.execute('SELECT * FROM review_events ORDER BY id').fetchall()
    with pytest.raises(service.ValidationError):
        service.bulk_review_actions({'action':'restore','review_ids':[*ids,999999],'reason':'Restore'}, db)
    assert [service.get_review(rid, db) for rid in ids] == before
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM review_events ORDER BY id').fetchall() == events
    result = service.bulk_review_actions({'action':'restore','review_ids':ids,'reason':'Restore'}, db)
    assert [tuple(r[k] for k in FLAGS) for r in result['items']] == [(1,0,1,0,0), (0,1,0,1,1)]
    with sqlite3.connect(db) as conn:
        after = conn.execute('SELECT * FROM review_events ORDER BY id').fetchall()
        assert after[:len(events)] == events
        assert conn.execute("SELECT COUNT(*) FROM review_events WHERE to_status='PENDING' AND reason='Restore'").fetchone()[0] == 2


@pytest.mark.parametrize('bulk', [False, True])
def test_restore_requires_reason(tmp_path, bulk):
    db = fixture_db(tmp_path)
    rid = seed(db)
    service.exclude_review(rid, {'reason':'Synthetic'}, db)
    before = service.get_review(rid, db)
    with pytest.raises(service.ValidationError):
        if bulk:
            service.bulk_review_actions({'action':'restore','review_ids':[rid]}, db)
        else:
            service.restore_review(rid, {}, db)
    assert service.get_review(rid, db) == before


def test_restoration_reason_survives_subsequent_review_without_event_table(tmp_path):
    db = fixture_db(tmp_path)
    rid = seed(db)
    service.exclude_review(rid, {'reason':'Excluded for re-review'}, db)
    service.restore_review(rid, {'reason':'Explicit human restoration'}, db)
    result = decision(db, rid, 'correct')
    assert result['ignored_reason'] == 'Explicit human restoration'


@contextmanager
def fixture_server(db):
    names = ('approve_review','correct_review','save_review','restore_review','bulk_review_actions',
             'exclude_review','delete_review','list_review_queue','list_reviewed')
    with ExitStack() as stack:
        for name in names:
            stack.enter_context(patch.object(server, name, partial(getattr(service, name), db_path=db)))
        http = server.NajdiLabHTTPServer(('127.0.0.1',0), server.NajdiLabHandler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{http.server_port}'
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=5)


def post(base, path, payload):
    request = Request(base+'/api/v1/'+path, data=json.dumps(payload).encode(),
                      headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


@pytest.mark.parametrize('action', ['approve','correct','restore','bulk'])
def test_http_actions_preserve_flags_and_reject_stale_revision(tmp_path, action):
    db = fixture_db(tmp_path)
    rid = seed(db)
    if action in ('restore','bulk'):
        service.exclude_review(rid, {'reason':'Synthetic'}, db)
    before = service.get_review(rid, db)
    payload = {'expected_updated_at':before['updated_at']}
    if action == 'correct':
        payload.update(review_status='DIALECT_CORRECTION', corrected_response='تصحيح API')
    if action in ('restore','bulk'):
        payload['reason'] = 'Restore via API'
    path = f'reviews/{rid}/{action}'
    if action == 'bulk':
        path = 'reviews/bulk'
        payload.update(action='restore', review_ids=[rid], expected_updated_at_by_id={str(rid):before['updated_at']})
    with fixture_server(db) as base:
        result = post(base, path, payload)
        saved = result['items'][0] if action == 'bulk' else result['review']
        assert tuple(saved[k] for k in FLAGS) == (1,1,1,1,1)
        assert saved['tags'] == ['dialect_issue'] and saved['training_eligible'] == 0
        with pytest.raises(HTTPError) as error:
            post(base, path, payload)
        assert error.value.code in (400,409)
    assert service.get_review(rid, db) == saved


def test_existing_export_bytes_and_original_message_survive_decisions(tmp_path):
    db = fixture_db(tmp_path)
    turn = service.ingest_turn({'conversation_id':'synthetic-export','source':'test','channel':'test',
                                'user_message':'سؤال اصطناعي','assistant_response':'رد أصلي اصطناعي'}, db)
    rid = turn['review_id']
    decision(db, rid, 'approve', {'training_eligible':True})
    exports = tmp_path/'exports'
    service.create_export(db, exports)
    before = {str(p.relative_to(exports)):p.read_bytes() for p in exports.rglob('*') if p.is_file()}
    decision(db, rid, 'correct', {'contains_personal_data':True})
    service.exclude_review(rid, {'reason':'Synthetic privacy review'}, db)
    service.restore_review(rid, {'reason':'Re-review'}, db)
    assert {str(p.relative_to(exports)):p.read_bytes() for p in exports.rglob('*') if p.is_file()} == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT content FROM messages WHERE role='assistant'").fetchone()[0] == 'رد أصلي اصطناعي'
    assert service.get_review(rid, db)['original_response'] == 'رد أصلي اصطناعي'


def test_bulk_stale_revision_rolls_back_earlier_restoration(tmp_path):
    db = fixture_db(tmp_path, events=True)
    ids = [seed(db, str(i)) for i in range(2)]
    for rid in ids:
        service.exclude_review(rid, {'reason':'Synthetic'}, db)
    before = [service.get_review(rid, db) for rid in ids]
    with pytest.raises(service.ValidationError):
        service.bulk_review_actions({'action':'restore', 'review_ids':ids, 'reason':'Re-review',
            'expected_updated_at_by_id':{str(ids[0]):before[0]['updated_at'], str(ids[1]):'stale'}}, db)
    assert [service.get_review(rid, db) for rid in ids] == before


def test_two_concurrent_decisions_accept_only_one_revision(tmp_path):
    db = fixture_db(tmp_path)
    rid = seed(db)
    revision = service.get_review(rid, db)['updated_at']
    barrier = threading.Barrier(2)
    outcomes = []
    def write(action):
        barrier.wait(timeout=5)
        try:
            decision(db, rid, action, {'expected_updated_at':revision})
            outcomes.append('saved')
        except service.ValidationError:
            outcomes.append('stale')
    workers = [threading.Thread(target=write, args=(action,)) for action in ('approve','correct')]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert sorted(outcomes) == ['saved','stale']
    assert tuple(service.get_review(rid, db)[k] for k in FLAGS) == (1,1,1,1,1)


def test_revision_advances_even_when_clock_repeats(tmp_path):
    db = fixture_db(tmp_path)
    rid = seed(db)
    repeated = '2026-11-01T09:00:00.000000Z'
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE reviews SET updated_at=? WHERE id=?', (repeated,rid))
    with patch.object(service, 'utc_now', return_value=repeated):
        result = decision(db, rid, 'approve', {'expected_updated_at':repeated})
        assert result['updated_at'] != repeated
        with pytest.raises(service.ValidationError):
            decision(db, rid, 'correct', {'expected_updated_at':repeated})


@pytest.mark.parametrize('action', ['approve','correct'])
def test_bulk_decisions_preserve_per_record_eligibility(tmp_path, action):
    db = fixture_db(tmp_path)
    ids = [add_pending(db, str(i)) for i in range(2)]
    payload = {'action':action, 'review_ids':ids}
    if action == 'correct':
        payload.update(review_status='FULL_CORRECTION', corrected_response='تصحيح جماعي')
    result = service.bulk_review_actions(payload, db)
    assert [r['training_eligible'] for r in result['items']] == [0,0]


def browser_main():
    with tempfile.TemporaryDirectory(prefix='najdilab-review-browser-') as temp:
        db = fixture_db(Path(temp))
        for i in range(5):
            seed(db, str(i))
        with fixture_server(db) as base:
            print('REVIEW_FIXTURE='+base, flush=True)
            threading.Event().wait()


if __name__ == '__main__':
    browser_main()
