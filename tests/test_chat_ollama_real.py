"""Real Ollama binary, disposable instance, synthetic tiny model. CPU only.

Opt-in with NAJDILAB_DISPOSABLE_OLLAMA=1: it starts an executable, so it is never
a side effect of a plain test run. Proves engine behavior on the installed
version, not any installed model's template, tokenizer or memory use.
"""
from dataclasses import replace
import os
import re
import threading
import time
from uuid import uuid4

import pytest

from app.chat_engine import OllamaEngine, open_engine
from app.chat_workspace import ChatWorkspace
from app.db import apply_migrations, connect
from app.integrations import CONNECTORS, IntegrationError, IntegrationManager
from ollama_disposable import DisposableOllama, TRAIN_CONTEXT, binary

pytestmark = pytest.mark.skipif(not (os.environ.get('NAJDILAB_DISPOSABLE_OLLAMA') == '1' and binary()),
                                reason='Set NAJDILAB_DISPOSABLE_OLLAMA=1 with an installed Ollama to run real-engine checks')


@pytest.fixture(scope='module')
def ollama(tmp_path_factory):
    with DisposableOllama(tmp_path_factory.mktemp('ollama')) as engine:
        engine.model = engine.create()
        engine.endless = engine.create('endless', eos=False)
        yield engine


def spec(ollama):
    return replace(CONNECTORS['ollama'], port=ollama.port)


def workspace(ollama, tmp_path, model):
    db = tmp_path / 'own.db'
    apply_migrations(db)
    manager = IntegrationManager(connectors={'ollama':spec(ollama)}, home=tmp_path)
    manager._states['ollama'].update(connection='CONNECTED', selected_model=model, models=[model], selection_revision=2)
    return ChatWorkspace(manager, db, engine_factory=open_engine), db


def new(ws, model, budget=512, reserve=32):
    return ws.create({'provider':'ollama', 'model':model, 'selection_revision':2, 'context_budget':budget,
                      'reply_reserve':reserve, 'load_approved':True})


def turn(ws, session, text):
    return ws.send(session['id'], {'request_id':str(uuid4()), 'revision':session['revision'], 'selection_revision':2, 'text':text})


def test_default_ollama_really_drops_history_which_is_why_this_design_exists(ollama):
    messages = [{'role':'user','content':'x' * 400}, {'role':'assistant','content':'ok'}, {'role':'user','content':'short'}]
    base = {'model':ollama.model, 'messages':messages, 'stream':False, 'options':{'num_ctx':256, 'num_predict':1}}
    status, silent = ollama.call('POST', '/api/chat', base)
    assert status == 200 and silent['prompt_eval_count'] < 100
    status, refused = ollama.call('POST', '/api/chat', {**base, 'truncate':False, 'shift':False})
    assert status == 400 and 'exceeds the available context size' in refused['error']


def test_count_is_full_prompt_even_when_served_from_cache(ollama):
    engine = OllamaEngine(spec(ollama), ollama.model)
    engine.budget = 512
    messages = [{'role':'user','content':'abc def'}]
    first = engine.chat(messages, 1, None)
    second = engine.chat(messages, 1, None)
    assert first['prompt_eval_count'] == second['prompt_eval_count'] > 7
    assert second['prompt_eval_cached_count'] > 0


def test_num_predict_one_counts_the_same_prompt_the_reply_uses(ollama):
    engine = OllamaEngine(spec(ollama), ollama.model)
    messages = [{'role':'user','content':'count me'}]
    measured = engine.measure(messages, 512)
    result = engine.generate(messages, 32, threading.Event())
    assert result['input_tokens'] == measured['input_tokens'] and measured['loaded_context'] == 512


def test_unknown_runner_setting_cannot_pass_ps_check(ollama):
    # 8192 is the synthetic model's trained maximum; Ollama would clamp above it.
    engine = OllamaEngine(spec(ollama), ollama.model)
    engine.budget = TRAIN_CONTEXT * 2
    engine.chat([{'role':'user','content':'a'}], 1, None)
    rows = ollama.call('GET', '/api/ps')[1]['models']
    assert rows[0]['context_length'] == TRAIN_CONTEXT


def test_real_multi_turn_chat_until_exact_budget_rollover(ollama, tmp_path):
    ws, db = workspace(ollama, tmp_path, ollama.model)
    try:
        session = new(ws, ollama.model, budget=1024, reserve=160)
        result = turn(ws, session, 'first question ' * 2)
        assert result['status'] == 'COMPLETED'
        first = result['session']['turns'][0]
        assert first['user'] == 'first question ' * 2
        result = turn(ws, result['session'], 'second')
        assert result['status'] == 'COMPLETED'
        assert result['session']['turns'][1]['input_tokens'] > first['input_tokens']
        rolled = turn(ws, result['session'], 'overflow ' * 120)
        assert rolled['status'] == 'CONTEXT_LIMIT'
        assert rolled['input_tokens'] + 160 > 1024
        assert rolled['new_session']['turns'] == []
        with connect(db) as conn:
            assert conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0] == 2
        fresh = turn(ws, rolled['new_session'], 'a new start')
        assert fresh['status'] == 'COMPLETED'
        assert fresh['session']['turns'][0]['input_tokens'] < first['input_tokens']
    finally:
        ws.close()


def test_real_near_limit_prompt_and_exact_reserve_complete_without_truncation(ollama, tmp_path):
    ws, db = workspace(ollama, tmp_path, ollama.model)
    try:
        measured = OllamaEngine(spec(ollama), ollama.model).measure([{'role':'user','content':'x' * 100}], 1024)['input_tokens']
        session = new(ws, ollama.model, budget=measured + 160, reserve=160)
        result = turn(ws, session, 'x' * 100)
        assert result['status'] == 'COMPLETED'
        saved = result['session']['turns'][0]
        assert saved['input_tokens'] == measured and saved['input_tokens'] + saved['output_tokens'] <= measured + 160
        over = new(ws, ollama.model, budget=measured + 159, reserve=160)
        assert turn(ws, over, 'x' * 100)['status'] == 'CONTEXT_LIMIT'
    finally:
        ws.close()


def test_real_limit_stop_is_length_and_never_saved(ollama, tmp_path):
    ws, db = workspace(ollama, tmp_path, ollama.endless)
    try:
        session = new(ws, ollama.endless, budget=512, reserve=8)
        with pytest.raises(IntegrationError) as caught:
            turn(ws, session, 'keep going')
        assert caught.value.code == 'INCOMPLETE_RESPONSE'
        with connect(db) as conn:
            assert conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0] == 0
    finally:
        ws.close()


def test_real_stop_cancels_generation_on_the_engine(ollama, tmp_path):
    ws, db = workspace(ollama, tmp_path, ollama.endless)
    try:
        session = new(ws, ollama.endless, budget=8192, reserve=8000)
        outcome = []

        def run():
            try:
                outcome.append(turn(ws, session, 'run for a long time'))
            except IntegrationError as error:
                outcome.append(error.code)

        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 30
        while not ws.get(session['id'])['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        time.sleep(.3)
        ws.stop(session['id'])
        worker.join(20)
        assert outcome and outcome[0] == 'STOPPED'
        # Serving the next request forces the old slot to be released and logged.
        ollama.call('POST', '/api/chat', {'model':ollama.endless, 'stream':False, 'truncate':False, 'shift':False,
                                          'messages':[{'role':'user','content':'a'}], 'options':{'num_ctx':8192, 'num_predict':1}})
        log = (ollama.root / 'serve.log').read_bytes().decode('utf-8', 'replace')
        processed = [int(n) for n in re.findall(r'stop processing: n_tokens = (\d+)', log)]
        assert processed and max(processed) < 7000
        with connect(db) as conn:
            assert conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0] == 0
    finally:
        ws.close()


def test_limits_read_never_loads_the_model(tmp_path_factory):
    with DisposableOllama(tmp_path_factory.mktemp('cold')) as ollama:
        model = ollama.create()
        limits = OllamaEngine(spec(ollama), model).limits()
        assert limits['model_max_context'] == TRAIN_CONTEXT and limits['runtime_context'] is None
        assert limits['engine_version'] and limits['model_key'].startswith('ollama:')
        assert ollama.call('GET', '/api/ps')[1]['models'] == []
