"""Consent and SFT context tests using synthetic databases and archives only."""
import json
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from app.db import apply_migrations, connect
from app import service
from app.clean_export import ArchiveIndex, reconstruct_review_record, validate_clean_records
from app.review_integrity import ExportReadinessError
from app.chat_workspace import ChatWorkspace
from app.integrations import IntegrationManager


def capture(db, *, complete=True, question='question', answer='answer'):
    metadata = {'origin': 'najdilab_chat', 'context_scope': 'continuous_consented_segment_only'}
    if complete is not None:
        metadata['context_complete'] = complete
    return service.ingest_turn({'conversation_id': 'chat-synthetic', 'source': 'najdilab_chat',
        'user_message': question, 'assistant_response': answer, 'metadata': metadata}, db, _preserve_text=True)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'synthetic.db'
    apply_migrations(path)
    return path


@pytest.mark.parametrize('complete', [False, None])
@pytest.mark.parametrize('flag', ['training_eligible', 'evaluation_only'])
def test_incomplete_chat_can_be_reviewed_but_cannot_be_promoted(db, complete, flag):
    turn = capture(db, complete=complete)
    review = service.get_review(turn['review_id'], db)
    assert review['context_complete'] is False
    assert review['context_warning']
    with pytest.raises(service.ValidationError, match='context'):
        service.approve_review(turn['review_id'], {flag: True}, db)
    saved = service.approve_review(turn['review_id'], {}, db)
    assert saved['review_status'] == 'APPROVED'
    assert saved['training_eligible'] == saved['evaluation_only'] == 0


def test_export_backstop_rejects_legacy_incomplete_promotion(db, tmp_path):
    turn = capture(db, complete=False)
    service.approve_review(turn['review_id'], {}, db)
    with connect(db) as conn:
        conn.execute('UPDATE reviews SET training_eligible=1')
    with pytest.raises(ExportReadinessError, match='context'):
        service.create_export(db, exports_dir=tmp_path / 'exports')
    assert not list((tmp_path / 'exports').glob('gold-*'))


def test_chat_clean_export_preserves_actual_prefix_and_only_corrects_target(db, tmp_path):
    first = capture(db, question='  prior user  ', answer='  actual prior answer  ')
    service.correct_review(first['review_id'], {'review_status': 'CONTENT_CORRECTION',
        'corrected_response': 'a different prior gold'}, db)
    last = capture(db, question='  follow up  ', answer='original target')
    service.correct_review(last['review_id'], {'review_status': 'CONTENT_CORRECTION',
        'corrected_response': 'approved target', 'training_eligible': True}, db)
    exported = service.create_export(db, exports_dir=tmp_path / 'exports')
    directory = tmp_path / 'exports' / exported['version']
    source = json.loads((directory / 'multi_turn.jsonl').read_text(encoding='utf-8'))
    assert source['messages'] == [
        {'role': 'user', 'content': '  prior user  '},
        {'role': 'assistant', 'content': '  actual prior answer  '},
        {'role': 'user', 'content': '  follow up  '},
        {'role': 'assistant', 'content': 'approved target'}]
    assert source['message_loss_mask'] == [0, 0, 0, 1]
    index = ArchiveIndex(json.loads((directory / 'full_archive.json').read_text(encoding='utf-8')))
    clean, audit, error = reconstruct_review_record(index, index.reviews[last['review_id']])
    assert error is None
    assert clean['messages'] == source['messages']
    assert clean['message_loss_mask'] == [0, 0, 0, 1]
    assert not audit.context_trimmed and audit.prior_assistant_gold_replacements == 0
    validate_clean_records([clean], [], index, {'max_multi_turn_records_per_conversation_after': 1})


@pytest.mark.parametrize('restriction', ['contains_personal_data', 'contains_sensitive_data', 'exclude_from_training'])
def test_chat_clean_reconstruction_cannot_trim_private_prefix(db, restriction):
    first = capture(db)
    service.approve_review(first['review_id'], {restriction: True}, db)
    last = capture(db, question='followup', answer='target')
    service.approve_review(last['review_id'], {'training_eligible': True}, db)
    with connect(db) as conn:
        archive = {name: [dict(row) for row in conn.execute('SELECT * FROM ' + name)]
                   for name in ('conversations', 'messages', 'reviews')}
    index = ArchiveIndex(archive)
    clean, _, error = reconstruct_review_record(index, index.reviews[last['review_id']])
    assert clean is None and error == 'chat_context_private_or_excluded'


@pytest.mark.parametrize('start_off', [False, True])
def test_raw_chat_to_review_exports_single_and_multi_turn_with_completion_only_loss(db, tmp_path, monkeypatch, start_off):
    from app import dataset_platform
    from app.unsloth_export import create_handoff

    class Engine:
        @contextmanager
        def open(self, spec, model):
            yield self

        def limits(self):
            return {'budget_ceiling': 4096, 'model_key': 'synthetic'}

        def measure(self, messages, budget, stop):
            self.tokens = len(messages) * 10
            return {'input_tokens': self.tokens, 'loaded_context': 4096, 'model_key': 'synthetic'}

        def generate(self, messages, reserve, stop):
            return {'input_tokens': self.tokens, 'output_tokens': 3, 'stop_reason': 'stop',
                    'content': '  actual answer ' + str(len(messages)) + '\n'}

    manager = IntegrationManager(home=tmp_path)
    manager._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture',
        models=['fixture'], selection_revision=2)
    engine = Engine()
    workspace = ChatWorkspace(manager, db, engine_factory=engine.open)
    try:
        session = workspace.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
            'context_budget': 512, 'reply_reserve': 32, 'load_approved': False})
        if start_off:
            session = workspace.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                'selection_revision': 2, 'text': 'PRIVATE BEFORE CONSENT'})['session']
        session = workspace.collect(session['id'], {'enabled': True, 'revision': session['revision']})
        for text in ('  initial user\n', '  followup user\n'):
            session = workspace.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                'selection_revision': 2, 'text': text})['session']
    finally:
        workspace.close()
    queue = service.list_review_queue(db)
    if start_off:
        assert len(queue) == 2 and all(item['context_complete'] is False for item in queue)
        assert 'PRIVATE BEFORE CONSENT' not in str(queue)
        for item in queue:
            with pytest.raises(service.ValidationError, match='context'):
                service.approve_review(item['id'], {'training_eligible': True}, db)
        return
    assert len(queue) == 2 and all(item['context_complete'] for item in queue)
    assert [len(item['context']) for item in queue] == [2, 4]
    with pytest.raises(ExportReadinessError):
        service.create_export(db, exports_dir=tmp_path / 'exports')
    for item in queue:
        service.approve_review(item['id'], {'training_eligible': True}, db)
    exported = service.create_export(db, exports_dir=tmp_path / 'exports')
    directory = tmp_path / 'exports' / exported['version']
    assert len((directory / 'sft.jsonl').read_text(encoding='utf-8').splitlines()) == 1
    multi = json.loads((directory / 'multi_turn.jsonl').read_text(encoding='utf-8'))
    assert multi['message_loss_mask'] == [0, 0, 0, 1]
    assert [message['content'] for message in multi['messages']] == [
        '  initial user\n', '  actual answer 1\n', '  followup user\n', '  actual answer 3\n']
    monkeypatch.setattr(dataset_platform, 'EXPORTS_DIR', tmp_path / 'exports')
    handoff = create_handoff(exported['version'], output_root=tmp_path / 'handoffs')
    assert handoff['record_count'] == 2
    rows = [json.loads(line) for line in (Path(handoff['directory']) / 'dataset.jsonl').read_text(encoding='utf-8').splitlines()]
    assert rows[1] == {'prompt': multi['messages'][:-1], 'completion': [multi['messages'][-1]]}
    assert handoff['trainer_requirements']['completion_only_loss'] is True
