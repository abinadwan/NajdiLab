"""Phase C / AI-05: independent acceptance of Chat collection privacy.

Synthetic data and a synthetic engine only; no installed runtime, model or user database is used.
The contract checked end to end, through the real Chat workspace, review service and exporter:

1. Collection is OFF by default; uncollected Chat text never reaches reviews, training files or
   the full archive of an export.
2. Consent is a separate explicit boolean and is never retrospective.
3. Collected pairs stay PENDING and ineligible until a human approves them; a pair carrying any
   restriction (sensitive, personal, fact-check, evaluation-only, excluded) or from an archived
   conversation can never become training data.
4. Native LM Studio / Ollama conversation stores are never opened or read.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.chat_workspace import ChatWorkspace
from app.db import apply_migrations, connect
from app.integrations import IntegrationError, IntegrationManager
from app.review_integrity import ExportReadinessError
from app.service import add_direct_text, create_export, save_review, training_dataset, ValidationError

OFF_SECRET = 'SYNTH_UNCOLLECTED_7c1e'
ON_SECRET = 'SYNTH_COLLECTED_42b9'
REPLY = 'SYNTH_REPLY_d03a'
NATIVE_SECRET = 'SYNTH_NATIVE_HISTORY_91fe'
RESTRICTIONS = ('contains_sensitive_data', 'contains_personal_data', 'needs_fact_check', 'evaluation_only',
                'exclude_from_training')


class Engine:
    def __init__(self):
        self.prompts = []

    @contextmanager
    def open(self, spec, model):
        yield self

    def limits(self):
        return {'budget_ceiling': 4096, 'model_max_context': 8192, 'runtime_context': 4096, 'kv': None,
                'weights_bytes': 1000, 'model_key': 'fixture'}

    def measure(self, messages, budget, stop=None):
        self.prompts.append([m['content'] for m in messages])
        self.seen = 10 + len(messages)
        return {'input_tokens': self.seen, 'loaded_context': 4096, 'model_key': 'fixture'}

    def generate(self, messages, reserve, stop):
        return {'content': REPLY + ' ' + str(len(messages)), 'stop_reason': 'eosFound', 'input_tokens': self.seen,
                'output_tokens': 3}


@pytest.fixture
def chat(tmp_path):
    db = tmp_path / 'ai05.db'
    apply_migrations(db)
    # One unrelated approved record, so an export is possible whenever no decision is pending.
    add_direct_text({'text': 'نص يدوي اصطناعي', 'language_layer': 'msa', 'source_type': 'human_written',
                     'origin': 'manual', 'training_eligible': True}, db)
    manager = IntegrationManager(home=tmp_path / 'home')
    manager._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', models=['fixture'], selection_revision=2)
    engine = Engine()
    ws = ChatWorkspace(manager, db, engine_factory=engine.open)
    try:
        yield ws, engine, db, tmp_path
    finally:
        ws.close()


def _new(ws):
    return ws.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2, 'context_budget': 512,
                      'reply_reserve': 32, 'load_approved': False})


def _send(ws, session, text):
    return ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                   'selection_revision': 2, 'text': text})['session']


def _collect(ws, session, enabled=True):
    return ws.collect(session['id'], {'enabled': enabled, 'revision': session['revision']})


def _reviews(db):
    with connect(db) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT r.*, (SELECT content FROM messages u WHERE u.conversation_id=m.conversation_id AND u.role='user' "
            "AND u.turn_index<m.turn_index ORDER BY u.turn_index DESC LIMIT 1) AS user_text "
            "FROM reviews r JOIN messages m ON m.id=r.message_id ORDER BY r.id")]


def _export(db, out: Path) -> tuple[dict[str, str], str]:
    """Return ({training file: text}, full archive) of a fresh export."""
    folder = Path(create_export(db, out)['path'])
    files = {p.name: p.read_text(encoding='utf-8') for p in sorted(folder.glob('*.jsonl'))}
    return files, (folder / 'full_archive.json').read_text(encoding='utf-8')


def _training_only(files: dict[str, str]) -> str:
    # evaluation_holdout.jsonl is the evaluation split, never a training file.
    return ''.join(text for name, text in files.items() if name != 'evaluation_holdout.jsonl')


def _selected(db) -> str:
    return json.dumps(training_dataset(db), ensure_ascii=False)


def test_collection_is_off_by_default_and_uncollected_chat_never_leaves_chat_storage(chat):
    ws, engine, db, tmp = chat
    session = _new(ws)
    assert session['collect'] is False, 'collection is OFF for a new conversation'
    session = _send(ws, session, OFF_SECRET)
    assert session['turns'][0]['user'] == OFF_SECRET, 'the raw turn is kept in Chat history'
    assert _reviews(db) == []
    assert OFF_SECRET not in _selected(db)
    files, archive = _export(db, tmp / 'exports')
    assert OFF_SECRET not in ''.join(files.values()) and OFF_SECRET not in archive, 'uncollected Chat is not part of any export'
    with connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM messages WHERE content LIKE ?', ('%' + OFF_SECRET + '%',)).fetchone()[0] == 0


@pytest.mark.parametrize('enabled', [1, 'true', 'yes', None])
def test_consent_requires_an_explicit_boolean(chat, enabled):
    ws, _, _, _ = chat
    session = _new(ws)
    with pytest.raises(IntegrationError) as caught:
        ws.collect(session['id'], {'enabled': enabled, 'revision': session['revision']})
    assert caught.value.code == 'CONSENT_REQUIRED'
    assert ws.get(session['id'])['collect'] is False


def test_consent_is_never_retrospective_and_collected_pairs_wait_for_a_human(chat):
    ws, _, db, tmp = chat
    session = _send(ws, _new(ws), OFF_SECRET)
    session = _collect(ws, session)
    assert session['collect'] is True
    session = _send(ws, session, ON_SECRET)
    reviews = _reviews(db)
    assert len(reviews) == 1, 'only the consented turn is copied'
    review = reviews[0]
    assert review['user_text'] == ON_SECRET
    with connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM messages WHERE content=?', (OFF_SECRET,)).fetchone()[0] == 0, \
            'earlier OFF history is not imported as review context'
    assert review['review_status'] == 'PENDING' and review['training_eligible'] == 0
    assert ON_SECRET not in _selected(db), 'a collected pair is not training data before review'
    with pytest.raises(ExportReadinessError) as blocked:
        create_export(db, tmp / 'before')
    assert 'REVIEW_PENDING' in str(blocked.value), 'an undecided collected pair blocks every export'
    assert not (tmp / 'before').exists() or not any((tmp / 'before').iterdir())

    with pytest.raises(ValidationError, match='Earlier chat context'):
        save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
    save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': False}, db)
    assert ON_SECRET not in _selected(db), 'human review cannot manufacture the missing pre-consent context'

    session = _collect(ws, session, enabled=False)
    _send(ws, session, OFF_SECRET + '-after')
    assert len(_reviews(db)) == 1, 'turning collection OFF stops copying at once'


@pytest.mark.parametrize('restriction', RESTRICTIONS)
def test_restricted_collected_pair_is_never_training_eligible(chat, restriction):
    ws, _, db, tmp = chat
    session = _collect(ws, _new(ws))
    _send(ws, session, ON_SECRET)
    review = _reviews(db)[0]
    save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True,
                               restriction: True}, db)
    stored = _reviews(db)[0]
    assert stored[restriction] == 1 and stored['training_eligible'] == 0, 'a restriction always wins over eligibility'
    # A later save that omits the restriction keeps it (restrictions are never cleared implicitly).
    save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
    stored = _reviews(db)[0]
    assert stored[restriction] == 1 and stored['training_eligible'] == 0
    selected = training_dataset(db)
    assert ON_SECRET not in json.dumps({k: v for k, v in selected.items() if k != 'stats'}, ensure_ascii=False)
    files, _ = _export(db, tmp / 'exports')
    assert ON_SECRET not in _training_only(files)


def test_archived_chat_pair_cannot_become_eligible_again(chat):
    ws, _, db, tmp = chat
    session = _collect(ws, _new(ws))
    session = _send(ws, session, ON_SECRET)
    review = _reviews(db)[0]
    save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
    assert ON_SECRET in _selected(db)
    ws.archive(session['id'], {'revision': session['revision']})
    stored = _reviews(db)[0]
    assert stored['training_eligible'] == 0 and stored['exclude_from_training'] == 1
    assert ON_SECRET not in _selected(db)
    with pytest.raises(sqlite3.IntegrityError, match='Archived chat cannot become training eligible'):
        save_review(review['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True,
                                   'exclude_from_training': False}, db)
    with connect(db) as conn, pytest.raises(sqlite3.DatabaseError):
        conn.execute('UPDATE reviews SET training_eligible=1, exclude_from_training=0 WHERE id=?', (review['id'],))
    assert ON_SECRET not in _selected(db)
    files, _ = _export(db, tmp / 'exports')
    assert ON_SECRET not in _training_only(files)


@pytest.fixture
def native_stores(tmp_path):
    """Synthetic native chat stores where LM Studio and Ollama keep conversations."""
    home = tmp_path / 'home'
    stores = [home / '.lmstudio' / 'conversations', home / '.ollama' / 'history', home / '.cache' / 'lm-studio' / 'conversations']
    for store in stores:
        store.mkdir(parents=True)
        (store / 'chat.json').write_text(json.dumps({'messages': [{'role': 'user', 'content': NATIVE_SECRET}]}),
                                         encoding='utf-8')
    return home, stores


_TOUCHED: list[str] | None = None


def _audit(event, args):
    if _TOUCHED is None or event not in {'open', 'os.listdir', 'os.scandir', 'glob.glob'}:
        return
    if args and isinstance(args[0], (str, bytes, Path)):
        _TOUCHED.append(str(args[0] if not isinstance(args[0], bytes) else args[0].decode(errors='replace')))


sys.addaudithook(_audit)


def test_native_runtime_chat_stores_are_never_read(chat, native_stores):
    global _TOUCHED
    ws, _, db, tmp = chat
    home, stores = native_stores
    manager = IntegrationManager(home=home)
    _TOUCHED = []
    try:
        discovered = manager.discover()
        session = _collect(ws, _new(ws))
        _send(ws, session, ON_SECRET)
        save_review(_reviews(db)[0]['id'], {'review_status': 'APPROVED', 'reviewer': 'human', 'training_eligible': True}, db)
        _export(db, tmp / 'exports')
        touched = list(_TOUCHED)
    finally:
        _TOUCHED = None
    assert {item['id'] for item in discovered['items']} >= {'lmstudio', 'ollama'}
    assert touched, 'the audit hook observed file access (it is not silently inactive)'
    roots = [str(store) for store in stores]
    assert not [path for path in touched if any(path.startswith(root) for root in roots)], \
        'native conversation stores were opened or listed'
    assert NATIVE_SECRET not in json.dumps(discovered)
    with connect(db) as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            for column in columns:
                hit = conn.execute(f'SELECT count(*) FROM "{table}" WHERE CAST("{column}" AS TEXT) LIKE ?',
                                   ('%' + NATIVE_SECRET + '%',)).fetchone()[0]
                assert hit == 0, (table, column)
