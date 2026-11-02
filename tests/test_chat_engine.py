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


# Phase C AI-02: these synthetic checks identify the failing predicate without
# exposing prompt bytes, generated content, model instance IDs or SDK exception text.
@pytest.mark.parametrize('fault,expected', [
    ('instance', 'RESULT_MISMATCH_INSTANCE'),
    ('structured', 'RESULT_MISMATCH_STRUCTURED'),
    ('content', 'RESULT_MISMATCH_CONTENT'),
    ('tokens', 'RESULT_MISMATCH_TOKENS'),
])
def test_lmstudio_four_post_generation_predicates_report_distinct_safe_codes(fault, expected):
    model = FakeModel()
    loaded = LoadedModel(*bound(model), 'fixture')
    loaded.measure([{'role': 'user', 'content': 'PRIVATE_PROMPT_MUST_NOT_LEAK'}])
    original_get_info = model.get_info
    changed = [False]
    def info():
        value = original_get_info()
        if fault == 'instance' and changed[0]:
            return NS(**{**vars(value), 'instance_reference': 'another-instance'})
        return value
    model.get_info = info

    class FakeStream:
        def __enter__(self): return self
        def __exit__(self, *_):
            changed[0] = True
            return False
        def __iter__(self):
            yield NS(content='PRIVATE_RESPONSE_MUST_NOT_LEAK', reasoning_type='none')
        def result(self):
            return NS(
                structured=(fault == 'structured'),
                content='different-text' if fault == 'content' else 'PRIVATE_RESPONSE_MUST_NOT_LEAK',
                stats=NS(
                    prompt_tokens_count=len(loaded.tokens) + (1 if fault == 'tokens' else 0),
                    predicted_tokens_count=3, stop_reason='stop'))
    model.respond_stream = lambda *_args, **_kwargs: FakeStream()
    with pytest.raises(ValueError) as error:
        loaded.generate(32, threading.Event())
    assert str(error.value) == expected
    assert 'PRIVATE_' not in str(error.value)


@pytest.mark.parametrize('check', ['INSTANCE_REFERENCE', 'STRUCTURED_OUTPUT', 'STREAM_CONTENT', 'PROMPT_TOKEN_COUNT'])
def test_lmstudio_result_diagnostic_keeps_wire_error_generic_and_sanitizes_details(check):
    import queue
    import time
    from app.chat_engine import EngineProcess
    process = object.__new__(EngineProcess)
    process.events = queue.Queue()
    process.deadline = time.monotonic() + 2
    process.events.put({'error': 'RESULT_MISMATCH', 'check': check})
    with pytest.raises(IntegrationError) as err:
        process.receive()
    assert err.value.code == 'RESULT_MISMATCH'
    assert 'Integrity check:' in str(err.value)
    assert 'PRIVATE_' not in str(err.value)


def test_lmstudio_result_diagnostic_ignores_unknown_untrusted_check():
    import queue
    import time
    from app.chat_engine import EngineProcess
    process = object.__new__(EngineProcess)
    process.events = queue.Queue()
    process.deadline = time.monotonic() + 2
    process.events.put({'error': 'RESULT_MISMATCH', 'check': 'PRIVATE_UNTRUSTED_PAYLOAD'})
    with pytest.raises(IntegrationError) as err:
        process.receive()
    assert err.value.code == 'RESULT_MISMATCH'
    assert 'PRIVATE_UNTRUSTED_PAYLOAD' not in str(err.value)


@pytest.mark.parametrize('internal,public', list(chat_engine_worker.MISMATCH_CHECKS.items()))
def test_lmstudio_worker_only_emits_whitelisted_mismatch_identifiers(monkeypatch, internal, public):
    class FakeClient:
        def __init__(self, *_): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
    sdk = NS(set_sync_api_timeout=lambda _: None, Client=FakeClient)
    monkeypatch.setitem(__import__('sys').modules, 'lmstudio', sdk)
    monkeypatch.setattr('importlib.metadata.version', lambda _: '1.5.0')
    monkeypatch.setattr(chat_engine_worker, 'read',
                        lambda: {'port': 1234, 'model': 'synthetic', 'deadline': 600})
    def fail(*_):
        raise ValueError(internal)
    monkeypatch.setattr(chat_engine_worker, 'LoadedModel', fail)
    observed = []
    monkeypatch.setattr(chat_engine_worker, 'emit', observed.append)
    chat_engine_worker.main()
    assert observed == [{'error': 'RESULT_MISMATCH', 'check': public}]
