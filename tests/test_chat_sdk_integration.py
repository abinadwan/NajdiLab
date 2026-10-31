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
    state={'replace_on_predict':False,'generated':0}
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
                        elif endpoint=='getModelInfo':result=instance
                        elif endpoint=='applyPromptTemplate':result={'formatted':'<bos>'+json.dumps(params['history'],ensure_ascii=False)}
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
                        emit({'type':'channelSend','channelId':channel,'message':{'type':'success','stats':{'stopReason':'eosFound','promptTokensCount':count,'predictedTokensCount':3},'modelInfo':model,'loadModelConfig':{'fields':[]},'predictionConfig':{'fields':[]}}})
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
        measured=engine.measure(messages)
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
        engine.measure([{'role':'user','content':'synthetic'}])
        state['replace_on_predict']=True
        with pytest.raises(IntegrationError):engine.generate([],32,threading.Event())
    assert state['generated']==0
