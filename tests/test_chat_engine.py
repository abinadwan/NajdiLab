"""Pinned SDK contract tested with synthetic loaded-model handles only."""
import json
from types import SimpleNamespace as NS
import threading

import pytest

from app.chat_engine import WORKER_ERRORS, open_engine
from app import chat_engine_worker
from app.chat_engine_worker import LoadedModel
from app.hardware import recommendation
from app.integrations import CONNECTORS, IntegrationError


class FakeModel:
    identifier = 'fixture'
    calls = []
    def get_info(self):
        return NS(identifier='fixture', model_key='fixture-key', instance_reference='instance-1',
                  max_context_length=8192, size_bytes=1000, architecture='llama')
    def get_context_length(self): return 2048
    def apply_prompt_template(self, history):
        self.calls.append(('template', history))
        return '<bos>' + repr(history)
    def tokenize(self, text): return list(range(len(text.encode('utf-8'))))



def bound(model):
    """The SDK surface LoadedModel may use: `LLM` handles on an instance reference."""
    def handle(specifier, session):
        assert specifier=={'type':'instanceReference','instanceReference':'instance-1'}
        assert session is llm
        return model
    llm = NS(list_loaded=lambda:[model])
    return NS(llm=llm), NS(Chat=NS(from_history=lambda h:h), LLM=handle)


def test_loaded_only_exact_template_and_no_implicit_system():
    model = FakeModel()
    client, sdk = bound(model)
    loaded = LoadedModel(client, sdk, 'fixture')
    messages = [{'role':'user','content':'  هلا 🙂  '}]
    result = loaded.measure(messages)
    assert result['input_tokens'] == len(('<bos>' + repr({'messages':messages})).encode('utf-8'))
    assert result['loaded_context'] == 2048
    assert model.calls[-1][1] == {'messages': messages}
    with pytest.raises(ValueError, match='MODEL_NOT_LOADED'):
        LoadedModel(client, sdk, 'not-loaded')
    with pytest.raises(ValueError):
        loaded.measure([{'role':'system','content':'hidden'}])


def test_ambiguous_loaded_handles_refused():
    model = FakeModel()
    with pytest.raises(ValueError):
        LoadedModel(NS(llm=NS(list_loaded=lambda:[model, model])), NS(), 'fixture')


def test_limits_separate_loaded_context_from_model_maximum():
    model = FakeModel()
    limits = LoadedModel(*bound(model), 'fixture').limits()
    assert (limits['budget_ceiling'], limits['runtime_context'], limits['model_max_context']) == (2048, 2048, 8192)
    assert limits['kv'] is None and limits['loaded']['size_vram_bytes'] is None


def test_worker_reports_only_fixed_codes_never_sdk_text(monkeypatch):
    class Client:
        def __init__(self, host):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
    sent = []
    fixture = NS(set_sync_api_timeout=lambda v: sent.append(v), Client=Client)
    monkeypatch.setitem(__import__('sys').modules, 'lmstudio', fixture)
    monkeypatch.setattr('importlib.metadata.version', lambda name: '1.5.0')
    lines = iter([{'port':1234,'model':'m','deadline':600}])
    monkeypatch.setattr(chat_engine_worker, 'read', lambda: next(lines))
    out = []
    monkeypatch.setattr(chat_engine_worker, 'emit', out.append)
    def fail(message):
        def load(*args):
            raise ValueError(message)
        monkeypatch.setattr(chat_engine_worker, 'LoadedModel', load)
    fail('MODEL_NOT_LOADED')
    chat_engine_worker.main()
    assert out.pop() == {'error':'MODEL_NOT_LOADED'} and sent == [600]
    lines = iter([{'port':1234,'model':'m','deadline':600}])
    fail('prompt text from an sdk error')
    chat_engine_worker.main()
    assert out.pop() == {'error':'ENGINE_UNAVAILABLE'}


def test_every_reported_worker_code_has_a_user_message():
    assert chat_engine_worker.REPORTED <= set(WORKER_ERRORS)


def test_memory_recommendation_never_guesses_from_gpu_or_model_size():
    result = recommendation({'ram_available_bytes':64*1024**3, 'gpus':[{'free_bytes':24*1024**3}]})
    assert result['recommended_context'] is None
    assert result['status'] == 'INSUFFICIENT_EVIDENCE'
    assert 'kv_cache' in result['missing']


def test_worker_revalidates_template_before_inference():
    model = FakeModel()
    loaded = LoadedModel(*bound(model), 'fixture')
    loaded.measure([{'role':'user','content':'test'}])
    model.apply_prompt_template = lambda h: 'changed-template'
    with pytest.raises(ValueError, match='MODEL_CHANGED'):
        loaded.generate(32, threading.Event())


@pytest.mark.parametrize('bad', ['template','tokens'])
def test_empty_template_or_empty_tokenizer_reply_cannot_mean_zero_tokens(bad):
    model=FakeModel()
    if bad=='template':model.apply_prompt_template=lambda history:''
    else:model.tokenize=lambda text:[]
    loaded=LoadedModel(*bound(model),'fixture')
    with pytest.raises(ValueError):loaded.measure([{'role':'user','content':'text'}])
