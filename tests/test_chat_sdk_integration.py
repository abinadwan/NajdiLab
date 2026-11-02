"""Real pinned SDK/helper transport against a disposable synthetic WS engine.

This is not acceptance of an installed LM Studio version or actual model.
"""
import base64
from dataclasses import replace
import hashlib
import json
import socketserver
import struct
import threading

import pytest

from app.chat_engine import open_engine
from app.integrations import CONNECTORS


@pytest.fixture
def sdk_runtime():
    pytest.importorskip('lmstudio')
    calls=[]
    # AI-01: 'instance_after_predict' and 'prompt_token_delta' inject the two post-generation
    # mismatches the pinned SDK can actually produce; both default to a consistent engine.
    state={'replace_on_predict':False,'generated':0,'instance_after_predict':False,'prompt_token_delta':0,
           # AI-04: runtime drift injected between measurement and inference, the engine stop reason,
           # and a reply held open after its first fragment until the client cancels the channel.
           'info_override':{},'template_suffix':'','stop_reason':'eosFound','hold':False,
           'streaming':threading.Event(),'cancelled':threading.Event()}
    model={'type':'llm','modelKey':'fixture-key','format':'gguf','displayName':'Synthetic',
           'path':'synthetic/fixture','sizeBytes':1000,'vision':False,'trainedForToolUse':False,'maxContextLength':4096}
    instance={**model,'identifier':'fixture','instanceReference':'synthetic-instance','contextLength':4096}
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request=self.rfile.readline().decode()
            headers={}
            while True:
                line=self.rfile.readline().decode().strip()
                if not line:break
                k,v=line.split(':',1);headers[k.lower()]=v.strip()
            if 'lmstudio-greeting' in request:
                raw=b'{"lmstudio":true}'
                self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw)).encode()+b'\r\nConnection: close\r\n\r\n'+raw)
                return
            key=base64.b64encode(hashlib.sha1((headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
            self.wfile.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+key+b'\r\n\r\n')
            def emit(value,opcode=1):
                raw=json.dumps(value).encode() if opcode==1 else value
                size=len(raw)
                prefix=bytes([128|opcode,size]) if size<126 else bytes([128|opcode,126])+struct.pack('!H',size)
                self.wfile.write(prefix+raw)
            count=0
            try:
                while True:
                    head=self.rfile.read(2)
                    if len(head)!=2 or head[0]&15==8:return
                    n=head[1]&127
                    if n==126:n=struct.unpack('!H',self.rfile.read(2))[0]
                    elif n==127:n=struct.unpack('!Q',self.rfile.read(8))[0]
                    if n>4*1024*1024:return
                    mask=self.rfile.read(4) if head[1]&128 else None
                    raw=self.rfile.read(n)
                    if mask:raw=bytes(b^mask[i%4] for i,b in enumerate(raw))
                    if head[0]&15==9:
                        emit(raw,10);continue
                    value=json.loads(raw)
                    if 'authVersion' in value:
                        emit({'success':True});continue
                    # SDK client auth keys differ from runtime authentication;
                    # this fake listener records no authentication material.
                    if value.get('type') not in {'rpcCall','channelCreate','channelSend'}:
                        emit({'success':True});continue
                    calls.append(value)
                    if value['type']=='rpcCall':
                        endpoint=value['endpoint'];params=value.get('parameter',{})
                        if endpoint=='listLoaded':result=[instance]
                        elif endpoint=='getModelInfo':
                            result={**instance,**state['info_override']}
                            if state['instance_after_predict'] and state['generated']:
                                result['instanceReference']='replacement-instance'
                        elif endpoint=='applyPromptTemplate':result={'formatted':'<bos>'+json.dumps(params['history'],ensure_ascii=False)+state['template_suffix']}
                        elif endpoint=='tokenize':
                            count=len(params['inputString'].encode('utf-8'));result={'tokens':list(range(count))}
                        else:raise AssertionError('Forbidden synthetic engine operation: '+endpoint)
                        emit({'type':'rpcResult','callId':value['callId'],'result':result})
                    elif value['type']=='channelCreate':
                        assert value['endpoint']=='predict'
                        channel=value['channelId']
                        if state['replace_on_predict']:
                            assert value['creationParameter']['modelSpecifier']=={'type':'instanceReference','instanceReference':'synthetic-instance'}
                            emit({'type':'channelSend','channelId':channel,'message':{'type':'error','error':{'message':'Synthetic instance unloaded'}}})
                            continue
                        state['generated']+=1
                        emit({'type':'channelSend','channelId':channel,'message':{'type':'fragment','fragment':{'content':'  synthetic answer  ','tokensCount':3,'containsDrafted':False,'reasoningType':'none'}}})
                        if state['hold']:
                            state['streaming'].set();continue
                        emit({'type':'channelSend','channelId':channel,'message':{'type':'success','stats':{'stopReason':state['stop_reason'],'promptTokensCount':count+state['prompt_token_delta'],'predictedTokensCount':3},'modelInfo':model,'loadModelConfig':{'fields':[]},'predictionConfig':{'fields':[]}}})
                    elif value['type']=='channelSend' and value.get('message',{}).get('type')=='cancel':
                        state['cancelled'].set()
                        emit({'type':'channelSend','channelId':value['channelId'],'message':{'type':'success','stats':{'stopReason':'userStopped','promptTokensCount':count,'predictedTokensCount':1},'modelInfo':model,'loadModelConfig':{'fields':[]},'predictionConfig':{'fields':[]}}})
            except (OSError,ValueError,EOFError):
                return
    class Server(socketserver.ThreadingMixIn,socketserver.TCPServer):
        daemon_threads=True
    http=Server(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:yield replace(CONNECTORS['lmstudio'],port=http.server_address[1]),calls,state
    finally:http.shutdown();http.server_close();thread.join(3)


def test_real_sdk_measure_and_generate_share_loaded_handle_without_load_or_prompts(sdk_runtime):
    spec,calls,state=sdk_runtime
    messages=[{'role':'user','content':'  raw question 🙂  '}]
    with open_engine(spec,'fixture') as engine:
        measured=engine.measure(messages,4096)
        assert measured['loaded_context']==4096
        result=engine.generate(messages,32,threading.Event())
    assert result['content']=='  synthetic answer  '
    assert result['input_tokens']==measured['input_tokens']
    assert result['stop_reason']=='eosFound'
    predict=next(c for c in calls if c['type']=='channelCreate')['creationParameter']
    assert predict['modelSpecifier']=={'type':'instanceReference','instanceReference':'synthetic-instance'}
    for call in calls:
        if call.get('endpoint') in {'applyPromptTemplate','tokenize'}:
            assert call['parameter']['specifier']==predict['modelSpecifier']
    assert predict['history']=={'messages':[{'role':'user','content':[{'type':'text','text':'  raw question 🙂  '}]}]}
    assert 'fuzzyPresetIdentifier' not in predict
    fields=predict['predictionConfigStack']['layers'][0]['config']['fields']
    assert any(f.get('value')=='stopAtLimit' for f in fields)
    assert not any(c.get('endpoint') in {'loadModel','unloadModel','getOrLoad'} for c in calls)


def test_instance_replaced_at_prediction_boundary_cannot_run_new_identifier_target(sdk_runtime):
    from app.integrations import IntegrationError
    spec,calls,state=sdk_runtime
    with open_engine(spec,'fixture') as engine:
        engine.measure([{'role':'user','content':'synthetic'}],4096)
        state['replace_on_predict']=True
        with pytest.raises(IntegrationError):engine.generate([],32,threading.Event())
    assert state['generated']==0


def test_real_sdk_limits_read_uses_only_info_calls(sdk_runtime):
    spec,calls,state=sdk_runtime
    with open_engine(spec,'fixture') as engine:
        limits=engine.limits()
    assert (limits['budget_ceiling'],limits['model_max_context'],limits['weights_bytes'])==(4096,4096,1000)
    assert limits['model_key']=='fixture-key' and state['generated']==0
    assert {c.get('endpoint') for c in calls}<={'listLoaded','getModelInfo'}


def test_model_not_loaded_is_reported_by_name_not_as_generic_failure(sdk_runtime):
    from app.integrations import IntegrationError
    spec,calls,state=sdk_runtime
    with pytest.raises(IntegrationError) as caught:
        with open_engine(spec,'not-loaded') as engine:
            engine.limits()
    assert caught.value.code=='MODEL_NOT_LOADED'


# Phase C / AI-01 + AI-02: the real pinned SDK, the real helper subprocess and the real Chat
# workspace against a synthetic engine. Only the two post-generation mismatches that SDK 1.5.0
# can produce are reachable here: it builds the final text from the very fragments it streams,
# and `structured` stays False because the helper never requests a response format.
SECRET_PROMPT = 'SYNTHETIC_PRIVATE_PROMPT_7f3a'


def _workspace(tmp_path, spec):
    from app.chat_workspace import ChatWorkspace
    from app.db import apply_migrations
    from app.integrations import IntegrationManager
    db = tmp_path / 'ai01.db'
    apply_migrations(db)
    manager = IntegrationManager(home=tmp_path)
    manager._states['lmstudio'].update(connection='CONNECTED', selected_model='fixture', models=['fixture'], selection_revision=2)
    return ChatWorkspace(manager, db, engine_factory=lambda _spec, model: open_engine(spec, model)), db


@pytest.mark.parametrize('fault,check', [
    ({'instance_after_predict': True}, 'The loaded model instance changed.'),
    ({'prompt_token_delta': 1}, 'The final token count differed from the measured prompt.'),
    ({'prompt_token_delta': -1}, 'The final token count differed from the measured prompt.'),
])
def test_post_generation_mismatch_is_named_saves_nothing_and_leaks_nothing(sdk_runtime, tmp_path, fault, check):
    from uuid import uuid4
    from app.db import connect
    from app.integrations import IntegrationError
    spec, calls, state = sdk_runtime
    ws, db = _workspace(tmp_path, spec)
    try:
        session = ws.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                             'context_budget': 4096, 'reply_reserve': 32, 'load_approved': False})
        session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
        state.update(fault)
        with pytest.raises(IntegrationError) as caught:
            ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                    'selection_revision': 2, 'text': SECRET_PROMPT})
    finally:
        ws.close()
    assert state['generated'] == 1, 'the mismatch is detected after a real generation'
    assert caught.value.code == 'RESULT_MISMATCH'
    message = str(caught.value)
    assert message == 'The reply did not match the measured request; no pair was saved. Integrity check: ' + check
    for private in (SECRET_PROMPT, 'synthetic answer', 'synthetic-instance', 'replacement-instance', 'fixture-key'):
        assert private not in message
    with connect(db) as conn:
        for table in ('chat_turns', 'reviews'):
            assert conn.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0, table
        assert conn.execute('SELECT count(*) FROM messages WHERE content LIKE ?', ('%synthetic answer%',)).fetchone()[0] == 0
    assert not any(c.get('endpoint') in {'loadModel', 'unloadModel', 'getOrLoad'} for c in calls)


def test_pinned_sdk_cannot_produce_structured_or_divergent_stream_results(sdk_runtime):
    """Narrows AI-01: with SDK 1.5.0 the STRUCTURED_OUTPUT and STREAM_CONTENT checks stay defence in depth."""
    import importlib.metadata
    spec, calls, state = sdk_runtime
    assert importlib.metadata.version('lmstudio') == '1.5.0'
    with open_engine(spec, 'fixture') as engine:
        engine.measure([{'role': 'user', 'content': 'synthetic'}], 4096)
        result = engine.generate([], 32, threading.Event())
    assert result['content'] == '  synthetic answer  '
    predict = next(c for c in calls if c['type'] == 'channelCreate')['creationParameter']
    fields = predict['predictionConfigStack']['layers'][0]['config']['fields']
    assert not any('structured' in str(f.get('key', '')).lower() for f in fields), 'no response format is requested'


# Phase C / AI-04: runtime contracts (identity, token accounting, cancellation, context overflow)
# exercised through the real pinned SDK and helper process. A synthetic engine is not a real model:
# these prove NajdiLab's side of each contract, not LM Studio's behavior on owner hardware.
@pytest.mark.parametrize('drift', [
    {'info_override': {'instanceReference': 'other-instance'}},
    {'info_override': {'contextLength': 2048}},
    {'template_suffix': '<injected system prompt>'},
])
def test_runtime_drift_between_measurement_and_inference_refuses_before_generation(sdk_runtime, drift):
    from app.integrations import IntegrationError
    spec, calls, state = sdk_runtime
    with open_engine(spec, 'fixture') as engine:
        engine.measure([{'role': 'user', 'content': 'synthetic'}], 4096)
        state.update(drift)
        with pytest.raises(IntegrationError) as caught:
            engine.generate([], 32, threading.Event())
    assert caught.value.code == 'MODEL_CHANGED'
    assert state['generated'] == 0, 'no prompt reaches the engine after identity, context or template drift'


def _session(ws, budget, reserve=32):
    return ws.create({'provider': 'lmstudio', 'model': 'fixture', 'selection_revision': 2,
                      'context_budget': budget, 'reply_reserve': reserve, 'load_approved': False})


def _turn(ws, session, text):
    from uuid import uuid4
    return ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                   'selection_revision': 2, 'text': text})


@pytest.mark.parametrize('slack,completes', [(0, True), (-1, False)])
def test_admission_uses_the_full_templated_token_count_plus_reply_reserve(sdk_runtime, tmp_path, slack, completes):
    from app.db import connect
    spec, calls, state = sdk_runtime
    text = 'سؤال اصطناعي 🙂'
    with open_engine(spec, 'fixture') as engine:
        exact = engine.measure([{'role': 'user', 'content': text}], 4096)['input_tokens']
    # The synthetic tokenizer counts UTF-8 bytes of the whole rendered template, BOS marker included.
    rendered = '<bos>' + json.dumps({'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': text}]}]}, ensure_ascii=False)
    assert exact == len(rendered.encode('utf-8'))
    generated_before = state['generated']
    ws, db = _workspace(tmp_path, spec)
    try:
        result = _turn(ws, _session(ws, exact + 32 + slack), text)
    finally:
        ws.close()
    with connect(db) as conn:
        turns = conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0]
    if completes:
        assert result['status'] == 'COMPLETED' and turns == 1
        assert state['generated'] == generated_before + 1
        predict = [c for c in calls if c['type'] == 'channelCreate'][-1]['creationParameter']
        fields = {f['key']: f['value'] for f in predict['predictionConfigStack']['layers'][0]['config']['fields']}
        assert fields['llm.prediction.maxPredictedTokens'] == {'checked': True, 'value': 32}
        assert fields['llm.prediction.contextOverflowPolicy'] == 'stopAtLimit', 'overflow can never roll history'
    else:
        assert result['status'] == 'CONTEXT_LIMIT' and turns == 0
        assert result['new_session']['turns'] == [] and result['new_session']['collect'] is False
        assert state['generated'] == generated_before, 'an over-budget prompt never reaches the engine'


@pytest.mark.parametrize('reason', ['maxPredictedTokensReached', 'contextLengthReached', 'userStopped'])
def test_engine_stop_reason_other_than_eos_is_never_saved(sdk_runtime, tmp_path, reason):
    from app.db import connect
    from app.integrations import IntegrationError
    spec, calls, state = sdk_runtime
    state['stop_reason'] = reason
    ws, db = _workspace(tmp_path, spec)
    try:
        session = _session(ws, 4096)
        session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
        with pytest.raises(IntegrationError):
            _turn(ws, session, 'synthetic')
    finally:
        ws.close()
    assert state['generated'] == 1
    with connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0


def test_stop_during_streaming_cancels_the_engine_channel_and_saves_nothing(sdk_runtime, tmp_path):
    from app.db import connect
    from app.integrations import IntegrationError
    spec, calls, state = sdk_runtime
    state['hold'] = True
    ws, db = _workspace(tmp_path, spec)
    outcome = {}
    try:
        session = _session(ws, 4096)
        session = ws.collect(session['id'], {'enabled': True, 'revision': session['revision']})
        def run():
            try:
                outcome['result'] = _turn(ws, session, 'synthetic')
            except IntegrationError as error:
                outcome['error'] = error
        worker = threading.Thread(target=run)
        worker.start()
        assert state['streaming'].wait(20), 'the engine started streaming'
        assert ws.stop(session['id'])['stop_requested'] is True
        worker.join(30)
        assert not worker.is_alive()
        assert state['cancelled'].wait(10), 'the pinned SDK sent a cancel on the prediction channel'
    finally:
        ws.close()
    assert outcome.get('error') is not None and outcome['error'].code == 'STOPPED'
    with connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM chat_turns').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0
