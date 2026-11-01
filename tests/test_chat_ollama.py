"""Ollama admission against a scripted fake server: failure paths no engine can be
made to produce on demand. Real engine behavior is in test_chat_ollama_real.py."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from uuid import uuid4

import pytest

from app.chat_engine import OllamaEngine, open_engine
from app.chat_workspace import ChatWorkspace
from app.db import apply_migrations, connect
from app.integrations import CONNECTORS, IntegrationError, IntegrationManager, request_json

DIGEST = 'a' * 64
MODEL = 'fixture:latest'


class FakeOllama:
    """Models the observed 0.40.13 contract; each test bends one part of it."""

    def __init__(self):
        self.requests, self.prompt, self.digest, self.context = [], 40, DIGEST, None
        self.show = {'capabilities':['completion'], 'details':{'quantization_level':'Q4_K_M'},
                     'model_info':{'general.architecture':'llama', 'llama.context_length':8192, 'llama.block_count':4,
                                   'llama.embedding_length':256, 'llama.attention.head_count':4}}
        self.reply = {'done':True, 'done_reason':'stop', 'eval_count':3,
                      'message':{'role':'assistant','content':'  هلا 🙂  '}}
        self.honors_truncate, self.clamp, self.overflow_text = True, None, None
        self.replace_digest_after_reply, self.hang = False, None
        self.version = '0.40.13'
        self.hang_show, self.release_show = None, threading.Event()
        self.hang_tags_after_reply, self.release_tags = None, threading.Event()
        self.reply_seen = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, value):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                fake.requests.append((self.path, None))
                if self.path == '/api/tags':
                    if fake.reply_seen and fake.hang_tags_after_reply:
                        fake.hang_tags_after_reply.set()
                        fake.release_tags.wait(4)
                    self.send(200, {'models':[{'name':MODEL, 'digest':fake.digest, 'size':5 * 1024**3}]})
                elif self.path == '/api/version':
                    self.send(200, {'version':fake.version})
                else:
                    rows = [{'name':MODEL, 'digest':fake.digest, 'context_length':fake.context, 'size':6 * 1024**3, 'size_vram':6 * 1024**3}] if fake.context else []
                    self.send(200, {'models':rows})

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fake.requests.append((self.path, payload))
                if self.path == '/api/show':
                    if fake.hang_show:
                        fake.hang_show.set()
                        fake.release_show.wait(4)
                    return self.send(200, fake.show)
                return self.send(*fake.chat(payload, self))

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.spec = replace(CONNECTORS['ollama'], port=self.http.server_port)

    def chat(self, payload, handler):
        options = payload['options']
        self.context = self.clamp or options['num_ctx']
        size = sum(len(m['content']) for m in payload['messages'])
        if self.hang and options['num_predict'] > 1:
            self.hang.set()
            time.sleep(5)
        if size > 1000:
            if self.honors_truncate and payload.get('truncate') is False:
                return 400, {'error':self.overflow_text or f'request ({size} tokens) exceeds the available context size ({self.context} tokens), try increasing it'}
            return 200, {**self.reply, 'prompt_eval_count':10}
        if options['num_predict'] == 1:
            return 200, {'done':True, 'done_reason':'length', 'eval_count':1, 'prompt_eval_count':self.prompt,
                         'message':{'role':'assistant','content':'x'}}
        if self.replace_digest_after_reply:
            self.digest = 'b' * 64
        self.reply_seen = True
        return 200, {**self.reply, 'prompt_eval_count':self.prompt}

    def chats(self):
        return [p for path, p in self.requests if path == '/api/chat']

    def close(self):
        if self.thread.is_alive():
            self.http.shutdown()
            self.http.server_close()
            self.thread.join(3)


@pytest.fixture
def fake():
    server = FakeOllama()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def chat(fake, tmp_path):
    db = tmp_path / 'own.db'
    apply_migrations(db)
    manager = IntegrationManager(connectors={'ollama':fake.spec}, home=tmp_path)
    manager._states['ollama'].update(connection='CONNECTED', selected_model=MODEL, models=[MODEL], selection_revision=2)
    workspace = ChatWorkspace(manager, db, engine_factory=open_engine)
    try:
        yield workspace, db
    finally:
        workspace.close()


def new(ws, budget=512, reserve=32, approved=True):
    return ws.create({'provider':'ollama', 'model':MODEL, 'selection_revision':2, 'context_budget':budget,
                      'reply_reserve':reserve, 'load_approved':approved})


def send(ws, session, text='سؤال'):
    return ws.send(session['id'], {'request_id':str(uuid4()), 'revision':session['revision'], 'selection_revision':2, 'text':text})


def saved(db):
    with connect(db) as conn:
        return conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0]


def error_of(call):
    with pytest.raises(IntegrationError) as caught:
        call()
    return caught.value.code


def test_request_is_only_history_and_the_two_disclosed_limits(fake, chat):
    ws, db = chat
    result = send(ws, new(ws))
    assert result['status'] == 'COMPLETED'
    assert result['session']['turns'][0]['assistant'] == '  هلا 🙂  '
    reply = fake.chats()[-1]
    assert set(reply) == {'model', 'messages', 'stream', 'truncate', 'shift', 'options'}
    assert reply['model'] == f'sha256:{DIGEST}:local'
    assert {r['model'] for path, r in fake.requests if path == '/api/show'} == {f'sha256:{DIGEST}:local'}
    assert reply['messages'] == [{'role':'user', 'content':'سؤال'}]
    assert reply['options'] == {'num_ctx':512, 'num_predict':32}
    assert reply['stream'] is False and reply['truncate'] is False and reply['shift'] is False


def test_every_turn_proves_refusal_then_counts_then_generates_in_that_order(fake, chat):
    ws, _ = chat
    send(ws, new(ws))
    predicts = [c['options']['num_predict'] for c in fake.chats()]
    assert predicts == [1, 1, 32]
    assert len(fake.chats()[0]['messages']) == 3
    assert all(path not in {'/api/generate', '/api/pull', '/api/create', '/api/delete'} for path, _ in fake.requests)


@pytest.mark.parametrize('prompt,allowed', [(480, True), (481, False)])
def test_exact_equality_is_admitted_and_one_over_rolls_over_without_reply(fake, chat, prompt, allowed):
    ws, db = chat
    session = new(ws)
    fake.prompt = prompt
    result = send(ws, session)
    if allowed:
        assert result['status'] == 'COMPLETED'
    else:
        assert result['status'] == 'CONTEXT_LIMIT'
        assert (result['input_tokens'], result['reply_reserve'], result['context_budget']) == (481, 32, 512)
        assert result['new_session']['turns'] == [] and result['new_session']['load_approved'] == 1
        assert ws.get(session['id'])['status'] == 'CONTEXT_LIMIT'
        assert not [c for c in fake.chats() if c['options']['num_predict'] == 32]
        assert saved(db) == 0


def test_prompt_beyond_engine_context_rolls_over_with_the_engine_count(fake, chat):
    ws, db = chat
    session = new(ws)
    result = send(ws, session, 'x' * 2000)
    assert result['status'] == 'CONTEXT_LIMIT' and result['input_tokens'] == 2000
    assert saved(db) == 0


def test_engine_that_ignores_truncate_is_blocked_before_any_real_turn(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.honors_truncate = False
    assert error_of(lambda: send(ws, session)) == 'CONTEXT_REFUSAL_UNPROVEN'
    assert len(fake.chats()) == 1 and saved(db) == 0


@pytest.mark.parametrize('text,code', [
    ('context too long', 'CONTEXT_REFUSAL_UNPROVEN'),
    ('request (9 tokens) exceeds the available context size (9 tokens)', 'CONTEXT_REFUSAL_UNPROVEN'),
    ('request (9999 tokens) exceeds the available context size (10 tokens)', 'ENGINE_CONTEXT_MISMATCH'),
])
def test_unrecognized_inconsistent_or_clamped_refusal_is_not_proof(fake, chat, text, code):
    ws, _ = chat
    session = new(ws)
    fake.overflow_text = text
    assert error_of(lambda: send(ws, session)) == code


def test_silent_num_ctx_clamp_seen_only_in_ps_blocks_the_turn(fake, chat):
    ws, db = chat
    session = new(ws, budget=4096)
    fake.clamp = 2048
    assert error_of(lambda: send(ws, session)) == 'ENGINE_CONTEXT_MISMATCH'
    assert not [c for c in fake.chats() if c['options']['num_predict'] == 32] and saved(db) == 0


def test_budget_above_model_maximum_refused_at_creation_and_after_stale_metadata(fake, chat):
    ws, _ = chat
    assert error_of(lambda: new(ws, budget=16384)) == 'ENGINE_CONTEXT_LIMIT'
    session = new(ws, budget=4096)
    fake.show['model_info']['llama.context_length'] = 2048
    assert error_of(lambda: send(ws, session)) == 'ENGINE_CONTEXT_LIMIT'
    assert fake.chats() == []
    assert ws.get(session['id'])['status'] == 'OPEN'


@pytest.mark.parametrize('name,change', [
    ('remote', lambda s: s.update(remote_host='https://ollama.com:443', remote_model='x')),
    ('capability', lambda s: s.update(capabilities=['embedding'])),
    ('context', lambda s: s['model_info'].pop('llama.context_length')),
])
def test_cloud_embedding_or_unknown_limit_models_never_receive_chat(fake, chat, name, change):
    ws, _ = chat
    session = new(ws)
    change(fake.show)
    assert error_of(lambda: send(ws, session)) in {'REMOTE_MODEL_REFUSED', 'MODEL_UNSUPPORTED', 'CONTEXT_UNKNOWN'}
    assert fake.chats() == []


def test_cloud_tag_is_refused_by_name_even_if_show_looks_local(fake):
    engine = OllamaEngine(fake.spec, 'gpt-oss:cloud')
    fake_tags = fake.requests
    with pytest.raises(IntegrationError):
        engine.limits()
    assert not [r for r in fake_tags if r[0] == '/api/chat']


@pytest.mark.parametrize('change', [
    lambda r: r.update(done_reason='length'), lambda r: r.update(done=False), lambda r: r.update(done_reason='unload'),
    lambda r: r.pop('done_reason'), lambda r: r['message'].update(content='   '), lambda r: r['message'].update(content=None),
    lambda r: r['message'].update(tool_calls=[{'function':{'name':'x'}}]), lambda r: r['message'].update(role='tool'),
    lambda r: r.update(eval_count=33), lambda r: r.update(remote_host='https://ollama.com'),
])
def test_incomplete_or_structured_reply_is_never_saved_or_collected(fake, chat, change):
    ws, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled':True, 'revision':session['revision']})
    change(fake.reply)
    assert error_of(lambda: send(ws, session)) in {'INCOMPLETE_RESPONSE', 'INVALID_LIMIT'}
    assert saved(db) == 0
    with connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0


def test_count_changing_between_probe_and_reply_is_refused(fake, chat):
    ws, db = chat
    session = new(ws)
    original = fake.chat

    def shifted(payload, handler):
        status, value = original(payload, handler)
        return (status, {**value, 'prompt_eval_count':41}) if payload['options']['num_predict'] == 32 else (status, value)

    fake.chat = shifted
    assert error_of(lambda: send(ws, session)) == 'INCOMPLETE_RESPONSE'
    assert saved(db) == 0


def test_thinking_counts_against_reply_but_only_final_text_is_kept(fake, chat):
    ws, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled':True, 'revision':session['revision']})
    fake.reply['message']['thinking'] = 'private reasoning trace'
    fake.reply['eval_count'] = 30
    result = send(ws, session)
    assert result['session']['turns'][0]['assistant'] == '  هلا 🙂  '
    assert result['session']['turns'][0]['output_tokens'] == 30
    with connect(db) as conn:
        assert 'private reasoning trace' not in str([tuple(r) for r in conn.execute('SELECT * FROM messages')])
        metadata = json.loads(conn.execute("SELECT metadata_json FROM messages WHERE role='assistant'").fetchone()[0])
    assert metadata['reasoning_discarded'] is True
    assert metadata['model_key'] == f'ollama:{DIGEST}' and metadata['engine_version'] == '0.40.13'


def test_model_replaced_during_reply_is_discarded(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.replace_digest_after_reply = True
    assert error_of(lambda: send(ws, session)) == 'MODEL_CHANGED'
    assert saved(db) == 0


def test_tag_repointed_between_turns_cannot_continue_old_history(fake, chat):
    ws, db = chat
    session = send(ws, new(ws))['session']
    fake.digest = 'c' * 64
    fake.prompt = 60
    assert error_of(lambda: send(ws, session)) == 'MODEL_CHANGED'
    assert saved(db) == 1


def test_history_dropped_by_engine_is_caught_even_if_refusal_looked_fine(fake, chat):
    ws, db = chat
    session = send(ws, new(ws))['session']
    fake.prompt = 40
    assert error_of(lambda: send(ws, session)) == 'CONTEXT_SHRANK'
    assert saved(db) == 1


def test_load_approval_required_and_lm_studio_can_never_claim_it(fake, chat, tmp_path):
    ws, db = chat
    assert error_of(lambda: new(ws, approved=False)) == 'LOAD_APPROVAL_REQUIRED'
    assert error_of(lambda: new(ws, approved='yes')) == 'INVALID_PAYLOAD'
    assert fake.requests == []
    session = new(ws)
    with connect(db) as conn:
        conn.execute('DELETE FROM chat_session_bindings')
    assert error_of(lambda: send(ws, session)) == 'LOAD_APPROVAL_REQUIRED'
    assert fake.chats() == []


def test_stop_during_reply_closes_the_socket_and_saves_nothing(fake, chat):
    ws, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled':True, 'revision':session['revision']})
    fake.hang = threading.Event()
    outcome = []

    def run():
        try:
            outcome.append(send(ws, session))
        except IntegrationError as error:
            outcome.append(error.code)

    turn = threading.Thread(target=run)
    began = time.monotonic()
    turn.start()
    assert fake.hang.wait(3)
    ws.stop(session['id'])
    turn.join(3)
    assert outcome == ['STOPPED'] and time.monotonic() - began < 2.5
    assert saved(db) == 0
    with connect(db) as conn:
        assert conn.execute('SELECT status FROM chat_requests').fetchone()[0] == 'STOPPED'
        assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0


def test_engine_failure_keeps_conversation_open_and_never_replays(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.close()
    assert error_of(lambda: send(ws, session)) in {'UNREACHABLE', 'INVALID_RESPONSE'}
    assert ws.get(session['id'])['status'] == 'OPEN' and saved(db) == 0


def test_concurrent_send_on_one_runtime_is_refused_not_queued(fake, chat):
    ws, db = chat
    first, second = new(ws), new(ws)
    fake.hang = threading.Event()
    outcome = []
    turn = threading.Thread(target=lambda: outcome.append(send(ws, first)))
    turn.start()
    assert fake.hang.wait(3)
    assert error_of(lambda: send(ws, second)) == 'ENGINE_BUSY'
    turn.join(8)
    assert outcome[0]['status'] == 'COMPLETED' and saved(db) == 1


def test_retry_of_completed_turn_is_idempotent_after_conversation_closed(fake, chat):
    ws, db = chat
    session = new(ws)
    request_id = str(uuid4())
    done = ws.send(session['id'], {'request_id':request_id, 'revision':session['revision'], 'selection_revision':2, 'text':'q'})
    fake.prompt = 500
    assert send(ws, done['session'])['status'] == 'CONTEXT_LIMIT'
    again = ws.send(session['id'], {'request_id':request_id, 'revision':0, 'selection_revision':2, 'text':'q'})
    assert again['duplicate'] is True and saved(db) == 1


def test_error_body_only_reaches_callers_who_listed_that_status(fake):
    fake.reply = {}
    assert 'http_status' not in request_json(fake.spec, '/api/version')
    with pytest.raises(IntegrationError):
        request_json(fake.spec, '/api/pull', {'model':'x'})


def test_rollover_keeps_collection_off_and_never_copies_history(fake, chat):
    ws, db = chat
    session = new(ws)
    session = ws.collect(session['id'], {'enabled':True, 'revision':session['revision']})
    done = send(ws, session)
    fake.prompt = 481
    result = send(ws, done['session'], 'unsent draft')
    assert result['new_session']['collect'] is False and result['new_session']['turns'] == []
    with connect(db) as conn:
        assert 'unsent draft' not in str([tuple(r) for r in conn.execute('SELECT * FROM chat_turns')])
        assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 1


def test_immutable_local_reference_prevents_cloud_retarget_and_A_B_A_misattribution(fake, chat):
    ws, db = chat
    session = new(ws)
    assert session['model_fingerprint'] == f'ollama:{DIGEST}'
    original = fake.chat
    outbound_cloud = []

    def swap(payload, handler):
        if payload['options']['num_predict'] == 32:
            # Another client changes A -> B (a cloud alias) -> A while the
            # final request is in flight. Name-based routing would leak.
            fake.digest = 'b' * 64
            try:
                if payload['model'] == MODEL:
                    outbound_cloud.append(payload['messages'])
                    return 200, {**fake.reply, 'message':{'role':'assistant','content':'B reply'},
                                 'prompt_eval_count':fake.prompt}
                assert payload['model'] == f'sha256:{DIGEST}:local'
                return original(payload, handler)
            finally:
                fake.digest = DIGEST
        return original(payload, handler)

    fake.chat = swap
    done = send(ws, session)
    assert done['status'] == 'COMPLETED'
    assert done['session']['turns'][0]['assistant'] == '  هلا 🙂  '
    assert not outbound_cloud and saved(db) == 1
    assert {p['model'] for p in fake.chats()} == {f'sha256:{DIGEST}:local'}


def test_alias_repoint_before_first_turn_is_refused_before_user_text(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.digest = 'b' * 64
    assert error_of(lambda: send(ws, session, 'sensitive input')) == 'MODEL_CHANGED'
    assert not fake.chats() and saved(db) == 0


@pytest.mark.parametrize('bad_digest,bad_version', [
    ('bad-digest', '0.40.13'),
    (DIGEST, '0.40.14'),
    (DIGEST, '0.12.0'),
])
def test_unsupported_digest_or_version_blocks_without_chat(fake, chat, bad_digest, bad_version):
    ws, db = chat
    fake.digest, fake.version = bad_digest, bad_version
    assert error_of(lambda: new(ws)) == 'MODEL_REFERENCE_UNVERIFIED'
    assert fake.chats() == [] and saved(db) == 0


def test_stop_interrupts_blocked_show_metadata_before_text_probe(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.hang_show = threading.Event()
    outcome = []

    def worker():
        try:
            outcome.append(send(ws, session))
        except IntegrationError as e:
            outcome.append(e.code)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert fake.hang_show.wait(3)
        began = time.monotonic()
        assert ws.stop(session['id'])['stop_requested']
        thread.join(2)
        assert outcome == ['STOPPED'] and time.monotonic() - began < 1.8
        assert fake.chats() == [] and saved(db) == 0
    finally:
        fake.release_show.set()
        thread.join(4)


def test_stop_interrupts_post_reply_tags_wait_without_saving(fake, chat):
    ws, db = chat
    session = new(ws)
    fake.hang_tags_after_reply = threading.Event()
    outcome = []

    def worker():
        try:
            outcome.append(send(ws, session))
        except IntegrationError as e:
            outcome.append(e.code)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert fake.hang_tags_after_reply.wait(3)
        began = time.monotonic()
        assert ws.stop(session['id'])['stop_requested']
        thread.join(2)
        assert outcome == ['STOPPED'] and time.monotonic() - began < 1.8
        assert saved(db) == 0
        with connect(db) as conn:
            assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0
    finally:
        fake.release_tags.set()
        thread.join(4)
