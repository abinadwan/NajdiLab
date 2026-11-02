"""Chat V2 streaming against scripted engines: Ollama NDJSON, the real pinned
LM Studio SDK helper, and NajdiLab's own NDJSON route. Synthetic text only."""
from __future__ import annotations

from http.client import HTTPConnection
import json
import threading
from uuid import uuid4

import pytest

from app import chat_engine, server
from app.chat_engine import open_engine
from app.chat_workspace import ChatWorkspace
from app.db import apply_migrations, connect
from app.http_security import CSRF_TOKEN
from app.integrations import IntegrationError, IntegrationManager

from test_chat_ollama import MODEL, FakeOllama
from test_chat_sdk_integration import sdk_runtime  # noqa: F401  (fixture)
from test_chat_v2 import StreamEngine


class StreamingOllama(FakeOllama):
    """Ollama 0.40.13 NDJSON shape: partial chunks, then exactly one `done`."""

    def __init__(self):
        super().__init__()
        self.chunks = [{'message': {'role': 'assistant', 'content': '', 'thinking': 'تفكير '}, 'done': False},
                       {'message': {'role': 'assistant', 'content': '', 'thinking': 'خاص'}, 'done': False},
                       {'message': {'role': 'assistant', 'content': 'هلا'}, 'done': False},
                       {'message': {'role': 'assistant', 'content': ' 🙂'}, 'done': False},
                       {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'done_reason': 'stop', 'eval_count': 9}]
        self.content_type = 'application/x-ndjson'
        handler = self.http.RequestHandlerClass
        original = handler.send

        def send(h, status, value):
            if status is not None:
                original(h, status, value)
        handler.send = send

    def chat(self, payload, handler):
        if not payload.get('stream'):
            return super().chat(payload, handler)
        self.streamed = payload
        handler.send_response(200)
        handler.send_header('Content-Type', self.content_type)
        handler.end_headers()
        for chunk in self.chunks:
            if chunk.get('done'):
                chunk = {**chunk, 'prompt_eval_count': self.prompt}
            handler.wfile.write(json.dumps(chunk, ensure_ascii=False).encode() + b'\n')
            handler.wfile.flush()
        handler.close_connection = True
        return None, None


@pytest.fixture
def stream_chat(tmp_path):
    fake = StreamingOllama()
    db = tmp_path / 'stream.db'
    apply_migrations(db)
    manager = IntegrationManager(connectors={'ollama': fake.spec}, home=tmp_path)
    manager._states['ollama'].update(connection='CONNECTED', selected_model=MODEL, models=[MODEL], selection_revision=2)
    ws = ChatWorkspace(manager, db, engine_factory=open_engine, artifact_roots=[], backups_root=None)
    try:
        yield ws, fake, db
    finally:
        ws.close()
        fake.close()


def _session(ws):
    return ws.create({'provider': 'ollama', 'model': MODEL, 'selection_revision': 2, 'context_budget': 512,
                      'reply_reserve': 32, 'load_approved': True})


def _send(ws, session, events):
    return ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                   'selection_revision': 2, 'text': 'سؤال'}, on_event=events.append)


def test_ollama_stream_separates_thinking_and_saves_only_the_verified_answer(stream_chat):
    ws, fake, db = stream_chat
    events = []
    result = _send(ws, _session(ws), events)
    assert ''.join(e['text'] for e in events if e['type'] == 'thinking') == 'تفكير خاص'
    assert ''.join(e['text'] for e in events if e['type'] == 'content') == 'هلا 🙂'
    assert result['session']['turns'][0]['assistant'] == 'هلا 🙂'
    assert fake.streamed['stream'] is True and fake.streamed['truncate'] is False and fake.streamed['shift'] is False
    assert set(fake.streamed) == {'model', 'messages', 'stream', 'truncate', 'shift', 'options'}, 'no think/system/tools added'
    with connect(db) as conn:
        dump = str([tuple(r) for t in ('chat_turns', 'messages', 'reviews') for r in conn.execute(f'SELECT * FROM {t}')])
    assert 'تفكير' not in dump and 'خاص' not in dump


def test_ollama_proof_is_reused_but_identity_and_runtime_are_rechecked(stream_chat):
    ws, fake, db = stream_chat
    chat_engine._REFUSAL_PROOFS.clear()
    session = _session(ws)
    first = _send(ws, session, [])
    oversized = lambda: sum(1 for p in fake.chats() if sum(len(m['content']) for m in p['messages']) > 1000)
    assert oversized() == 1
    fake.prompt += 20
    second = _send(ws, first['session'], [])
    assert oversized() == 1, 'second turn reused the version/digest/budget-bound proof'
    assert second['timings']['admission']['context_proof'] == 'reused'
    fake.digest, fake.prompt = 'b' * 64, fake.prompt + 20
    with pytest.raises(IntegrationError) as changed:
        _send(ws, second['session'], [])
    assert changed.value.code == 'MODEL_CHANGED'


@pytest.mark.parametrize('chunks,code,check', [
    ([{'message': {'role': 'assistant', 'content': 'نص'}, 'done': True, 'done_reason': 'length', 'eval_count': 32}], 'INCOMPLETE_RESPONSE', 'STOP_REASON_LENGTH'),
    ([{'message': {'role': 'assistant', 'content': '', 'thinking': 'فقط تفكير'}, 'done': True, 'done_reason': 'stop', 'eval_count': 5}], 'INCOMPLETE_RESPONSE', 'EMPTY_CONTENT'),
    ([{'message': {'role': 'assistant', 'content': 'نص'}, 'done': False}, {'error': 'synthetic engine failure'}], 'ENGINE_REFUSED', None),
    ([{'message': {'role': 'assistant', 'content': 'نص'}, 'done': False}], 'INCOMPLETE_RESPONSE', None),
    ([{'message': {'role': 'assistant', 'content': 'نص'}, 'done': True, 'done_reason': 'stop', 'eval_count': 1},
      {'message': {'role': 'assistant', 'content': 'زيادة'}, 'done': False}], 'INCOMPLETE_RESPONSE', None),
])
def test_ollama_stream_failures_save_nothing(stream_chat, chunks, code, check):
    ws, fake, db = stream_chat
    fake.chunks = chunks
    with pytest.raises(IntegrationError) as error:
        _send(ws, _session(ws), [])
    assert error.value.code == code and getattr(error.value, 'check', None) == check
    with connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0] == 0
        assert conn.execute('SELECT status FROM chat_requests').fetchone()[0] == 'FAILED'


def test_ollama_stream_with_wrong_content_type_is_refused(stream_chat):
    ws, fake, _ = stream_chat
    fake.content_type = 'text/html'
    with pytest.raises(IntegrationError) as error:
        _send(ws, _session(ws), [])
    assert error.value.code == 'INVALID_RESPONSE'


def test_real_lmstudio_helper_streams_answer_fragments_and_verifies_them(sdk_runtime):  # noqa: F811
    spec, calls, state = sdk_runtime
    messages = [{'role': 'user', 'content': 'synthetic'}]
    deltas = []
    with open_engine(spec, 'fixture') as engine:
        engine.measure(messages, 4096)
        result = engine.generate(messages, 32, threading.Event(), on_delta=lambda c, t: deltas.append((c, t)))
    assert deltas == [('content', '  synthetic answer  ')]
    assert result['content'] == '  synthetic answer  ' and result['stop_reason'] == 'eosFound'
    assert 'first_token_ms' in result['timings']


# ------------------------------------------------------------------ HTTP route
@pytest.fixture
def api(tmp_path):
    db = tmp_path / 'http.db'
    apply_migrations(db)
    http = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    http.integrations._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', selection_revision=2)
    engine = StreamEngine()
    http.chat = ChatWorkspace(http.integrations, db, engine_factory=engine.open, artifact_roots=[], backups_root=None)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def request(path, data=None):
        conn = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
        conn.request('POST' if data is not None else 'GET', path, json.dumps(data).encode() if data is not None else None,
                     {'Content-Type': 'application/json', 'X-NajdiLab-CSRF': CSRF_TOKEN})
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, response.getheader('Content-Type'), raw
    try:
        yield request, engine
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)


def test_stream_route_sends_ndjson_events_then_done(api):
    request, _ = api
    status, _, raw = request('/api/v1/chat/sessions', {'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                                                       'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})
    session = json.loads(raw)
    status, kind, raw = request(f"/api/v1/chat/sessions/{session['id']}/send-stream",
                                {'request_id': str(uuid4()), 'revision': session['revision'], 'selection_revision': 2, 'text': 'سؤال'})
    assert status == 200 and kind.startswith('application/x-ndjson')
    events = [json.loads(line) for line in raw.decode().splitlines()]
    assert events[0]['type'] == 'accepted' and events[-1]['type'] == 'done'
    assert events[-1]['result']['session']['turns'][0]['assistant'] == 'هلا والله'
    status, _, raw = request('/api/v1/chat/presets')
    assert [p['context_budget'] for p in json.loads(raw)['items']] == [4096, 8192, 16384]


def test_stream_route_errors_before_acceptance_are_plain_json_and_after_are_events(api):
    request, engine = api
    _, _, raw = request('/api/v1/chat/sessions', {'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                                                  'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})
    session = json.loads(raw)
    status, kind, raw = request(f"/api/v1/chat/sessions/{session['id']}/send-stream",
                                {'request_id': str(uuid4()), 'revision': session['revision'] + 9, 'selection_revision': 2, 'text': 'x'})
    assert status == 409 and kind.startswith('application/json') and json.loads(raw)['code'] == 'STALE_CHAT'
    engine.reason = 'length'
    status, _, raw = request(f"/api/v1/chat/sessions/{session['id']}/send-stream",
                             {'request_id': str(uuid4()), 'revision': session['revision'], 'selection_revision': 2, 'text': 'x'})
    last = json.loads(raw.decode().splitlines()[-1])
    assert status == 200 and last == {'type': 'error', 'code': 'INCOMPLETE_RESPONSE', 'error': last['error'], 'check': 'STOP_REASON_LENGTH'}
    status, _, raw = request(f"/api/v1/chat/sessions/{session['id']}/delete-preview")
    assert status == 200 and json.loads(raw)['turns'] == 0
