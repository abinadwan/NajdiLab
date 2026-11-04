"""Manual data through the pipeline, diversity statistics and cross-split leakage (V2.2.0 Phase 2).

Synthetic, privacy-safe fixtures only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import dataset_platform as platform
from app.dataset_quality import analyze_directory
from app.db import apply_migrations
from app.service import (ValidationError, add_direct_text, add_manual_sft, add_preference_pair, create_export,
                         list_manual_versions, update_manual_data)
from app.unsloth_export import create_handoff


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'najdilab.db'
    apply_migrations(path)
    return path


def _export(db, tmp_path, monkeypatch):
    exports = tmp_path / 'exports'
    export = create_export(db, exports)
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    directory = Path(export['path'])
    return directory, json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['version']


def test_manual_sft_direct_and_dpo_each_reach_their_own_export_and_only_sft_is_a_training_target(db, tmp_path, monkeypatch):
    # A human-written answer needs no earlier (wrong) model response to be eligible.
    sft = add_manual_sft({'messages': [{'role': 'user', 'content': 'كيف أبدأ؟'}, {'role': 'assistant', 'content': 'ابدأ بخطوة صغيرة.'}],
                          'language_layer': 'msa', 'origin': 'manual', 'training_eligible': True}, db)
    add_direct_text({'text': 'نص لغوي مستقل بلا سؤال وجواب.', 'language_layer': 'msa', 'source_type': 'human_written',
                     'origin': 'manual', 'training_eligible': True}, db)
    add_preference_pair({'prompt_context': 'اشرح الفكرة', 'rejected_response': 'جواب مرفوض', 'preferred_response': 'جواب مفضّل',
                         'origin': 'manual', 'training_eligible': True}, db)
    directory, version = _export(db, tmp_path, monkeypatch)
    read = lambda name: [json.loads(line) for line in (directory / name).read_text(encoding='utf-8').splitlines() if line.strip()]
    sft_rows = read('sft.jsonl')
    assert [r['messages'][-1]['content'] for r in sft_rows] == ['ابدأ بخطوة صغيرة.']
    assert read('direct_language.jsonl')[0]['text'] == 'نص لغوي مستقل بلا سؤال وجواب.'
    assert 'messages' not in read('direct_language.jsonl')[0], 'direct language is not forced into question and answer'
    assert read('preference_pairs.jsonl')[0]['preferred_response'] == 'جواب مفضّل'
    handoff = create_handoff(version, profile='studio_chat', output_root=tmp_path / 'handoffs')
    text = (Path(handoff['directory']) / 'dataset.jsonl').read_text(encoding='utf-8')
    assert handoff['record_count'] == 1 and 'ابدأ بخطوة صغيرة.' in text
    assert 'جواب مرفوض' not in text and 'جواب مفضّل' not in text and 'نص لغوي مستقل' not in text, 'DPO and direct text never enter SFT'
    stats = platform.dataset_health(version)['statistics']
    assert stats['by_type'] == {'sft': 1, 'multi_turn': 0, 'direct_language': 1, 'preference_pairs': 1, 'evaluation': stats['by_type']['evaluation']}
    assert stats['origin'].get('manual') == 3


def test_manual_records_validate_input_and_keep_their_history(db):
    with pytest.raises(ValidationError):
        add_manual_sft({'messages': [{'role': 'user', 'content': 'سؤال فقط'}], 'language_layer': 'msa'}, db)
    with pytest.raises(ValidationError):
        add_preference_pair({'prompt_context': 'س', 'rejected_response': 'نفس', 'preferred_response': 'نفس'}, db)
    with pytest.raises(ValidationError):
        add_direct_text({'text': 'نص', 'language_layer': 'msa', 'source_type': 'scraped'}, db)
    item = add_direct_text({'text': 'نص أول', 'language_layer': 'msa', 'source_type': 'human_written', 'origin': 'manual'}, db)
    update_manual_data('direct', item['id'], {'text': 'نص مُحسَّن'}, db)
    versions = list_manual_versions('direct', item['id'], db)
    assert len(versions) >= 2, 'an edit keeps the earlier version'


def _write(directory: Path, name: str, rows: list[dict]):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def _record(rid, conversation, question, answer, status='FULL_CORRECTION'):
    return {'id': rid, 'conversation_id': conversation, 'review_status': status, 'origin': 'human_corrected',
            'messages': [{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer}],
            'target_message_index': 1, 'train_on_last_assistant_only': True, 'message_loss_mask': [0, 1]}


def test_statistics_separate_size_from_diversity(tmp_path):
    directory = tmp_path / 'v'
    # Ten records from two conversations: the shape of the first Qwen experiment.
    _write(directory, 'sft.jsonl', [_record(f'r{i}', 'conv-A' if i < 9 else 'conv-B', f'question number {i}', f'answer {i}',
                                            'FULL_CORRECTION' if i % 2 else 'CONTENT_CORRECTION') for i in range(10)])
    stats = platform.dataset_statistics(directory, analyze_directory(directory))
    assert (stats['training_records'], stats['independent_source_conversations']) == (10, 2)
    assert stats['largest_source_share'] == 0.9 and stats['records_sharing_a_conversation'] == 9
    assert stats['review_status'] == {'FULL_CORRECTION': 5, 'CONTENT_CORRECTION': 5}
    assert stats['missing_language_metadata'] == 10
    assert (stats['stage'], stats['stage_reason']) == ('technical_smoke_test', 'no independent evaluation samples')
    _write(directory, 'evaluation_holdout.jsonl', [_record('e1', 'conv-E', 'an unrelated held out question', 'held out answer')])
    stats = platform.dataset_statistics(directory, analyze_directory(directory))
    assert stats['stage'] == 'small_exploratory' and stats['split']['evaluation_sources'] == 1
    _write(directory, 'multi_turn.jsonl', [_record('m1', 'conv-C', 'third source question', 'third source answer')])
    assert platform.dataset_statistics(directory, analyze_directory(directory))['stage'] == 'measurable_evaluation'


def test_shared_context_and_near_duplicates_across_splits_are_detected(tmp_path):
    directory = tmp_path / 'v'
    _write(directory, 'sft.jsonl', [_record('t1', 'conv-A', 'what is the capital city of saudi arabia today', 'Riyadh'),
                                    _record('t2', 'conv-B', 'explain how fast random access memory really is compared to old spinning disks today', 'Faster')])
    # Different conversation and different answer, but the same question: the evaluated prompt was trained on.
    _write(directory, 'evaluation_holdout.jsonl', [_record('e1', 'conv-E', 'what is the capital city of saudi arabia today', 'It is Riyadh.'),
                                                   _record('e2', 'conv-F', 'explain how fast random access memory really is compared to old spinning disk today', 'Much faster')])
    codes = {f['code']: f['severity'] for f in analyze_directory(directory)['findings']}
    assert codes['TRAIN_EVAL_CONTEXT_LEAKAGE'] == 'confirmed_blocker'
    assert codes['TRAIN_EVAL_NEAR_DUPLICATE'] == 'warning'
    stats = platform.dataset_statistics(directory, analyze_directory(directory))
    assert stats['cross_split_shared_contexts'] == 1 and stats['cross_split_near_duplicates'] == 1
    assert stats['stage'] == 'technical_smoke_test' and stats['stage_reason'] == 'evaluation shares data with training'
