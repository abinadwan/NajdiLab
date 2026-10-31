"""Pinned SDK contract tested with synthetic loaded-model handles only."""
from types import SimpleNamespace as NS
import threading

import pytest

from app.integrations import CONNECTORS, IntegrationError
from app.chat_engine import open_engine
from app.chat_engine_worker import LoadedModel
from app.hardware import recommendation


class FakeModel:
    identifier = 'fixture'
    calls = []
    def get_info(self):
        return NS(identifier='fixture', model_key='fixture-key', instance_reference='instance-1')
    def get_context_length(self): return 2048
    def apply_prompt_template(self, history):
        self.calls.append(('template', history))
        return '<bos>' + repr(history)
    def tokenize(self, text): return list(range(len(text.encode('utf-8'))))



def session(model):
    def check(spec,fn,*args):
        assert spec=={'type':'instanceReference','instanceReference':'instance-1'}
        return fn(*args)
    return NS(list_loaded=lambda:[model],get_model_info=lambda spec:check(spec,model.get_info),
              _get_context_length=lambda spec:check(spec,model.get_context_length),
              _apply_prompt_template=lambda spec,h:check(spec,model.apply_prompt_template,h),
              _tokenize=lambda spec,text:check(spec,model.tokenize,text))

def test_loaded_only_exact_template_and_no_implicit_system():
    model = FakeModel()
    llm = session(model)
    sdk = NS(Chat=NS(from_history=lambda h: h), Client=lambda host: NS(llm=llm))
    loaded = LoadedModel(NS(llm=llm), sdk, 'fixture')
    messages = [{'role':'user','content':'  هلا 🙂  '}]
    result = loaded.measure(messages)
    assert result['input_tokens'] == len(('<bos>' + repr({'messages':messages})).encode('utf-8'))
    assert result['loaded_context'] == 2048
    assert model.calls[-1][1] == {'messages': messages}
    with pytest.raises(ValueError):
        LoadedModel(NS(llm=llm), sdk, 'not-loaded')
    with pytest.raises(ValueError):
        loaded.measure([{'role':'system','content':'hidden'}])


def test_ambiguous_loaded_handles_refused():
    model = FakeModel()
    with pytest.raises(ValueError):
        LoadedModel(NS(llm=NS(list_loaded=lambda:[model, model])), NS(), 'fixture')


def test_ollama_exact_count_unavailable_blocks_before_process_or_api():
    with pytest.raises(IntegrationError, match='exact'):
        with open_engine(CONNECTORS['ollama'], 'fixture'):
            pytest.fail('must not yield a fake engine')


def test_memory_recommendation_never_guesses_from_gpu_or_model_size():
    result = recommendation({'ram_available_bytes':64*1024**3, 'gpus':[{'free_bytes':24*1024**3}]})
    assert result['recommended_context'] is None
    assert result['status'] == 'INSUFFICIENT_EVIDENCE'
    assert 'kv_cache' in result['missing']


def test_worker_revalidates_template_before_inference():
    model = FakeModel()
    loaded = LoadedModel(NS(llm=session(model)), NS(Chat=NS(from_history=lambda h:h)), 'fixture')
    loaded.measure([{'role':'user','content':'test'}])
    model.apply_prompt_template = lambda h: 'changed-template'
    with pytest.raises(ValueError):
        loaded.generate(32, threading.Event())


@pytest.mark.parametrize('bad', ['template','tokens'])
def test_empty_template_or_empty_tokenizer_reply_cannot_mean_zero_tokens(bad):
    model=FakeModel()
    if bad=='template':model.apply_prompt_template=lambda history:''
    else:model.tokenize=lambda text:[]
    loaded=LoadedModel(NS(llm=session(model)),NS(Chat=NS(from_history=lambda h:h)),'fixture')
    with pytest.raises(ValueError):loaded.measure([{'role':'user','content':'text'}])
