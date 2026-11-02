"""Chat Experience V2 on synthetic data only: migration 008, session metadata,
archive/restore, permanent deletion, streaming, thinking, completion checks and
segment collection. No installed engine, model or user database is used."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

import app.db as appdb
from app.chat_history import saved_sessions_page, suggest_title
from app.chat_workspace import ChatWorkspace, completion_check
from app.db import apply_migrations, connect
from app.integrations import IntegrationError, IntegrationManager
from app.service import create_export, ingest_turn, save_review

from test_chat_workspace import Engine

SECRET = 'نص-اصطناعي-سري-' + uuid4().hex
REPLY = 'رد-اصطناعي-' + uuid4().hex


class StreamEngine(Engine):
    """Streams thinking, then the answer in parts; never claims extra content."""
    thinking = ['أفكر ', 'بصمت']
    parts = ['هلا', ' ', 'والله']
    stop_after = None

    def generate(self, messages, reserve, stop, on_delta=None):
        self.calls.append(('generate', messages, reserve))
        if self.started:
            self.started.set()
            self.release.wait(3)
        if on_delta:
            for text in self.thinking:
                on_delta('thinking', text)
            for index, text in enumerate(self.parts):
                if self.stop_after is not None and index == self.stop_after:
                    stop.set()
                    raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                on_delta('content', text)
        return {'content': ''.join(self.parts), 'stop_reason': self.reason, 'input_tokens': self.seen,
                'output_tokens': 3, 'reasoning_discarded': bool(self.thinking), 'timings': {'first_token_ms': 1}}


@pytest.fixture
def chat(tmp_path):
    db = tmp_path / 'v2.db'
    apply_migrations(db)
    manager = IntegrationManager(home=tmp_path)
    manager._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', models=['fixture'], selection_revision=2)
    engine = StreamEngine()
    roots = [tmp_path / 'exports', tmp_path / 'datasets']
    ws = ChatWorkspace(manager, db, engine_factory=engine.open, artifact_roots=roots, backups_root=tmp_path / 'backups')
    try:
        yield ws, engine, db, tmp_path
    finally:
        ws.close()


def new(ws):
    return ws.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                      'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})


def send(ws, session, text='سؤال', **kw):
    return ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                   'selection_revision': 2, 'text': text}, **kw)


def rows(db, sql, *args):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, args).fetchall()


# --------------------------------------------------------------------- migration
def _db_at_007(tmp_path, monkeypatch):
    old = tmp_path / 'migrations-007'
    old.mkdir()
    registry = json.loads((appdb.MIGRATIONS_DIR / 'registry.json').read_text(encoding='utf-8'))
    registry['migrations'] = [m for m in registry['migrations'] if m['name'] <= '007_review_events.sql']
    for entry in registry['migrations']:
        shutil.copy2(appdb.MIGRATIONS_DIR / entry['name'], old / entry['name'])
    (old / 'registry.json').write_text(json.dumps(registry), encoding='utf-8')
    real = appdb.MIGRATIONS_DIR
    monkeypatch.setattr(appdb, 'MIGRATIONS_DIR', old)
    db = tmp_path / 'legacy.db'
    apply_migrations(db)
    monkeypatch.setattr(appdb, 'MIGRATIONS_DIR', real)
    return db


def test_migration_008_is_lossless_on_a_pre_v2_database(tmp_path, monkeypatch):
    db = _db_at_007(tmp_path, monkeypatch)
    with sqlite3.connect(db) as conn:
        assert 'native' not in conn.execute("SELECT sql FROM sqlite_master WHERE name='chat_sessions'").fetchone()[0]
        for sid, status, rev in (('a' * 8 + '-0000-4000-8000-' + '0' * 12, 'OPEN', 3),
                                 ('b' * 8 + '-0000-4000-8000-' + '0' * 12, 'ARCHIVED', 5),
                                 ('c' * 8 + '-0000-4000-8000-' + '0' * 12, 'CONTEXT_LIMIT', 7)):
            conn.execute("INSERT INTO chat_sessions VALUES(?,?,?,?,?,?,?,?,?)",
                         (sid, 'ollama', 'm', 4096, 512, status, rev, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'))
            conn.execute("INSERT INTO chat_session_bindings VALUES(?,1,'ollama:x')", (sid,))
            conn.execute("INSERT INTO chat_requests VALUES(?,?,?,?,?)", (sid, 'r1', 'h', 'COMPLETED', 'now'))
            conn.execute("INSERT INTO chat_turns VALUES(?,?,?,?,?,?,?,?,?)", (sid, 'r1', 1, SECRET, REPLY, 10, 3, None, 'now'))
        before = conn.execute('SELECT id,provider,model,context_budget,reply_reserve,status,revision,created_at,updated_at FROM chat_sessions ORDER BY id').fetchall()
    apply_migrations(db)
    apply_migrations(db)  # replay is a no-op
    with sqlite3.connect(db) as conn:
        after = conn.execute('SELECT id,provider,model,context_budget,reply_reserve,status,revision,created_at,updated_at FROM chat_sessions ORDER BY id').fetchall()
        assert after == before
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0] == 3
        archived = conn.execute("SELECT archived_at, archived_from_status, title FROM chat_sessions WHERE status='ARCHIVED'").fetchone()
        assert archived == ('2026-01-02T00:00:00Z', None, None), 'no title or prior status is invented'
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='chat_archive_eligibility'").fetchone()[0] == 1
        conn.execute("INSERT INTO chat_sessions(id,provider,model,context_budget,reply_reserve,created_at,updated_at) VALUES('n','native','x',4096,512,'t','t')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO chat_sessions(id,provider,model,context_budget,reply_reserve,created_at,updated_at) VALUES('z','cloud','x',4096,512,'t','t')")


def test_legacy_archived_conversation_restores_open_and_keeps_history(tmp_path, monkeypatch):
    db = _db_at_007(tmp_path, monkeypatch)
    sid = str(uuid4())
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO chat_sessions VALUES(?,?,?,?,?,?,?,?,?)", (sid, 'lmstudio', 'fixture', 512, 32, 'ARCHIVED', 1, 't', 't'))
        conn.execute("INSERT INTO chat_requests VALUES(?,?,?,?,?)", (sid, 'r', 'h', 'COMPLETED', 'now'))
        conn.execute("INSERT INTO chat_turns VALUES(?,?,?,?,?,?,?,?,?)", (sid, 'r', 0, SECRET, REPLY, 10, 3, None, 'now'))
    apply_migrations(db)
    manager = IntegrationManager(home=tmp_path)
    ws = ChatWorkspace(manager, db, engine_factory=Engine().open, artifact_roots=[], backups_root=None)
    try:
        assert saved_sessions_page(db, 10, 0, archived=True)[0][0]['display_title'] == suggest_title(SECRET)
        restored = ws.restore(sid, {'revision': 1})
        assert restored['status'] == 'OPEN' and restored['turns'][0]['user'] == SECRET
    finally:
        ws.close()


# ------------------------------------------------------------- titles and lists
def test_auto_title_rename_pin_search_and_activity_order(chat):
    ws, _, db, _ = chat
    first, second = new(ws), new(ws)
    assert first['title'] is None and first['display_title'] is None
    first = send(ws, first, text='## كيف أطبخ **كبسة** دجاج؟\nبالتفصيل')['session']
    assert first['title'] == 'كيف أطبخ كبسة دجاج؟' and first['title_source'] == 'auto'
    second = send(ws, second, text='second topic')['session']
    items, _ = saved_sessions_page(db, 10, 0)
    assert [i['id'] for i in items] == [second['id'], first['id']], 'most recent activity first'
    ws.pin(first['id'], {'pinned': True})
    assert saved_sessions_page(db, 10, 0)[0][0]['id'] == first['id'], 'pinned first'
    renamed = ws.rename(first['id'], {'title': '  عشاء   الجمعة '})
    assert renamed['title'] == 'عشاء الجمعة' and renamed['title_source'] == 'manual'
    assert renamed['revision'] == first['revision'], 'metadata never stales the send revision'
    assert ws.rename(first['id'], {'title': None})['title_source'] == 'auto'
    assert [i['id'] for i in saved_sessions_page(db, 10, 0, query='كبسة')[0]] == [first['id']]
    assert [i['id'] for i in saved_sessions_page(db, 10, 0, query='%')[0]] == [], 'LIKE wildcards are literal'
    for bad in ('', '   ', 'x' * 121, 5):
        with pytest.raises(IntegrationError):
            ws.rename(first['id'], {'title': bad})
    with pytest.raises(IntegrationError):
        ws.pin(first['id'], {'pinned': 'yes'})


def test_archive_restore_returns_prior_status_and_keeps_pairs_excluded(chat):
    ws, engine, db, _ = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    session = send(ws, session)['session']
    archived = ws.archive(session['id'], {'revision': session['revision']})
    assert archived['status'] == 'ARCHIVED' and archived['archived_from_status'] == 'OPEN'
    assert saved_sessions_page(db, 10, 0)[1] == 0 and saved_sessions_page(db, 10, 0, archived=True)[1] == 1
    with pytest.raises(IntegrationError) as again:
        ws.archive(session['id'], {'revision': archived['revision']})
    assert again.value.code == 'ALREADY_ARCHIVED'
    restored = ws.restore(session['id'], {'revision': archived['revision']})
    assert restored['status'] == 'OPEN' and restored['archived_at'] is None and restored['collect'] is False
    assert rows(db, 'SELECT training_eligible, exclude_from_training FROM reviews') == [(0, 1)]
    with pytest.raises(IntegrationError) as wrong:
        ws.restore(session['id'], {'revision': restored['revision']})
    assert wrong.value.code == 'NOT_ARCHIVED'


# ------------------------------------------------------------ permanent delete
def _collected(ws):
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    return send(ws, session, text=SECRET)['session']


def _raw(db):
    data = db.read_bytes()
    wal = db.with_name(db.name + '-wal')
    return data + (wal.read_bytes() if wal.exists() else b'')


def test_delete_requires_exact_confirmation_and_current_revision(chat):
    ws, _, db, _ = chat
    session = send(ws, new(ws), text=SECRET)['session']
    for confirm in ('delete', '', 'yes', None):
        with pytest.raises(IntegrationError) as error:
            ws.delete(session['id'], {'revision': session['revision'], 'confirm': confirm})
        assert error.value.code == 'DELETE_CONFIRMATION_REQUIRED'
    with pytest.raises(IntegrationError) as stale:
        ws.delete(session['id'], {'revision': session['revision'] - 1, 'confirm': 'DELETE'})
    assert stale.value.code == 'STALE_CHAT'
    assert rows(db, 'SELECT COUNT(*) FROM chat_turns') == [(1,)], 'archive or refusal never deletes'


def test_delete_removes_chat_and_uncollected_review_copies_everywhere_in_the_db(chat):
    ws, _, db, tmp = chat
    session = _collected(ws)
    keep = send(ws, new(ws), text='يبقى')['session']
    assert SECRET.encode() in _raw(db)
    preview = ws.delete_preview(session['id'])
    assert preview['turns'] == 1 and preview['review_conversations'] == 1 and preview['blocked'] is None
    result = ws.delete(session['id'], {'revision': preview['revision'], 'confirm': 'DELETE'})
    assert result['review_conversations_deleted'] == 1 and result['wal_checkpoint'] == 'TRUNCATED'
    for table in ('chat_sessions', 'chat_turns', 'chat_requests', 'chat_session_bindings'):
        assert rows(db, f'SELECT COUNT(*) FROM {table} WHERE {"id" if table == "chat_sessions" else "session_id"}=?', session['id']) == [(0,)]
    assert rows(db, 'SELECT COUNT(*) FROM messages WHERE content LIKE ?', '%' + SECRET + '%') == [(0,)]
    assert SECRET.encode() not in _raw(db), 'secure_delete + WAL truncate leave no readable copy in the DB files'
    assert REPLY.encode() not in _raw(db)
    tomb = rows(db, 'SELECT session_id, turns_deleted, review_conversations_deleted FROM chat_deletions')
    assert tomb == [(session['id'], 1, 1)]
    with pytest.raises(sqlite3.DatabaseError):
        rows(db, 'DELETE FROM chat_deletions')
    assert ws.get(keep['id'])['turns'][0]['user'] == 'يبقى', 'other conversations untouched'
    with pytest.raises(IntegrationError):
        ws.get(session['id'])
    other = ingest_turn({'conversation_id': 'unrelated', 'user_message': 'q', 'assistant_response': 'a'}, db)
    save_review(other['review_id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
    exported = Path(create_export(db, tmp / 'later-exports')['path'])
    assert (exported / 'full_archive.json').is_file()
    assert all(SECRET not in p.read_text(encoding='utf-8') for p in exported.iterdir() if p.is_file())


def test_reviewed_copy_is_redacted_and_only_content_free_events_remain(chat):
    ws, _, db, _ = chat
    session = _collected(ws)
    review_id = rows(db, 'SELECT id FROM reviews')[0][0]
    save_review(review_id, {'review_status': 'CONTENT_CORRECTION', 'reviewer': 'human', 'training_eligible': True,
                            'corrected_response': SECRET + ' corrected', 'review_notes': SECRET}, db)
    preview = ws.delete_preview(session['id'])
    assert preview['review_conversations_to_redact'] == 1 and preview['review_events_retained'] >= 1
    result = ws.delete(session['id'], {'revision': preview['revision'], 'confirm': 'DELETE'})
    assert result['review_conversations_redacted'] == 1
    status, original, corrected, notes, eligible = rows(db, 'SELECT review_status, original_response, corrected_response, review_notes, training_eligible FROM reviews WHERE id=?', review_id)[0]
    assert (status, original, corrected, notes, eligible) == ('DELETED', '[deleted]', None, None, 0)
    events = rows(db, 'SELECT to_status, source_sha256 FROM review_events WHERE review_id=?', review_id)
    assert events and all(len(h) == 64 for _, h in events)
    assert SECRET.encode() not in _raw(db) and REPLY.encode() not in _raw(db)
    assert rows(db, 'PRAGMA integrity_check') == [('ok',)] and rows(db, 'PRAGMA foreign_key_check') == []


def test_delete_is_refused_while_exported_and_nothing_changes(chat):
    ws, _, db, tmp = chat
    session = _collected(ws)
    (tmp / 'exports' / 'v1').mkdir(parents=True)
    (tmp / 'exports' / 'v1' / 'full_archive.json').write_text(json.dumps({'id': f"najdilab-chat:{session['id']}:x"}), encoding='utf-8')
    preview = ws.delete_preview(session['id'])
    assert preview['blocked'] == 'EXPORTED' and preview['exported_copies'] == ['exports/v1/full_archive.json']
    with pytest.raises(IntegrationError) as error:
        ws.delete(session['id'], {'revision': preview['revision'], 'confirm': 'DELETE'})
    assert error.value.code == 'DELETE_BLOCKED_EXPORTED'
    assert rows(db, 'SELECT COUNT(*) FROM chat_turns') == [(1,)] and rows(db, 'SELECT COUNT(*) FROM reviews') == [(1,)]


def test_delete_failure_mid_transaction_rolls_back_everything(chat):
    ws, _, db, _ = chat
    session = _collected(ws)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON chat_requests BEGIN SELECT RAISE(ABORT, 'fixture'); END")
    preview = ws.delete_preview(session['id'])
    with pytest.raises(sqlite3.DatabaseError):
        ws.delete(session['id'], {'revision': preview['revision'], 'confirm': 'DELETE'})
    assert rows(db, 'SELECT COUNT(*) FROM chat_turns') == [(1,)]
    assert rows(db, 'SELECT COUNT(*) FROM reviews') == [(1,)]
    assert rows(db, 'SELECT COUNT(*) FROM chat_deletions') == [(0,)]


def test_delete_is_refused_during_an_active_turn(chat):
    ws, engine, db, _ = chat
    session = new(ws)
    engine.started, engine.release = threading.Event(), threading.Event()
    worker = threading.Thread(target=send, args=(ws, session))
    worker.start()
    assert engine.started.wait(3)
    with pytest.raises(IntegrationError) as busy:
        ws.delete(session['id'], {'revision': ws.get(session['id'])['revision'], 'confirm': 'DELETE'})
    assert busy.value.code == 'CHAT_BUSY'
    engine.release.set()
    worker.join(5)
    assert rows(db, 'SELECT COUNT(*) FROM chat_sessions') == [(1,)]


def test_backups_are_counted_never_changed(chat):
    ws, _, _, tmp = chat
    session = _collected(ws)
    (tmp / 'backups').mkdir()
    backup = tmp / 'backups' / 'najdilab-backup-29991231T000000Z.zip'
    backup.write_bytes(b'synthetic')
    preview = ws.delete_preview(session['id'])
    assert preview['backups_not_changed'] == 1
    ws.delete(session['id'], {'revision': preview['revision'], 'confirm': 'DELETE'})
    assert backup.read_bytes() == b'synthetic'


# --------------------------------------------------------- streaming and checks
def test_stream_events_thinking_is_shown_never_saved(chat):
    ws, engine, db, _ = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    events = []
    result = send(ws, session, on_event=events.append)
    kinds = [e['type'] for e in events]
    assert kinds[0] == 'accepted' and 'admitted' in kinds
    phases = [e['phase'] for e in events if e['type'] == 'phase']
    assert phases == ['engine_check', 'admission', 'waiting_first_token', 'thinking', 'answering', 'verifying']
    assert ''.join(e['text'] for e in events if e['type'] == 'content') == 'هلا والله'
    assert result['session']['turns'][0]['assistant'] == 'هلا والله'
    assert set(result['timings']) >= {'engine_check_ms', 'admission_ms', 'generation_total_ms', 'verify_commit_ms'}
    raw = _raw(db)
    assert 'أفكر'.encode() not in raw and 'بصمت'.encode() not in raw, 'thinking never reaches the database'
    assert all(isinstance(v, (int, str, dict, type(None))) for v in result['timings'].values())


def test_stopped_stream_saves_nothing_and_marks_request_stopped(chat):
    ws, engine, db, _ = chat
    engine.stop_after = 1
    session = new(ws)
    events = []
    with pytest.raises(IntegrationError) as error:
        send(ws, session, on_event=events.append)
    assert error.value.code == 'STOPPED'
    assert [e['text'] for e in events if e['type'] == 'content'] == ['هلا']
    assert rows(db, 'SELECT COUNT(*) FROM chat_turns') == [(0,)]
    assert rows(db, 'SELECT status FROM chat_requests') == [('STOPPED',)]
    assert rows(db, 'SELECT COUNT(*) FROM reviews') == [(0,)]


@pytest.mark.parametrize('result,check', [
    ({'stop_reason': 'length', 'content': 'x', 'input_tokens': 10}, 'STOP_REASON_LENGTH'),
    ({'stop_reason': 'maxPredictedTokensReached', 'content': 'x', 'input_tokens': 10}, 'STOP_REASON_LENGTH'),
    ({'stop_reason': 'weird', 'content': 'x', 'input_tokens': 10}, 'STOP_REASON_OTHER'),
    ({'stop_reason': 'stop', 'content': '  \n', 'input_tokens': 10}, 'EMPTY_CONTENT'),
    ({'stop_reason': 'stop', 'content': 'x', 'input_tokens': 9}, 'PROMPT_TOKENS_MISMATCH'),
    ({'stop_reason': 'stop', 'content': 'x', 'input_tokens': None}, 'PROMPT_TOKENS_MISMATCH'),
    ({'stop_reason': 'stop', 'content': 'x', 'input_tokens': 10, 'tool_calls': [{}]}, 'TOOL_CALLS'),
    ({'stop_reason': 'stop', 'content': 'x', 'input_tokens': 10}, None),
])
def test_completion_check_names_the_failed_predicate(result, check):
    assert completion_check(result, 10, 3, 512) == check
    assert completion_check({'stop_reason': 'stop', 'content': 'x', 'input_tokens': 10}, 10, 600, 512) == 'OVER_BUDGET'


def test_length_stop_reports_reserve_and_thinking_and_saves_nothing(chat):
    ws, engine, db, _ = chat
    engine.reason = 'length'
    with pytest.raises(IntegrationError) as error:
        send(ws, new(ws))
    assert error.value.code == 'INCOMPLETE_RESPONSE' and error.value.check == 'STOP_REASON_LENGTH'
    assert str(error.value).startswith('Engine did not return an unchanged, complete text reply; no pair was saved.')
    assert 'Thinking tokens count' in str(error.value)
    assert rows(db, 'SELECT COUNT(*) FROM chat_turns') == [(0,)]


# ------------------------------------------------------------ segment collection
def test_collection_is_off_by_default_and_segments_link_turns(chat):
    ws, _, db, _ = chat
    session = new(ws)
    assert session['collect'] is False
    session = send(ws, session, text='قبل الموافقة')['session']
    assert rows(db, 'SELECT COUNT(*) FROM reviews') == [(0,)], 'nothing is collected retroactively'
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    session = send(ws, session, text='أول')['session']
    session = send(ws, session, text='ثاني')['session']
    meta = [json.loads(m) for (m,) in rows(db, "SELECT c.metadata_json FROM conversations c")]
    assert len(meta) == 1
    messages = rows(db, "SELECT role, content, parent_message_id, metadata_json FROM messages ORDER BY turn_index")
    assert [m[1] for m in messages if m[0] == 'user'] == ['أول', 'ثاني'], 'only consented turns'
    assistants = [json.loads(m[3]) for m in messages if m[0] == 'assistant']
    assert [a['collection_mode'] for a in assistants] == ['single_turn', 'multi_turn']
    assert [a['segment_turn'] for a in assistants] == [1, 2]
    assert all(a['depends_on_excluded_context'] and a['earlier_turns_excluded'] == 1 for a in assistants)
    assert all(a['thinking_collected'] is False for a in assistants)
    assert all(s == 'PENDING' for (s,) in rows(db, 'SELECT review_status FROM reviews')), 'never auto-approved'
    session = ws.collect(session['id'], {'enabled': False, 'revision': session['revision']})
    send(ws, session, text='بعد الإيقاف')
    assert rows(db, 'SELECT COUNT(*) FROM reviews') == [(2,)]


def test_segment_export_keeps_single_and_multi_turn_shapes_and_no_unconsented_context(chat):
    ws, engine, db, tmp = chat
    answers = iter(['جواب اصطناعي أول مختلف', 'جواب اصطناعي ثانٍ مختلف', 'جواب اصطناعي ثالث مختلف'])
    original = engine.generate

    def distinct(*args, **kwargs):
        result = original(*args, **kwargs)
        result['content'] = next(answers)
        return result
    engine.generate = distinct
    session = send(ws, new(ws), text='قبل الموافقة سري')['session']
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    session = send(ws, session, text='سؤال أول بعد الموافقة')['session']
    send(ws, session, text='سؤال ثانٍ بعد الموافقة')
    for (review_id,) in rows(db, 'SELECT id FROM reviews'):
        save_review(review_id, {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
    out = Path(create_export(db, tmp / 'exports')['path'])
    single = [json.loads(line) for line in (out / 'sft.jsonl').read_text(encoding='utf-8').splitlines()]
    multi = [json.loads(line) for line in (out / 'multi_turn.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [[m['content'] for m in r['messages']] for r in single] == [['سؤال أول بعد الموافقة', 'جواب اصطناعي ثانٍ مختلف']]
    assert [[m['role'] for m in r['messages']] for r in multi] == [['user', 'assistant', 'user', 'assistant']]
    assert multi[0]['messages'][0]['content'] == 'سؤال أول بعد الموافقة'
    for path in out.iterdir():
        if path.is_file():
            assert 'قبل الموافقة سري' not in path.read_text(encoding='utf-8'), f'unconsented text leaked into {path.name}'
