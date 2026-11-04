"""The composer's single runtime-preparation path: model list, start, restart at another context,
LM Studio / Ollama approval, refusals while a reply runs. Fake runtimes; nothing real is started."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chat_preparation import ChatPreparation, short_label  # noqa: E402
from app.integrations import IntegrationError  # noqa: E402

GIB = 1024 ** 3
GEMMA = 'huggingface/google--gemma-4-E4B-it-qat-q4_0-gguf/4b4a2c1d584b/gemma-4-E4B_q4_0-it.gguf'
QWEN = 'huggingface/Qwen--Qwen2.5-0.5B-Instruct-GGUF/9217f5db79a2/qwen2.5-0.5b-instruct-q4_k_m.gguf'
FILES = {GEMMA: {'size': 5_154_941_280, 'max': 131072, 'quant': 'Q4_0'}, QWEN: {'size': 491_400_032, 'max': 32768, 'quant': 'Q4_K_M'},
         'owner/local.gguf': {'size': 100_000_000, 'max': 4096, 'quant': 'Q8_0'}}
KV = {'block_count': 24, 'attention.head_count_kv': 2, 'attention.key_length': 64, 'attention.value_length': 64,
      'embedding_length': 896, 'attention.head_count': 14}


class FakeNative:
    """Just the surface ChatPreparation uses; records every start and stop."""

    def __init__(self, tmp_path, server=True):
        self.server_path = tmp_path / 'llama-server.exe'
        tmp_path.mkdir(parents=True, exist_ok=True)
        if server:
            self.server_path.write_bytes(b'x')
        self.run, self.revision, self.calls, self.start_gate, self.leased = None, 0, [], None, False

    def _resolve(self, model):
        if model not in FILES:
            raise IntegrationError('NATIVE_MODEL_NOT_FOUND', 'That model file is not in the models folder.', 404)
        return Path(model)

    def inspect(self, path):
        f = FILES[str(path).replace('\\', '/')]
        return {'id': str(path).replace('\\', '/'), 'file': Path(path).name, 'size_bytes': f['size'], 'valid': True, 'error': None,
                'architecture': 'llama', 'quantization': f['quant'], 'model_max_context': f['max'], 'kv': KV}

    def models(self):
        return {'items': [self.inspect(Path(m)) for m in FILES]}

    def running(self):
        return None if self.run is None else {**self.run, 'revision': self.revision, 'leased': self.leased}

    def brief(self):
        return ('RUNNING' if self.run else 'STOPPED'), None, self.run and self.run['model'], self.revision

    def status(self):
        return {'server_available': True, 'devices': [{'id': 'CUDA0', 'name': 'GPU', 'total_bytes': 12 * GIB, 'free_bytes': 10 * GIB}]}

    def stop(self, data):
        assert data == {'approved': True}
        if self.leased:
            raise IntegrationError('NATIVE_BUSY', 'A chat reply is using NajdiLab Native; stop the reply first.', 409)
        self.calls.append(('stop',))
        self.run = None
        self.revision += 1

    def start(self, data):
        assert data['approved'] is True
        self.calls.append(('start', data['model'], data['context_budget'], data['gpu_layers']))
        self.run = {'model': data['model'], 'context': data['context_budget'], 'gpu_layers': data['gpu_layers'],
                    'sha256': 'a' * 64, 'build': 'b12059', 'started_at': 'now'}
        self.revision += 1


class FakeIntegrations:
    def __init__(self, connected=True, selected=None):
        self.state = {'lmstudio': {'id': 'lmstudio', 'kind': 'model_runtime', 'connection': 'CONNECTED' if connected else 'DISCONNECTED',
                                   'models': ['lm-model'], 'selected_model': selected, 'selection_revision': 3},
                      'ollama': {'id': 'ollama', 'kind': 'model_runtime', 'connection': 'CONNECTED' if connected else 'DISCONNECTED',
                                 'models': ['gemma4:e4b'], 'selected_model': 'gemma4:e4b', 'selection_revision': 7}}
        self.actions = []

    def snapshot(self):
        return {'items': [dict(v) for v in self.state.values()]}

    def action(self, key, action, payload):
        self.actions.append((key, action, payload))
        self.state[key]['selected_model'] = payload['model']
        self.state[key]['selection_revision'] += 1
        return self.snapshot()


class Library:
    def library(self):
        return {'items': [{'native_id': GEMMA, 'status': 'READY', 'repo_id': 'google/gemma-4-E4B-it-qat-q4_0-gguf', 'verified_sha256': 'b' * 64},
                          {'native_id': QWEN, 'status': 'DOWNLOADING', 'repo_id': 'Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'verified_sha256': None}]}


def snapshot(free=10 * GIB):
    return lambda: {'ram_total_bytes': 32 * GIB, 'ram_available_bytes': 16 * GIB,
                    'gpus': [{'name': 'GPU', 'total_bytes': 12 * GIB, 'free_bytes': free, 'backend': 'NVIDIA'}], 'warnings': []}


def prep(tmp_path, **kw):
    native = kw.pop('native', None) or FakeNative(tmp_path)
    integrations = kw.pop('integrations', None) or FakeIntegrations()
    return ChatPreparation(native, lambda: integrations, lambda: Library(), kw.pop('snapshot', snapshot())), native, integrations


def ask(p, model=GEMMA, provider='native', context=8192, **extra):
    return p.prepare({'provider': provider, 'model': model, 'context_budget': context, 'reply_reserve': 1024, **extra})


def code(call):
    with pytest.raises(IntegrationError) as caught:
        call()
    return caught.value.code


def test_short_labels_are_readable():
    assert short_label(GEMMA, 'google/gemma-4-E4B-it-qat-q4_0-gguf', 'Q4_0') == 'gemma-4-E4B-it-qat-q4_0'
    assert short_label(QWEN, 'Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'Q4_K_M') == 'Qwen2.5-0.5B-Instruct · Q4_K_M'
    assert short_label('owner/local.gguf', None, 'Q8_0') == 'local · Q8_0'


def test_model_list_comes_from_approved_runtimes_with_verification(tmp_path):
    p, native, _ = prep(tmp_path)
    items = {(i['provider'], i['model']): i for i in p.models()['items']}
    assert items[('native', GEMMA)]['verification'] == 'VERIFIED' and items[('native', GEMMA)]['available']
    qwen = items[('native', QWEN)]
    assert qwen['verification'] == 'UNVERIFIED' and not qwen['available'] and qwen['reason'] == 'MODEL_NOT_VERIFIED'
    assert items[('native', 'owner/local.gguf')]['verification'] == 'LOCAL'
    assert items[('lmstudio', 'lm-model')]['state'] == 'AVAILABLE' and items[('ollama', 'gemma4:e4b')]['state'] == 'SELECTED'
    native.start({'approved': True, 'model': GEMMA, 'context_budget': 8192, 'gpu_layers': 'auto'})
    listed = p.models()
    assert listed['native']['context'] == 8192 and next(i for i in listed['items'] if i['model'] == GEMMA)['loaded_context'] == 8192
    unplugged, _, _ = prep(tmp_path / 'x', integrations=FakeIntegrations(connected=False))
    assert {i['provider'] for i in unplugged.models()['items']} == {'native'}, 'disconnected runtimes offer nothing'


def test_nothing_starts_without_approval_and_reuse_is_exact(tmp_path):
    p, native, _ = prep(tmp_path)
    plan = ask(p)
    assert plan['state'] == 'NEEDS_START' and native.calls == []
    ready = ask(p, approved=True)
    assert ready['state'] == 'READY' and ready['action'] == 'START' and native.calls == [('start', GEMMA, 8192, 'auto')]
    assert ready['advice']['classification'] in {'COMPATIBLE', 'LIMITED'} and ready['selection_revision'] == native.revision
    again = ask(p)
    assert again['state'] == 'READY' and len(native.calls) == 1, 'same model and context: reused, never restarted'


def test_a_context_mismatch_is_explained_before_sending_and_restarted_only_with_approval(tmp_path):
    p, native, _ = prep(tmp_path)
    ask(p, approved=True)
    plan = ask(p, context=16384)
    assert plan['state'] == 'NEEDS_RESTART' and 'different context' in plan['message'] and len(native.calls) == 1
    other = ask(p, model='owner/local.gguf', context=4096)
    assert other['state'] == 'NEEDS_RESTART' and 'different model' in other['message']
    native.leased = True
    busy = ask(p, context=16384, approved=True)
    assert busy['state'] == 'BUSY' and busy['code'] == 'NATIVE_BUSY' and len(native.calls) == 1, 'never restarted during a reply'
    native.leased = False
    done = ask(p, context=16384, approved=True)
    assert done['state'] == 'READY' and done['stopped_previous'] and native.calls[-2:] == [('stop',), ('start', GEMMA, 16384, 'auto')]


def test_memory_that_does_not_fit_blocks_the_start(tmp_path):
    p, native, _ = prep(tmp_path, snapshot=lambda: {'ram_total_bytes': 2 * GIB, 'ram_available_bytes': 1 * GIB,
                                                     'gpus': [{'name': 'GPU', 'total_bytes': 2 * GIB, 'free_bytes': 1 * GIB, 'backend': 'NVIDIA'}], 'warnings': []})
    result = ask(p, approved=True)
    assert result['state'] == 'BLOCKED' and result['code'] == 'DOES_NOT_FIT' and native.calls == []


def test_invalid_choices_fail_closed(tmp_path):
    p, native, _ = prep(tmp_path)
    assert ask(p, context=262144)['code'] == 'ENGINE_CONTEXT_LIMIT', 'above the model maximum'
    assert code(lambda: ask(p, model='../escape.gguf')) == 'NATIVE_MODEL_NOT_FOUND'
    assert code(lambda: p.prepare({'provider': 'native', 'model': GEMMA, 'context_budget': 4096, 'reply_reserve': 4096})) == 'INVALID_LIMIT'
    assert code(lambda: ask(p, gpu_layers='99')) == 'INVALID_PAYLOAD'
    assert code(lambda: ask(p, provider='cloud')) == 'UNKNOWN_PROVIDER'
    assert code(lambda: ask(p, extra=1)) == 'INVALID_PAYLOAD'
    gated = []
    native.start_gate = lambda path: (gated.append(path), (_ for _ in ()).throw(IntegrationError('MODEL_NOT_VERIFIED', 'not verified', 409)))
    assert code(lambda: ask(p)) == 'MODEL_NOT_VERIFIED' and gated, 'the verification gate runs before any approval'
    missing, _, _ = prep(tmp_path / 'n', native=FakeNative(tmp_path / 'n', server=False))
    assert ask(missing)['code'] == 'NATIVE_SERVER_MISSING'


def test_lm_studio_and_ollama_need_approval_to_select_or_load(tmp_path):
    p, _, integrations = prep(tmp_path)
    lm = ask(p, provider='lmstudio', model='lm-model')
    assert lm['state'] == 'NEEDS_APPROVAL' and lm['needs_select'] and integrations.actions == []
    lm = ask(p, provider='lmstudio', model='lm-model', approved=True)
    assert lm['state'] == 'READY' and integrations.actions == [('lmstudio', 'select', {'approved': True, 'model': 'lm-model'})]
    assert lm['load_approved'] is False
    ollama = ask(p, provider='ollama', model='gemma4:e4b')
    assert ollama['state'] == 'NEEDS_APPROVAL' and ollama['needs_load'], 'every new Ollama chat asks before loading'
    assert ask(p, provider='ollama', model='gemma4:e4b', approved=True)['load_approved'] is True
    existing = ask(p, provider='ollama', model='gemma4:e4b', new_session=False)
    assert existing['state'] == 'READY' and existing['load_approved'] is False, 'an existing chat keeps its own approval'
    assert ask(p, provider='ollama', model='missing')['code'] == 'MODEL_UNAVAILABLE'
    off, _, _ = prep(tmp_path / 'o', integrations=FakeIntegrations(connected=False))
    assert ask(off, provider='lmstudio', model='lm-model')['code'] == 'NOT_CONNECTED'
