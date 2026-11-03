"""NajdiLab-owned raw chat sessions. Native application histories are never read."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import threading
import time
from uuid import UUID, uuid4

from . import chat_deletion
from .chat_history import suggest_title
from .db import DB_PATH, ROOT, connect as db_connect, transaction, utc_now
from .hardware import snapshot as hardware_snapshot
from .integrations import IntegrationError
from .service import ingest_turn

PROVIDERS = {'lmstudio', 'ollama', 'native'}
STOP_REASONS = {'eosFound', 'stopStringFound', 'stop'}
# INCOMPLETE_RESPONSE reconciliation (PR #21 95e7604 + PR #22): the message is
# PR #21's fixed per-predicate text; `check` names the predicate (PR #22) and an
# optional fixed `hint` says what to do. None of them contains prompt, reply or
# thinking text.
INCOMPLETE_CHECKS = {
    'STOP_REASON_LENGTH': ('The engine did not finish the reply normally; no pair was saved.',
                           'The reply reached the reserved reply limit before it finished. Thinking tokens count toward this limit, so thinking models need a larger reserve. Start a new chat with a larger reply reserve.'),
    'STOP_REASON_OTHER': ('The engine did not finish the reply normally; no pair was saved.', None),
    'EMPTY_CONTENT': ('The engine returned empty, invalid or oversized final text; no pair was saved.',
                      'The final answer was empty (the model may have produced only thinking).'),
    'TOO_LARGE': ('The engine returned empty, invalid or oversized final text; no pair was saved.', None),
    'PROMPT_TOKENS_MISMATCH': ('The final prompt token count differed from the measured prompt; no pair was saved.', None),
    'OVER_BUDGET': ('The final token usage exceeded the conversation budget; no pair was saved.', None),
    'TOOL_CALLS': ('The engine returned tool calls instead of a plain text reply; no pair was saved.', None),
}


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


def incomplete(check):
    message, hint = INCOMPLETE_CHECKS[check]
    error = IntegrationError('INCOMPLETE_RESPONSE', message, 502)
    error.check, error.hint = check, hint
    return error


def completion_check(result, tokens, output, budget):
    """Returns the first failed completion predicate, or None. Order is fixed."""
    content = result.get('content')
    reason = result.get('stop_reason')
    if reason not in STOP_REASONS:
        return 'STOP_REASON_LENGTH' if reason in {'length', 'maxPredictedTokensReached'} else 'STOP_REASON_OTHER'
    if not isinstance(content, str) or not content.strip():
        return 'EMPTY_CONTENT'
    if len(content.encode('utf-8')) > 262144:
        return 'TOO_LARGE'
    if type(result.get('input_tokens')) is not int or result['input_tokens'] != tokens:
        return 'PROMPT_TOKENS_MISMATCH'
    if tokens + output > budget:
        return 'OVER_BUDGET'
    if result.get('tool_calls'):
        return 'TOOL_CALLS'
    return None


def ms(start):
    return int((time.monotonic() - start) * 1000)


class ChatWorkspace:
    def __init__(self, integrations, db_path=DB_PATH, *, engine_factory=None, native=None,
                 artifact_roots=None, backups_root=None):
        self.integrations, self.db_path = integrations, Path(db_path)
        self.native = native
        # Deletion refuses while any of these hold a copy; backups are only counted.
        self.artifact_roots = [Path(p) for p in (artifact_roots if artifact_roots is not None else
                               (ROOT / 'exports', ROOT / 'datasets', ROOT / 'reports'))]
        self.backups_root = Path(backups_root) if backups_root is not None else ROOT / 'backups'
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
            row['display_title'] = row['title'] or (suggest_title(row['turns'][0]['user']) if row['turns'] else None)
            return row

    def list(self):
        with self._lock, connect(self.db_path) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM chat_sessions WHERE status!='ARCHIVED' ORDER BY updated_at DESC LIMIT 200")]

    def _lease(self, provider, model, revision):
        if provider == 'native':
            if self.native is None:
                raise IntegrationError('NATIVE_UNAVAILABLE', 'NajdiLab Native is not available in this process.', 409)
            return self.native.chat_lease(model, revision)
        return self.integrations.chat_lease(provider, model, revision)

    def _insert_session(self, conn, data):
        sid, now = str(uuid4()), utc_now()
        conn.execute("""INSERT INTO chat_sessions(id,provider,model,context_budget,reply_reserve,created_at,updated_at,last_activity_at)
                        VALUES(?,?,?,?,?,?,?,?)""",
                     (sid, data['provider'], data['model'], data['context_budget'], data['reply_reserve'], now, now, now))
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
        if not isinstance(data['provider'], str) or data['provider'] not in PROVIDERS:
            raise IntegrationError("UNKNOWN_PROVIDER", "Choose an approved local runtime.")
        if type(data['load_approved']) is not bool or (data['load_approved'] and data['provider'] != 'ollama'):
            raise IntegrationError("INVALID_PAYLOAD", "Load approval applies only to Ollama, which loads models on request.")
        if data['provider'] == 'ollama' and not data['load_approved']:
            raise IntegrationError("LOAD_APPROVAL_REQUIRED", "Approve Ollama loading this model at the selected context first.", 403)
        with self._lease(data['provider'], data['model'], data['selection_revision']) as spec:
            with self.engine_factory(spec, data['model']) as engine:
                limits = engine.limits()
            ceiling = limits.get('budget_ceiling')
            if type(ceiling) is not int or ceiling < 1:
                raise IntegrationError("CONTEXT_UNKNOWN", "The runtime did not report a context limit, so the budget cannot be proven.", 409)
            if data['context_budget'] > ceiling:
                raise IntegrationError("ENGINE_CONTEXT_LIMIT", f"This model allows at most {ceiling} tokens of context here; choose a smaller budget.", 409)
            fingerprint = limits.get('model_key')
            if data['provider'] in {'ollama', 'native'} and (not isinstance(fingerprint, str) or not fingerprint):
                raise IntegrationError('MODEL_REFERENCE_UNVERIFIED', 'Model identity could not be fixed; Chat is blocked.', 409)
            with self._lock:
                return self._create({**data, 'model_fingerprint':fingerprint if isinstance(fingerprint, str) else None})

    def hardware(self, data):
        """Device evidence, plus model evidence when a selected model is named."""
        if set(data) == {'approved'}:
            return hardware_snapshot()
        if set(data) == {'approved', 'native_model'} and self.native is not None:
            # Estimate for a GGUF file that is not loaded; nothing is started.
            return hardware_snapshot(self.native.model_limits(data['native_model']))
        fields(data, {'approved','provider','model','selection_revision'})
        try:
            with self._lease(data['provider'], data['model'], data['selection_revision']) as spec:
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
            if row['status'] == 'ARCHIVED':
                raise IntegrationError("ALREADY_ARCHIVED", "This conversation is already archived.", 409)
            if sid in self._active:
                self._active[sid].set()
            now = utc_now()
            conn.execute("""UPDATE chat_sessions SET status='ARCHIVED',archived_at=?,archived_from_status=?,
                            revision=revision+1,updated_at=? WHERE id=?""", (now, row['status'], now, sid))
            conn.execute('''UPDATE reviews SET training_eligible=0,exclude_from_training=1,updated_at=?
                WHERE message_id IN (SELECT id FROM messages WHERE conversation_id IN
                (SELECT review_conversation_id FROM chat_turns WHERE session_id=?))''', (utc_now(), sid))
            self._consent[sid] = False, uuid4().hex
        return self.get(sid)

    def restore(self, sid, data):
        """Un-archive. Earlier collected pairs stay excluded (a new human decision
        is required) and collection stays off; send-time gates are unchanged."""
        fields(data, {'revision'})
        with self._lock, connect(self.db_path) as conn, transaction(conn):
            row = self._row(conn, sid)
            self._expected(row, data['revision'])
            if row['status'] != 'ARCHIVED':
                raise IntegrationError("NOT_ARCHIVED", "Only an archived conversation can be restored.", 409)
            conn.execute("""UPDATE chat_sessions SET status=COALESCE(archived_from_status,'OPEN'),archived_at=NULL,
                            archived_from_status=NULL,revision=revision+1,updated_at=? WHERE id=?""", (utc_now(), sid))
            self._consent[sid] = False, uuid4().hex
        return self.get(sid)

    def rename(self, sid, data):
        """Display metadata only: does not change history or the send revision."""
        fields(data, {'title'})
        title = data['title']
        if title is not None:
            if not isinstance(title, str) or not title.strip():
                raise IntegrationError("INVALID_TITLE", "Enter a title, or clear it to use the automatic one.")
            title = ' '.join(title.split())
            if len(title) > 120:
                raise IntegrationError("INVALID_TITLE", "Titles are limited to 120 characters.")
        with self._lock, connect(self.db_path) as conn, transaction(conn):
            self._row(conn, sid)
            if title is None:
                first = conn.execute('SELECT user_content FROM chat_turns WHERE session_id=? ORDER BY ordinal LIMIT 1', (sid,)).fetchone()
                auto = suggest_title(first[0]) if first else None
                conn.execute('UPDATE chat_sessions SET title=?,title_source=? WHERE id=?', (auto, 'auto' if auto else None, sid))
            else:
                conn.execute("UPDATE chat_sessions SET title=?,title_source='manual' WHERE id=?", (title, sid))
        return self.get(sid)

    def pin(self, sid, data):
        fields(data, {'pinned'})
        if type(data['pinned']) is not bool:
            raise IntegrationError("INVALID_PAYLOAD", "pinned must be true or false.")
        with self._lock, connect(self.db_path) as conn, transaction(conn):
            self._row(conn, sid)
            conn.execute('UPDATE chat_sessions SET pinned_at=? WHERE id=?', (utc_now() if data['pinned'] else None, sid))
        return self.get(sid)

    def delete_preview(self, sid):
        with self._lock, connect(self.db_path) as conn:
            row = self._row(conn, sid)
            preview = chat_deletion.plan(conn, row, self.artifact_roots, self.backups_root)
            preview['busy'] = sid in self._active or preview['running'] > 0
            preview['revision'] = row['revision']
            return preview

    def delete(self, sid, data):
        """Permanent deletion (see app/chat_deletion.py for the declared scope).

        Requires the exact confirmation word and the current revision, and is
        refused while a turn is active or a copy exists in NajdiLab's exports.
        """
        fields(data, {'revision', 'confirm'})
        if data['confirm'] != chat_deletion.CONFIRMATION:
            raise IntegrationError("DELETE_CONFIRMATION_REQUIRED", "Type DELETE to confirm permanent deletion.", 400)
        with self._lock:
            if sid in self._active:
                raise IntegrationError("CHAT_BUSY", "Stop the running reply and wait for it to end before deleting.", 409)
            with connect(self.db_path) as conn:
                # Freed pages are overwritten with zeros, not just unlinked.
                conn.execute('PRAGMA secure_delete = ON')
                with transaction(conn):
                    row = self._row(conn, sid)
                    self._expected(row, data['revision'])
                    preview = chat_deletion.plan(conn, row, self.artifact_roots, self.backups_root)
                    if preview['running']:
                        raise IntegrationError("CHAT_BUSY", "A reply is still recorded as running; wait for it to end before deleting.", 409)
                    if preview['blocked'] == 'EXPORTED':
                        error = IntegrationError("DELETE_BLOCKED_EXPORTED", "This conversation is already in NajdiLab exports or dataset folders, which are never rewritten. Archive it instead; nothing was deleted.", 409)
                        error.check = 'EXPORTED'
                        raise error
                    done = chat_deletion.execute(conn, row, preview)
            self._consent.pop(sid, None)
        wal = chat_deletion.compact(self.db_path)
        return {'ok': True, 'deleted': sid, 'policy': chat_deletion.POLICY, 'turns_deleted': preview['turns'],
                **done, 'review_events_retained': preview['review_events_retained'],
                'backups_not_changed': preview['backups_not_changed'], 'wal_checkpoint': wal}

    def send(self, sid, data, on_event=None):
        """One turn. `on_event` (streaming) receives phase/delta/timing events;
        nothing it receives is saved, and only a verified, complete reply is
        committed. Without it the behavior is the original request/response."""
        emit = on_event or (lambda event: None)
        timings = {}
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
            if row['provider'] in {'ollama', 'native'} and not row['model_fingerprint']:
                raise IntegrationError("MODEL_BINDING_REQUIRED", "This session has no verified model identity. Start a new chat.", 409)
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
            turns = self.get(sid)['turns']
            for turn in turns:
                messages.extend([{'role':'user','content':turn['user']}, {'role':'assistant','content':turn['assistant']}])
                previous_input = turn['input_tokens']
            messages.append({'role':'user','content':text})
        try:
            emit({'type':'accepted', 'request_id':request_id})
            started = time.monotonic()
            emit({'type':'phase', 'phase':'engine_check'})
            with self._lease(row['provider'], row['model'], data['selection_revision']) as spec:
                with self.engine_factory(spec, row['model']) as engine:
                    timings['engine_check_ms'] = ms(started)
                    if row['provider'] in {'ollama', 'native'}:
                        engine.expected_model_key = row['model_fingerprint']
                    emit({'type':'phase', 'phase':'admission'})
                    started = time.monotonic()
                    measured = engine.measure(messages, row['context_budget'], event)
                    timings['admission_ms'] = ms(started)
                    if isinstance(measured.get('timings'), dict):
                        timings['admission'] = measured['timings']
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
                    emit({'type':'admitted', 'input_tokens':tokens, 'reply_reserve':row['reply_reserve'], 'context_budget':row['context_budget']})
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
                                    'context_budget':row['context_budget'], 'session':self.get(sid), 'new_session':self.get(new_sid),
                                    'timings':timings}
                    if event.is_set():
                        raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                    emit({'type':'phase', 'phase':'waiting_first_token'})
                    started = time.monotonic()
                    if on_event is None:
                        result = engine.generate(messages, row['reply_reserve'], event)
                    else:
                        phase = {'now':'waiting_first_token'}

                        def delta(channel, value):
                            wanted = 'thinking' if channel == 'thinking' else 'answering'
                            if phase['now'] != wanted:
                                phase['now'] = wanted
                                emit({'type':'phase', 'phase':wanted})
                            emit({'type':channel, 'text':value})
                        result = engine.generate(messages, row['reply_reserve'], event, on_delta=delta)
                    timings['generation_total_ms'] = ms(started)
                    if isinstance(result.get('timings'), dict):
                        timings['generation'] = result['timings']
                emit({'type':'phase', 'phase':'verifying'})
                started = time.monotonic()
                with self._lock, connect(self.db_path) as conn, transaction(conn):
                    if event.is_set() or self._row(conn, sid)['status'] != 'OPEN':
                        raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
                    content = result.get('content')
                    output = integer(result.get('output_tokens'), 0, row['reply_reserve'])
                    check = completion_check(result, tokens, output, row['context_budget'])
                    if check:
                        raise incomplete(check)
                    review_conversation = None
                    ordinal = len(messages) // 2
                    if consent[0] and self._consent.get(sid, (False, 0)) == consent:
                        review_conversation = self._collect(conn, sid, row, consent, turns, text, content, request_id,
                                                            fingerprint, measured, result)
                    conn.execute('INSERT INTO chat_turns VALUES(?,?,?,?,?,?,?,?,?)',
                        (sid, request_id, ordinal, text, content, tokens, output, review_conversation, utc_now()))
                    conn.execute("UPDATE chat_requests SET status='COMPLETED' WHERE session_id=? AND request_id=?", (sid, request_id))
                    now = utc_now()
                    conn.execute('UPDATE chat_sessions SET revision=revision+1,updated_at=?,last_activity_at=? WHERE id=?', (now, now, sid))
                    if ordinal == 0:
                        auto = suggest_title(text)
                        if auto:
                            conn.execute("UPDATE chat_sessions SET title=?,title_source='auto' WHERE id=? AND title IS NULL", (auto, sid))
                    conn.execute("""INSERT INTO chat_session_bindings(session_id,model_fingerprint) VALUES(?,?)
                        ON CONFLICT(session_id) DO UPDATE SET model_fingerprint=excluded.model_fingerprint""", (sid, fingerprint))
                timings['verify_commit_ms'] = ms(started)
            with self._lock:
                self._active.pop(sid, None)
                return {'status':'COMPLETED', 'duplicate':False, 'session':self.get(sid), 'timings':timings,
                        'thinking_shown':bool(result.get('reasoning_discarded'))}
        except Exception:
            with self._lock, connect(self.db_path) as conn:
                conn.execute("UPDATE chat_requests SET status=? WHERE session_id=? AND request_id=? AND status='RUNNING'",
                             ('STOPPED' if event.is_set() else 'FAILED', sid, request_id))
            raise
        finally:
            with self._lock:
                self._active.pop(sid, None)

    def _collect(self, conn, sid, row, consent, turns, text, content, request_id, fingerprint, measured, result):
        """Consented segment only: never earlier turns, thinking or partial text.

        Reconciled with PR #21: `context_complete` is true only when the segment
        starts at the conversation's first turn. Review, export readiness and
        both exporters then refuse incomplete segments for training/evaluation.

        A segment is the run of turns collected under one consent epoch. Its
        first collected turn is `single_turn`; each later one links to the
        previous collected answer (`multi_turn`). Whether the segment began
        mid-conversation is recorded, because such answers may depend on
        context that was deliberately not collected.
        """
        base = f'najdilab-chat:{sid}:{consent[1]}'
        conversation_key = base
        previous = conn.execute(
            """SELECT t.request_id, t.ordinal, c.external_conversation_id AS key FROM chat_turns t
               JOIN conversations c ON c.id=t.review_conversation_id
               WHERE t.session_id=? AND (c.external_conversation_id=? OR c.external_conversation_id LIKE ?)
               ORDER BY t.ordinal DESC LIMIT 1""",
            (sid, base, base + ':%')).fetchone()
        ordinal = len(turns)
        if previous is not None and previous['ordinal'] == ordinal - 1:
            conversation_key = previous['key']
        elif previous is not None:
            # A non-collected turn broke the segment: start a fresh one so a
            # collected record can never silently skip context.
            conversation_key = f'{base}:{ordinal}'
            previous = None
        segment_start = ordinal if previous is None else conn.execute(
            """SELECT MIN(t.ordinal) FROM chat_turns t JOIN conversations c ON c.id=t.review_conversation_id
               WHERE t.session_id=? AND c.external_conversation_id=?""", (sid, conversation_key)).fetchone()[0]
        payload = {'conversation_id': conversation_key,
            'title':'NajdiLab Chat collected segment' + (' — earlier context excluded' if segment_start > 0 else ''),
            'source':'najdilab_chat', 'channel':'web', 'provider':row['provider'], 'model_name':row['model'],
            'user_message':text, 'assistant_response':content, 'source_message_id':request_id,
            'metadata':{'origin':'najdilab_chat','chat_session_id':sid,'chat_request_id':request_id,
                        'context_scope':'continuous_consented_segment_only','model_key':fingerprint,
                        'engine_version':measured.get('engine_version'),'context_budget':row['context_budget'],
                        'collection_mode':'multi_turn' if previous is not None else 'single_turn',
                        'segment_turn':ordinal - segment_start + 1,
                        'earlier_turns_excluded':segment_start,
                        'depends_on_excluded_context':segment_start > 0,
                        # PR #21 (95e7604) gate: only a segment collected from the
                        # first turn has complete consented context; anything else
                        # stays reviewable but is blocked from training/evaluation.
                        'context_complete':segment_start == 0,
                        'thinking_collected':False,
                        'reasoning_discarded':bool(result.get('reasoning_discarded'))}}
        if previous is not None:
            payload['reply_to_source_message_id'] = previous['request_id']
        captured = ingest_turn(payload, self.db_path, _connection=conn, _preserve_text=True)
        return captured['conversation_id']
