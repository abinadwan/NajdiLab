"""NajdiLab-owned raw chat sessions. Native application histories are never read."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import threading
from uuid import UUID, uuid4

from .db import DB_PATH, connect as db_connect, transaction, utc_now
from .hardware import snapshot as hardware_snapshot
from .integrations import IntegrationError
from .service import ingest_turn


@contextmanager
def connect(path):
    connection = db_connect(path)
    try:
        yield connection
    finally:
        connection.close()


def fields(data, allowed):
    if not isinstance(data, dict) or set(data) != set(allowed):
        raise IntegrationError("INVALID_PAYLOAD", "Only the documented chat fields are allowed.")


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise IntegrationError("INVALID_LIMIT", "A valid integer context/token limit is required.")
    return value


class ChatWorkspace:
    def __init__(self, integrations, db_path=DB_PATH, *, engine_factory=None):
        self.integrations, self.db_path = integrations, Path(db_path)
        self._lock = threading.RLock()
        self._active, self._consent = {}, {}
        self._closed = False
        if engine_factory is None:
            from .chat_engine import open_engine
            engine_factory = open_engine
        self.engine_factory = engine_factory
        # Separate ports cannot create competing owners of the same chat DB.
        self._owner = self.db_path.with_suffix('.chat.lock').open('a+b')
        try:
            self._owner.seek(0, 2)
            if self._owner.tell() == 0:
                self._owner.write(b'0')
                self._owner.flush()
            self._owner.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._owner.close()
            raise IntegrationError("DATABASE_BUSY", "A chat workspace already owns this database.", 409) from None
        try:
            with connect(self.db_path) as conn:
                conn.execute("UPDATE chat_requests SET status='INTERRUPTED' WHERE status='RUNNING'")
        except Exception:
            self._owner.close()
            raise

    def close(self):
        with self._lock:
            if self._closed:
                return
            if self._active:
                for event in self._active.values():
                    event.set()
                # Never release ownership while an old writer can still commit.
                raise IntegrationError("CHAT_BUSY", "Stop and wait for active chat requests before closing.", 409)
            self._owner.close()
            self._closed = True

    def _row(self, conn, sid):
        if self._closed:
            raise IntegrationError("WORKSPACE_CLOSED", "Chat workspace is closed.", 409)
        row = conn.execute("""SELECT s.*, b.load_approved, b.model_fingerprint FROM chat_sessions s
            LEFT JOIN chat_session_bindings b ON b.session_id=s.id WHERE s.id=?""", (sid,)).fetchone()
        if not row:
            raise IntegrationError("CHAT_NOT_FOUND", "Conversation not found.", 404)
        return dict(row)

    def _expected(self, row, revision):
        if type(revision) is not int or revision != row['revision']:
            raise IntegrationError("STALE_CHAT", "Conversation changed in another request; refresh before continuing.", 409)

    def get(self, sid):
        with self._lock, connect(self.db_path) as conn:
            row = self._row(conn, sid)
            row['collect'] = self._consent.get(sid, (False, 0))[0]
            row['busy'] = sid in self._active
            row['turns'] = [dict(request_id=r['request_id'], user=r['user_content'], assistant=r['assistant_content'],
                                 input_tokens=r['input_tokens'], output_tokens=r['output_tokens'],
                                 collected=r['review_conversation_id'] is not None, created_at=r['created_at'])
                            for r in conn.execute('SELECT * FROM chat_turns WHERE session_id=? ORDER BY ordinal', (sid,))]
            return row

    def list(self):
        with self._lock, connect(self.db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM chat_sessions WHERE status!='ARCHIVED' ORDER BY updated_at DESC LIMIT 200")]

    def _insert_session(self, conn, data):
        sid, now = str(uuid4()), utc_now()
        conn.execute('INSERT INTO chat_sessions(id,provider,model,context_budget,reply_reserve,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                     (sid, data['provider'], data['model'], data['context_budget'], data['reply_reserve'], now, now))
        conn.execute('INSERT INTO chat_session_bindings(session_id,load_approved,model_fingerprint) VALUES(?,?,?)',
                     (sid, int(bool(data['load_approved'])), data.get('model_fingerprint')))
        return sid

    def _create(self, data):
        with connect(self.db_path) as conn:
            sid = self._insert_session(conn,data)
        return self.get(sid)

    def create(self, data):
        fields(data, {'provider','model','selection_revision','context_budget','reply_reserve','load_approved'})
        integer(data['context_budget'], 128, 1048576)
        integer(data['reply_reserve'], 1, min(8192, data['context_budget'] - 1))
        if type(data['load_approved']) is not bool or (data['load_approved'] and data['provider'] != 'ollama'):
            raise IntegrationError("INVALID_PAYLOAD", "Load approval applies only to Ollama, which loads models on request.")
        if data['provider'] == 'ollama' and not data['load_approved']:
            raise IntegrationError("LOAD_APPROVAL_REQUIRED", "Approve Ollama loading this model at the selected context first.", 403)
        with self.integrations.chat_lease(data['provider'], data['model'], data['selection_revision']) as spec:
            with self.engine_factory(spec, data['model']) as engine:
                limits = engine.limits()
            ceiling = limits.get('budget_ceiling')
            if type(ceiling) is not int or ceiling < 1:
                raise IntegrationError("CONTEXT_UNKNOWN", "The runtime did not report a context limit, so the budget cannot be proven.", 409)
            if data['context_budget'] > ceiling:
                raise IntegrationError("ENGINE_CONTEXT_LIMIT", f"This model allows at most {ceiling} tokens of context here; choose a smaller budget.", 409)
            fingerprint = limits.get('model_key')
            if data['provider'] == 'ollama' and (not isinstance(fingerprint, str) or not fingerprint):
                raise IntegrationError('MODEL_REFERENCE_UNVERIFIED', 'Ollama model identity could not be fixed; Chat is blocked.', 409)
            with self._lock:
                return self._create({**data, 'model_fingerprint':fingerprint if isinstance(fingerprint, str) else None})

    def hardware(self, data):
        """Device evidence, plus model evidence when a selected model is named."""
        if set(data) == {'approved'}:
            return hardware_snapshot()
        fields(data, {'approved','provider','model','selection_revision'})
        try:
            with self.integrations.chat_lease(data['provider'], data['model'], data['selection_revision']) as spec:
                with self.engine_factory(spec, data['model']) as engine:
                    return hardware_snapshot(engine.limits())
        except IntegrationError as error:
            # Device numbers stay useful when the runtime cannot answer.
            return hardware_snapshot(limits_error=error.code)

    def collect(self, sid, data):
        fields(data, {'enabled','revision'})
        if type(data['enabled']) is not bool:
            raise IntegrationError("CONSENT_REQUIRED", "Collection requires a separate explicit boolean choice.")
        with self._lock:
            with connect(self.db_path) as conn, transaction(conn):
                row = self._row(conn, sid)
                self._expected(row, data['revision'])
                if row['status'] != 'OPEN':
                    raise IntegrationError("CHAT_CLOSED", "Start a new conversation before enabling collection.", 409)
                epoch = uuid4().hex  # A restart must never reuse an old segment.
                conn.execute('UPDATE chat_sessions SET revision=revision+1, updated_at=? WHERE id=?', (utc_now(), sid))
            self._consent[sid] = data['enabled'], epoch
            return self.get(sid)

    def stop(self, sid):
        with self._lock:
            self.get(sid)
            event = self._active.get(sid)
            if event:
                event.set()
            return {'ok': True, 'stop_requested': event is not None}

    def archive(self, sid, data):
        fields(data, {'revision'})
        with self._lock, connect(self.db_path) as conn, transaction(conn):
            row = self._row(conn, sid)
            self._expected(row, data['revision'])
            if sid in self._active:
                self._active[sid].set()
            conn.execute("UPDATE chat_sessions SET status='ARCHIVED',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), sid))
            conn.execute('''UPDATE reviews SET training_eligible=0,exclude_from_training=1,updated_at=?
                WHERE message_id IN (SELECT id FROM messages WHERE conversation_id IN
                (SELECT review_conversation_id FROM chat_turns WHERE session_id=?))''', (utc_now(), sid))
            self._consent[sid] = False, uuid4().hex
        return self.get(sid)

    def send(self, sid, data):
        fields(data, {'request_id','revision','selection_revision','text'})
        try:
            request_id = str(UUID(data['request_id']))
        except (ValueError, TypeError, AttributeError):
            raise IntegrationError("INVALID_REQUEST_ID", "A request UUID is required.") from None
        text = data['text']
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 65536:
            raise IntegrationError("INVALID_TEXT", "Enter nonblank text up to 64 KiB.")
        payload_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        with self._lock, connect(self.db_path) as conn, transaction(conn):
            row = self._row(conn, sid)
            # Before the status check: a lost response must stay retryable after
            # that very turn, or a later one, closed the conversation.
            receipt = conn.execute('SELECT * FROM chat_requests WHERE session_id=? AND request_id=?', (sid, request_id)).fetchone()
            if receipt:
                if receipt['payload_hash'] != payload_hash or receipt['status'] != 'COMPLETED':
                    raise IntegrationError("REQUEST_ALREADY_USED", "Request was interrupted or differs; refresh and explicitly retry with a new request.", 409)
                return {'status':'COMPLETED', 'duplicate':True, 'session':self.get(sid)}
            if row['status'] != 'OPEN':
                raise IntegrationError("CHAT_CLOSED", "This conversation is closed. Start a new one.", 409)
            if row['provider'] == 'ollama' and not row['load_approved']:
                raise IntegrationError("LOAD_APPROVAL_REQUIRED", "Start a new conversation and approve Ollama loading this model.", 403)
            if row['provider'] == 'ollama' and not row['model_fingerprint']:
                raise IntegrationError("MODEL_BINDING_REQUIRED", "This Ollama session has no verified model identity. Start a new chat.", 409)
            self._expected(row, data['revision'])
            if sid in self._active:
                raise IntegrationError("CHAT_BUSY", "One turn is already in progress.", 409)
            conn.execute("INSERT INTO chat_requests VALUES(?,?,?,'RUNNING',?)", (sid, request_id, payload_hash, utc_now()))
            conn.execute('UPDATE chat_sessions SET revision=revision+1 WHERE id=?', (sid,))
            event = threading.Event()
            self._active[sid] = event
            consent = self._consent.get(sid, (False, 0))
            messages = []
            previous_input = 0
            for turn in self.get(sid)['turns']:
                messages.extend([{'role':'user','content':turn['user']}, {'role':'assistant','content':turn['assistant']}])
                previous_input = turn['input_tokens']
            messages.append({'role':'user','content':text})
        try:
            with self.integrations.chat_lease(row['provider'], row['model'], data['selection_revision']) as spec:
                with self.engine_factory(spec, row['model']) as engine:
                    if row['provider'] == 'ollama':
                        engine.expected_model_key = row['model_fingerprint']
                    measured = engine.measure(messages, row['context_budget'], event)
                    tokens = integer(measured.get('input_tokens'), 0, 1048576)
                    ceiling = integer(measured.get('loaded_context'), 128, 1048576)
                    fingerprint = measured.get('model_key')
                    if row['context_budget'] > ceiling:
                        raise IntegrationError("ENGINE_CONTEXT_LIMIT", "Selected budget exceeds the loaded engine context; choose a smaller budget in a new chat.", 409)
                    if not isinstance(fingerprint, str) or not fingerprint or row['model_fingerprint'] not in (None, fingerprint):
                        raise IntegrationError("MODEL_CHANGED", "A different model now answers to this name, so this history is not its own. Start a new conversation.", 409)
                    # This history extends the last one, so a prompt that did not
                    # grow means something was dropped, whatever the engine claims.
                    if tokens <= previous_input:
                        raise IntegrationError("CONTEXT_SHRANK", "The prompt did not grow with the conversation, so history may have been dropped; nothing was sent for a reply.", 409)
                    if tokens + row['reply_reserve'] > row['context_budget']:
                        with self._lock, connect(self.db_path) as conn, transaction(conn):
                            if event.is_set() or self._row(conn, sid)['status'] != 'OPEN':
                                raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                            conn.execute("UPDATE chat_sessions SET status='CONTEXT_LIMIT',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), sid))
                            conn.execute("UPDATE chat_requests SET status='CONTEXT_LIMIT' WHERE session_id=? AND request_id=?", (sid, request_id))
                            new_sid = self._insert_session(conn,row)
                        with self._lock:
                            self._active.pop(sid, None)
                            return {'status':'CONTEXT_LIMIT', 'input_tokens':tokens, 'reply_reserve':row['reply_reserve'],
                                    'context_budget':row['context_budget'], 'session':self.get(sid), 'new_session':self.get(new_sid)}
                    if event.is_set():
                        raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                    result = engine.generate(messages, row['reply_reserve'], event)
                with self._lock, connect(self.db_path) as conn, transaction(conn):
                    if event.is_set() or self._row(conn, sid)['status'] != 'OPEN':
                        raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                    content = result.get('content')
                    output = integer(result.get('output_tokens'), 0, row['reply_reserve'])
                    if (result.get('stop_reason') not in {'eosFound', 'stopStringFound', 'stop'} or
                        not isinstance(content, str) or not content.strip() or len(content.encode('utf-8')) > 262144 or
                        type(result.get('input_tokens')) is not int or result['input_tokens'] != tokens or
                        tokens + output > row['context_budget'] or result.get('tool_calls')):
                        raise IntegrationError('INCOMPLETE_RESPONSE', 'Engine did not return an unchanged, complete text reply; no pair was saved.', 502)
                    review_conversation = None
                    if consent[0] and self._consent.get(sid, (False, 0)) == consent:
                        captured = ingest_turn({'conversation_id': f'najdilab-chat:{sid}:{consent[1]}',
                            'title':'NajdiLab Chat collected segment' + (' — earlier context excluded' if len(messages)>1 else ''),
                            'source':'najdilab_chat', 'channel':'web', 'provider':row['provider'], 'model_name':row['model'],
                            'user_message':text, 'assistant_response':content, 'source_message_id':request_id,
                            'metadata':{'origin':'najdilab_chat','chat_session_id':sid,'chat_request_id':request_id,
                                        'context_scope':'continuous_consented_segment_only','model_key':fingerprint,
                                        'engine_version':measured.get('engine_version'),'context_budget':row['context_budget'],
                                        'reasoning_discarded':bool(result.get('reasoning_discarded'))},
                        }, self.db_path, _connection=conn, _preserve_text=True)
                        review_conversation = captured['conversation_id']
                    ordinal = len(messages) // 2
                    conn.execute('INSERT INTO chat_turns VALUES(?,?,?,?,?,?,?,?,?)',
                        (sid, request_id, ordinal, text, content, tokens, output, review_conversation, utc_now()))
                    conn.execute("UPDATE chat_requests SET status='COMPLETED' WHERE session_id=? AND request_id=?", (sid, request_id))
                    conn.execute('UPDATE chat_sessions SET revision=revision+1,updated_at=? WHERE id=?', (utc_now(), sid))
                    conn.execute("""INSERT INTO chat_session_bindings(session_id,model_fingerprint) VALUES(?,?)
                        ON CONFLICT(session_id) DO UPDATE SET model_fingerprint=excluded.model_fingerprint""", (sid, fingerprint))
            with self._lock:
                self._active.pop(sid, None)
                return {'status':'COMPLETED', 'duplicate':False, 'session':self.get(sid)}
        except Exception:
            with self._lock, connect(self.db_path) as conn:
                conn.execute("UPDATE chat_requests SET status=? WHERE session_id=? AND request_id=? AND status='RUNNING'",
                             ('STOPPED' if event.is_set() else 'FAILED', sid, request_id))
            raise
        finally:
            with self._lock:
                self._active.pop(sid, None)
