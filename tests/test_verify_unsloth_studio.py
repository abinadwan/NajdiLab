"""Training-mask verification (V2.2.0 P0).

Unit tests cover the checker with a fake tokenizer and run everywhere. The integration test runs Unsloth
Studio's own formatting and masking on synthetic handoffs; it needs a local Studio install:
    NAJDILAB_UNSLOTH_STUDIO_PYTHON=<Studio>/unsloth_studio/Scripts/python.exe
    NAJDILAB_UNSLOTH_STUDIO_MODEL=unsloth/Qwen2.5-0.5B-Instruct   (cached; the test runs offline)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

from app import dataset_platform as platform
from app.unsloth_export import create_handoff

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_unsloth_studio', ROOT / 'scripts' / 'verify_unsloth_studio.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class FakeTokenizer:
    def __init__(self, pieces):
        self.pieces = pieces

    def decode(self, ids, skip_special_tokens=False):
        return ''.join(self.pieces[i] for i in ids if not (skip_special_tokens and self.pieces[i].startswith('<|')))


TOKENS = FakeTokenizer({1: 'User: q', 2: ' old wrong', 3: ' approved', 4: ' answer', 5: '<|im_end|>'})


def sample(flags, ids=(1, 2, 3, 4, 5), truncated=None):
    return {'tokens': [[i, '', f] for i, f in zip(ids, flags)], 'num_tokens': len(ids), 'num_trained': sum(flags), 'truncated_from': truncated}


def test_checker_accepts_only_one_contiguous_span_that_is_exactly_the_answer():
    assert verify.check(TOKENS, sample([0, 0, 1, 1, 1]), ' approved answer')['ok'] is True
    two_spans = verify.check(TOKENS, sample([0, 1, 0, 1, 1]), ' approved answer')
    assert not two_spans['ok'] and 'contiguous' in two_spans['problems'][0]
    wrong = verify.check(TOKENS, sample([0, 1, 1, 1, 1]), ' approved answer')
    assert not wrong['ok'] and 'not exactly the approved answer' in wrong['problems'][0]
    assert not verify.check(TOKENS, sample([0, 0, 0, 0, 0]), ' approved answer')['ok']
    assert 'truncated' in verify.check(TOKENS, sample([0, 0, 1, 1, 1], truncated=4096), ' approved answer')['problems'][0]


def test_checker_reads_the_target_of_each_profile_and_refuses_a_changed_file(tmp_path):
    assert verify.target_of({'messages': [{'role': 'user', 'content': 'q'}, {'role': 'assistant', 'content': 'A'}]}, 'studio_chat') == 'A'
    assert verify.target_of({'instruction': 'q', 'input': '', 'output': 'A'}, 'studio_alpaca') == 'A'
    assert verify.target_of({'prompt': [], 'completion': [{'role': 'assistant', 'content': 'A'}]}, 'trl_prompt_completion') == 'A'
    (tmp_path / 'dataset.jsonl').write_text('{"output":"A"}\n', encoding='utf-8')
    (tmp_path / 'provenance.jsonl').write_text('', encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps({'sha256': {'dataset.jsonl': '0' * 64}}), encoding='utf-8')
    with pytest.raises(SystemExit):
        verify.load_handoff(tmp_path)


def synthetic_dataset(directory: Path) -> None:
    """Privacy-safe rows shaped like the first Qwen experiment: growing multi-turn records whose earlier
    assistant turns are the model's original (partly wrong) answers, plus single-turn manual records."""
    u = lambda t: {'role': 'user', 'content': t}
    a = lambda t: {'role': 'assistant', 'content': t}
    rows, history = [], []
    for i, (q, original, approved) in enumerate([('وش عاصمة السعودية؟', 'WRONG: جدة', 'العاصمة هي الرياض.'),
                                                 ('وكم عدد سكانها؟', 'WRONG: مليون', 'أكثر من سبعة ملايين تقريبًا.'),
                                                 ('Which is faster, RAM or disk?', 'WRONG: disk', 'RAM is far faster than disk.')]):
        messages = history + [u(q), a(approved)]
        rows.append({'id': f'review:{i}', 'conversation_id': 'synthetic-A', 'origin': 'human_corrected', 'review_status': 'APPROVED',
                     'messages': messages, 'target_message_index': len(messages) - 1, 'train_on_last_assistant_only': True,
                     'message_loss_mask': [0] * (len(messages) - 1) + [1]})
        history = history + [u(q), a(original)]
    rows.append({'id': 'manual:1', 'conversation_id': 'manual:1', 'origin': 'human_written', 'review_status': 'APPROVED',
                 'messages': [u('Say hello.'), a('Hello! How can I help?')], 'target_message_index': 1,
                 'train_on_last_assistant_only': True, 'message_loss_mask': [0, 1]})
    directory.mkdir(parents=True)
    (directory / 'sft.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    (directory / 'manifest.json').write_text(json.dumps({'version': 'gold-v001', 'state': 'Frozen', 'privacy_policy': 'no_flagged_or_excluded_context_v1',
                                                         'sha256': {'sft.jsonl': hashlib.sha256((directory / 'sft.jsonl').read_bytes()).hexdigest()}}))


STUDIO = os.environ.get('NAJDILAB_UNSLOTH_STUDIO_PYTHON')


@pytest.mark.skipif(not (STUDIO and Path(STUDIO).is_file()), reason='Set NAJDILAB_UNSLOTH_STUDIO_PYTHON to Unsloth Studio\'s Python')
def test_unsloth_studio_trains_only_the_approved_answer_for_studio_profiles(tmp_path, monkeypatch):
    synthetic_dataset(tmp_path / 'exports' / 'gold-v001')
    monkeypatch.setattr(platform, 'EXPORTS_DIR', tmp_path / 'exports')
    model = os.environ.get('NAJDILAB_UNSLOTH_STUDIO_MODEL', 'unsloth/Qwen2.5-0.5B-Instruct')
    verdicts = {}
    for profile in ('studio_chat', 'studio_alpaca', 'trl_prompt_completion'):
        handoff = create_handoff('gold-v001', profile=profile, output_root=tmp_path / 'handoffs')
        report = tmp_path / f'{profile}.json'
        run = subprocess.run([STUDIO, '-I', str(ROOT / 'scripts' / 'verify_unsloth_studio.py'), handoff['directory'], '--model', model,
                              '--output', str(report)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600,
                             env={**os.environ, 'HF_HUB_OFFLINE': '1'})
        assert report.is_file(), run.stderr[-2000:]
        data = json.loads(report.read_text(encoding='utf-8'))
        assert data['records_inspected'] == 4
        verdicts[profile] = (data['verdict'], data['records_failed'], run.returncode)
    assert verdicts['studio_chat'] == ('PASS', 0, 0)
    assert verdicts['studio_alpaca'] == ('PASS', 0, 0)
    # The old conversational prompt/completion file, loaded in Studio, also trains earlier assistant turns.
    assert verdicts['trl_prompt_completion'] == ('FAIL', 2, 1)
