"""Language metadata as four independent dimensions (V2.2.0 Phase 3). Synthetic data only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import dataset_platform as platform
from app.db import apply_migrations, connect
from app.service import (ValidationError, add_direct_text, add_manual_sft, add_preference_pair, create_export,
                         list_manual_data, update_manual_data)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'najdilab.db'
    apply_migrations(path)
    return path


def _row(db, table, item_id):
    with connect(db) as conn:
        return dict(conn.execute(f'SELECT * FROM {table} WHERE id = ?', (item_id,)).fetchone())


def test_english_text_needs_no_arabic_layer_and_neutral_defaults_force_nothing(db):
    item = add_direct_text({'text': 'A standalone English paragraph.', 'language': 'en', 'style': 'academic', 'domain': 'education',
                            'source_type': 'human_written', 'origin': 'manual'}, db)
    row = _row(db, 'direct_language_texts', item['id'])
    assert (row['language'], row['dialect'], row['style'], row['domain'], row['language_layer']) == ('en', None, 'academic', 'education', None)
    bare = add_manual_sft({'messages': [{'role': 'user', 'content': 'q'}, {'role': 'assistant', 'content': 'a'}], 'origin': 'manual'}, db)
    row = _row(db, 'manual_sft_items', bare['id'])
    assert (row['language'], row['dialect'], row['style'], row['language_layer']) == (None, None, None, None), 'no Najdi or Saudi default'


def test_dialects_follow_the_language_and_custom_values_are_allowed(db):
    with pytest.raises(ValidationError, match='Arabic dialects'):
        add_direct_text({'text': 't', 'language': 'en', 'dialect': 'najdi', 'source_type': 'human_written', 'origin': 'manual'}, db)
    with pytest.raises(ValidationError, match='language before'):
        add_direct_text({'text': 't', 'dialect': 'gulf', 'source_type': 'human_written', 'origin': 'manual'}, db)
    custom = add_direct_text({'text': 'Bonjour', 'language': 'French', 'dialect': 'Québécois', 'style': 'conversational', 'domain': 'Tourism',
                              'source_type': 'human_written', 'origin': 'manual'}, db)
    row = _row(db, 'direct_language_texts', custom['id'])
    assert (row['language'], row['dialect'], row['domain']) == ('French', 'Québécois', 'Tourism')
    with pytest.raises(ValidationError):
        add_direct_text({'text': 't', 'language': '<script>x</script>', 'source_type': 'human_written', 'origin': 'manual'}, db)
    multi = add_preference_pair({'prompt_context': 'سياق', 'rejected_response': 'r', 'preferred_response': 'p', 'origin': 'manual',
                                 'language': 'multilingual', 'dialect': 'najdi'}, db)
    assert _row(db, 'preference_pairs', multi['id'])['dialect'] == 'najdi'


def test_legacy_clients_keep_working_with_the_certain_mapping(db):
    item = add_manual_sft({'messages': [{'role': 'user', 'content': 'وش الأخبار؟'}, {'role': 'assistant', 'content': 'كل شي طيب.'}],
                           'language_layer': 'najdi_riyadh', 'origin': 'manual'}, db)
    row = _row(db, 'manual_sft_items', item['id'])
    assert (row['language_layer'], row['language'], row['dialect']) == ('najdi_riyadh', 'ar', 'najdi_riyadh')
    formal = add_direct_text({'text': 'نص رسمي', 'language_layer': 'formal_arabic', 'source_type': 'human_written', 'origin': 'manual'}, db)
    row = _row(db, 'direct_language_texts', formal['id'])
    assert (row['language'], row['dialect'], row['style']) == ('ar', None, 'formal'), 'the variety is not guessed'
    with pytest.raises(ValidationError):
        add_direct_text({'text': 'x', 'language_layer': 'not_a_layer', 'source_type': 'human_written', 'origin': 'manual'}, db)


def test_edits_are_validated_together_and_filters_match_exactly(db):
    item = add_direct_text({'text': 'نص', 'language': 'ar', 'dialect': 'gulf', 'source_type': 'human_written', 'origin': 'manual'}, db)
    with pytest.raises(ValidationError, match='Arabic dialects'):
        update_manual_data('direct', item['id'], {'language': 'en'}, db)
    update_manual_data('direct', item['id'], {'language': 'en', 'dialect': ''}, db)
    assert (_row(db, 'direct_language_texts', item['id'])['language'], _row(db, 'direct_language_texts', item['id'])['dialect']) == ('en', None)
    add_direct_text({'text': 'english', 'language': 'en', 'source_type': 'human_written', 'origin': 'manual'}, db)
    add_direct_text({'text': 'arabic', 'language': 'ar', 'source_type': 'human_written', 'origin': 'manual'}, db)
    page = list_manual_data({'language': 'ar'}, db)
    assert [i['language'] for i in page['items']] == ['ar']
    assert set(page['facets']['language']) == {'ar'}


def test_metadata_is_exported_as_fields_and_never_written_into_training_text(db, tmp_path, monkeypatch):
    messages = [{'role': 'user', 'content': 'كيف الحال؟'}, {'role': 'assistant', 'content': 'بخير والحمد لله.'}]
    add_manual_sft({'messages': messages, 'language': 'ar', 'dialect': 'najdi', 'style': 'conversational', 'domain': 'general',
                    'origin': 'manual', 'training_eligible': True}, db)
    export = create_export(db, tmp_path / 'exports')
    monkeypatch.setattr(platform, 'EXPORTS_DIR', tmp_path / 'exports')
    row = json.loads((Path(export['path']) / 'sft.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert (row['language'], row['dialect'], row['style'], row['domain']) == ('ar', 'najdi', 'conversational', 'general')
    assert row['messages'] == messages, 'training text is unchanged by its metadata'
    version = json.loads((Path(export['path']) / 'manifest.json').read_text(encoding='utf-8'))['version']
    stats = platform.dataset_health(version)['statistics']
    assert stats['metadata']['language'] == {'ar': 1} and stats['metadata']['dialect'] == {'najdi': 1}
    assert stats['missing_language_metadata'] == 0
