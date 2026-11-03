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
    assert status == 200 and last == {'type': 'error', 'code': 'INCOMPLETE_RESPONSE', 'error': last['error'], 'check': 'STOP_REASON_LENGTH', 'hint': last['hint']}
    assert 'Thinking tokens count' in last['hint']
    status, _, raw = request(f"/api/v1/chat/sessions/{session['id']}/delete-preview")
    assert status == 200 and json.loads(raw)['turns'] == 0


def test_browser_disconnect_mid_stream_stops_the_turn_and_saves_nothing(tmp_path):
    """Security review: a closed browser connection must stop generation, and a
    stopped turn is never committed or collected."""
    import socket
    import time as _time

    class Endless(StreamEngine):
        def generate(self, messages, reserve, stop, on_delta=None):
            deadline = _time.monotonic() + 8
            while not stop.is_set() and _time.monotonic() < deadline:
                on_delta('content', 'PARTIAL ' * 50)
                _time.sleep(0.02)
            raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)

    db = tmp_path / 'disconnect.db'
    apply_migrations(db)
    http = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    http.integrations._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', selection_revision=2)
    engine = Endless()
    http.chat = ChatWorkspace(http.integrations, db, engine_factory=engine.open, artifact_roots=[], backups_root=None)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        session = http.chat.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                                    'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})
        session = http.chat.collect(session['id'], {'enabled': True, 'revision': session['revision']})
        body = json.dumps({'request_id': str(uuid4()), 'revision': session['revision'], 'selection_revision': 2, 'text': 'x'}).encode()
        sock = socket.create_connection(('127.0.0.1', http.server_port), timeout=5)
        sock.sendall((f"POST /api/v1/chat/sessions/{session['id']}/send-stream HTTP/1.1\r\nHost: 127.0.0.1:{http.server_port}\r\n"
                      f"Content-Type: application/json\r\nX-NajdiLab-CSRF: {CSRF_TOKEN}\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body)
        # The headers and the first NDJSON line may arrive in separate reads (they do on Windows).
        received = b''
        while b'"accepted"' not in received:
            chunk = sock.recv(65536)
            assert chunk, received
            received += chunk
        sock.close()  # the browser goes away mid-reply
        deadline = _time.monotonic() + 6
        while _time.monotonic() < deadline:
            with connect(db) as conn:
                status = conn.execute('SELECT status FROM chat_requests').fetchone()[0]
            if status != 'RUNNING':
                break
            _time.sleep(0.05)
        assert status == 'STOPPED'
        with connect(db) as conn:
            assert conn.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)


def test_client_that_stops_reading_cannot_hold_the_runtime(tmp_path, monkeypatch):
    """F6: a stalled reader (connection open, nothing read) times out the write
    and stops the turn instead of holding the session and runtime lease."""
    import socket
    import time as _time
    monkeypatch.setattr(server, 'STREAM_WRITE_TIMEOUT', 1)

    class Flood(StreamEngine):
        def generate(self, messages, reserve, stop, on_delta=None):
            deadline = _time.monotonic() + 15
            while not stop.is_set() and _time.monotonic() < deadline:
                on_delta('content', 'Z' * 8192)
            raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)

    db = tmp_path / 'stall.db'
    apply_migrations(db)
    http = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    http.integrations._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', selection_revision=2)
    http.chat = ChatWorkspace(http.integrations, db, engine_factory=Flood().open, artifact_roots=[], backups_root=None)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    sock = None
    try:
        session = http.chat.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                                    'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})
        body = json.dumps({'request_id': str(uuid4()), 'revision': session['revision'], 'selection_revision': 2, 'text': 'x'}).encode()
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.connect(('127.0.0.1', http.server_port))
        sock.sendall((f"POST /api/v1/chat/sessions/{session['id']}/send-stream HTTP/1.1\r\nHost: 127.0.0.1:{http.server_port}\r\n"
                      f"Content-Type: application/json\r\nX-NajdiLab-CSRF: {CSRF_TOKEN}\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body)
        deadline = _time.monotonic() + 12  # never read: the server's writes must time out
        status = 'RUNNING'
        while _time.monotonic() < deadline and status == 'RUNNING':
            _time.sleep(0.1)
            with connect(db) as conn:
                status = conn.execute('SELECT status FROM chat_requests').fetchone()[0]
        assert status == 'STOPPED'
        assert http.chat.get(session['id'])['busy'] is False, 'the session is free again'
    finally:
        if sock:
            sock.close()
        http.shutdown()
        http.server_close()
        thread.join(3)


def test_request_log_never_contains_query_text(api, capsys):
    """F7: chat search terms can be conversation text; logs keep only the path."""
    request, _ = api
    request('/api/v1/chat/sessions?q=SECRET-SEARCH-TERM&limit=5')
    out = capsys.readouterr().out
    assert 'SECRET-SEARCH-TERM' not in out and '/api/v1/chat/sessions?[query omitted]' in out
