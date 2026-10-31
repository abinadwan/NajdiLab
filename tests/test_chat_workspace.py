"""Synthetic chat state/transaction tests. No installed engine or user database."""
from contextlib import contextmanager
import sqlite3
import threading
from uuid import uuid4

import pytest

from app.db import apply_migrations, connect
from app.integrations import IntegrationManager, IntegrationError
from app.chat_workspace import ChatWorkspace


class Engine:
    count = 10
    ceiling = 4096
    content = '  هلا\n🙂  '
    reason = 'eosFound'
    fail = False
    started = None
    release = None

    def __init__(self):
        self.calls = []

    @contextmanager
    def open(self, spec, model):
        yield self

    def measure(self, messages):
        self.calls.append(('measure', messages))
        return {'input_tokens': self.count, 'loaded_context': self.ceiling, 'model_key': 'fixture'}

    def generate(self, messages, reserve, stop):
        self.calls.append(('generate', messages, reserve))
        if self.started:
            self.started.set()
            self.release.wait(3)
        if self.fail:
            raise IntegrationError('ENGINE_FAILED', 'Synthetic engine error', 502)
        return {'content': self.content, 'stop_reason': self.reason,
                'input_tokens': self.count, 'output_tokens': 3}


@pytest.fixture
def chat(tmp_path):
    db = tmp_path / 'own.db'
    apply_migrations(db)
    manager = IntegrationManager(home=tmp_path)
    manager._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', models=['fixture'], selection_revision=2)
    engine = Engine()
    workspace = ChatWorkspace(manager, db, engine_factory=engine.open)
    try:
        yield workspace, engine, manager, db
    finally:
        workspace.close()


def new(ws, **extra):
    return ws.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                      'context_budget': 512, 'reply_reserve': 32, **extra})


def send(ws, session, **extra):
    return ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                  'selection_revision': 2, 'text': '  سؤال\n🙂  ', **extra})


def count(db, table):
    with connect(db) as conn:
        return conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]


def test_raw_history_saved_without_collection_and_reused_exactly(chat):
    ws, engine, _, db = chat
    session = new(ws)
    assert session['collect'] is False
    result = send(ws, session)
    assert result['session']['turns'][0]['user'] == '  سؤال\n🙂  '
    assert result['session']['turns'][0]['assistant'] == engine.content
    assert count(db, 'reviews') == 0
    send(ws, result['session'], text='التالي')
    history = engine.calls[-1][1]
    assert [m['role'] for m in history] == ['user', 'assistant', 'user']
    assert history[0]['content'] == '  سؤال\n🙂  '
    assert history[1]['content'] == engine.content


def test_collection_pending_provenance_dedup_and_atomicity(chat):
    ws, _, _, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    request_id = str(uuid4())
    result = send(ws, session, request_id=request_id)
    again = send(ws, session, request_id=request_id)
    assert again['duplicate'] is True
    assert count(db, 'chat_turns') == count(db, 'reviews') == 1
    with connect(db) as conn:
        r = conn.execute('SELECT * FROM reviews').fetchone()
        assert r['review_status'] == 'PENDING' and r['training_eligible'] == 0
        assert r['original_response'] == '  هلا\n🙂  '
        m = conn.execute("SELECT * FROM messages WHERE role='assistant'").fetchone()
        assert 'najdilab_chat' in m['metadata_json']
        assert request_id in m['source_message_id']
    with pytest.raises(IntegrationError):
        send(ws, session, request_id=request_id, text='different payload')
    # Failure after receipt reservation must roll back the entire pair/review.
    with connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_turn BEFORE INSERT ON chat_turns BEGIN SELECT RAISE(ABORT, 'fixture'); END")
    with pytest.raises(sqlite3.Error):
        send(ws, result['session'])
    assert count(db, 'reviews') == count(db, 'chat_turns') == 1


@pytest.mark.parametrize('count_value,allowed', [(480, True), (481, False)])
def test_boundary_reserves_reply_and_rolls_over_without_inference(chat, count_value, allowed):
    ws, engine, _, db = chat
    session = new(ws)
    engine.count = count_value
    result = send(ws, session)
    if allowed:
        assert result['status'] == 'COMPLETED'
    else:
        assert result['status'] == 'CONTEXT_LIMIT'
        assert result['session']['status'] == 'CONTEXT_LIMIT'
        assert result['new_session']['turns'] == [] and not result['new_session']['collect']
        assert not any(c[0] == 'generate' for c in engine.calls)
        assert count(db, 'chat_turns') == 0


@pytest.mark.parametrize('invalid', [None, -1, True, 1.2, '10'])
def test_unknown_or_invalid_token_counts_fail_before_inference(chat, invalid):
    ws, engine, _, _ = chat
    engine.count = invalid
    with pytest.raises(IntegrationError):
        send(ws, new(ws))
    assert not any(c[0] == 'generate' for c in engine.calls)


@pytest.mark.parametrize('reason', ['maxPredictedTokensReached', 'contextLengthReached', 'userStopped', 'unknown'])
def test_partial_or_failed_completion_never_saved(chat, reason):
    ws, engine, _, db = chat
    engine.reason = reason
    with pytest.raises(IntegrationError):
        send(ws, new(ws))
    assert count(db, 'chat_turns') == count(db, 'reviews') == 0


def test_stop_and_consent_revoke_reenable_inflight_never_capture(chat):
    ws, engine, _, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    engine.started, engine.release = threading.Event(), threading.Event()
    outcomes = []
    def run():
        try:
            outcomes.append(send(ws, session))
        except IntegrationError as e:
            outcomes.append(e.code)
    t = threading.Thread(target=run)
    t.start()
    assert engine.started.wait(2)
    off = ws.collect(session['id'], {'enabled': False, 'revision': ws.get(session['id'])['revision']})
    ws.collect(session['id'], {'enabled': True, 'revision': off['revision']})
    ws.stop(session['id'])
    engine.release.set()
    t.join(4)
    assert outcomes == ['STOPPED']
    assert count(db, 'chat_turns') == count(db, 'reviews') == 0


def test_restart_collect_off_and_single_database_owner(chat):
    ws, engine, manager, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    result = send(ws, session)
    with pytest.raises(IntegrationError, match='already'):
        ChatWorkspace(manager, db, engine_factory=engine.open)
    ws.close()
    reopened = ChatWorkspace(manager, db, engine_factory=engine.open)
    try:
        assert reopened.get(session['id'])['collect'] is False
        assert len(reopened.get(session['id'])['turns']) == 1
        archived = reopened.archive(session['id'], {'revision': result['session']['revision']})
        assert archived['status'] == 'ARCHIVED'
        with connect(db) as conn:
            assert conn.execute('SELECT training_eligible, exclude_from_training FROM reviews').fetchone()[:] == (0, 1)
        with pytest.raises(IntegrationError):
            send(reopened, archived)
    finally:
        reopened.close()


def test_strict_fields_and_stale_tabs(chat):
    ws, _, manager, db = chat
    with pytest.raises(IntegrationError):
        new(ws, collect=True)
    session = new(ws)
    with pytest.raises(IntegrationError):
        send(ws, session, system='hidden')
    with pytest.raises(IntegrationError):
        ws.collect(session['id'], {'enabled': 'true', 'revision': 0})
    session2 = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
    with pytest.raises(IntegrationError):
        send(ws, session)
    manager._states['lmstudio']['connection'] = 'DISCONNECTED'
    with pytest.raises(IntegrationError):
        send(ws, session2)
    assert count(db, 'chat_turns') == 0


def test_review_context_contains_only_continuously_consented_complete_segment(chat):
    from app.service import list_review_queue
    ws,engine,_,db=chat
    first=send(ws,new(ws),text='PRIVATE BEFORE COLLECTION')['session']
    opted=ws.collect(first['id'],{'enabled':True,'revision':first['revision']})
    second=send(ws,opted,text='consented question one')['session']
    send(ws,second,text='consented question two')
    queue=list_review_queue(db)
    assert len(queue[-1]['context'])==4
    assert 'PRIVATE BEFORE COLLECTION' not in str(queue)
    assert 'earlier context excluded' in queue[-1]['conversation_title']


def test_revocation_then_reenable_without_stop_cannot_collect_old_turn(chat):
    ws,engine,_,db=chat
    session=new(ws);session=ws.collect(session['id'],{'enabled':True,'revision':session['revision']})
    engine.started,engine.release=threading.Event(),threading.Event()
    results=[]
    t=threading.Thread(target=lambda:results.append(send(ws,session)))
    t.start();assert engine.started.wait(2)
    off=ws.collect(session['id'],{'enabled':False,'revision':ws.get(session['id'])['revision']})
    ws.collect(session['id'],{'enabled':True,'revision':off['revision']})
    engine.release.set();t.join(4)
    assert results[0]['status']=='COMPLETED'
    assert count(db,'chat_turns')==1 and count(db,'reviews')==0


def test_context_rollover_is_atomic_if_empty_session_creation_fails(chat):
    ws,engine,_,db=chat
    session=new(ws);engine.count=481
    with connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_rollover BEFORE INSERT ON chat_sessions BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(sqlite3.Error):send(ws,session)
    assert ws.get(session['id'])['status']=='OPEN'
    assert count(db,'chat_sessions')==1


def test_restart_marks_unfinished_receipts_interrupted_and_never_replays(chat):
    ws,engine,manager,db=chat
    session=new(ws);request_id=str(uuid4())
    with connect(db) as conn:
        conn.execute("INSERT INTO chat_requests VALUES(?,?,?,'RUNNING','fixture')",(session['id'],request_id,'unknown'))
    ws.close();reopened=ChatWorkspace(manager,db,engine_factory=engine.open)
    try:
        with connect(db) as conn:
            assert conn.execute('SELECT status FROM chat_requests').fetchone()[0]=='INTERRUPTED'
        with pytest.raises(IntegrationError):send(reopened,session,request_id=request_id)
        assert not engine.calls and count(db,'chat_turns')==0
    finally:reopened.close()
