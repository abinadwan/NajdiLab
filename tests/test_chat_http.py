import json
from http.client import HTTPConnection
import threading
from unittest.mock import patch

import pytest

from app import server
from app.db import apply_migrations
from app.http_security import CSRF_TOKEN
from app.chat_workspace import ChatWorkspace
from app.integrations import IntegrationError
from test_chat_workspace import Engine


@pytest.fixture
def api(tmp_path):
    db = tmp_path/'chat.db'
    apply_migrations(db)
    http = server.NajdiLabHTTPServer(('127.0.0.1',0),server.NajdiLabHandler)
    http.integrations._states['lmstudio'].update(connection='CONNECTED',selected_model='fixture',selection_revision=2)
    http.chat = ChatWorkspace(http.integrations,db,engine_factory=Engine().open)
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    def request(path, data=None, token=True, origin=None, method=None):
        conn = HTTPConnection('127.0.0.1',http.server_port,timeout=4)
        headers = {'Content-Type':'application/json'}
        if token: headers['X-NajdiLab-CSRF'] = CSRF_TOKEN
        if origin: headers['Origin'] = origin
        conn.request(method or ('POST' if data is not None else 'GET'),path,
                     json.dumps(data).encode() if data is not None else None,headers)
        response=conn.getresponse()
        result=response.status,json.loads(response.read())
        conn.close()
        return result
    try: yield request, http
    finally:
        http.shutdown(); http.server_close(); thread.join(3)


def test_chat_routes_and_security(api):
    request,_=api
    data={'provider':'lmstudio','model':'fixture','selection_revision':2,'context_budget':512,'reply_reserve':32,'load_approved':False}
    assert request('/api/v1/chat/sessions',data,token=False)[0]==403
    assert request('/api/v1/chat/sessions',data,origin='http://evil.example')[0]==403
    status,session=request('/api/v1/chat/sessions',data)
    assert status==201 and session['collect'] is False
    assert request('/api/v1/chat/sessions')[0]==200
    path='/api/v1/chat/sessions/'+session['id']
    from uuid import uuid4
    status,result=request(path+'/send',{'request_id':str(uuid4()),'revision':session['revision'],'selection_revision':2,'text':'هلا'})
    assert status==200 and result['status']=='COMPLETED'
    assert request(path)[1]['turns'][0]['user']=='هلا'
    assert request(path+'/stop',{})[0]==200


def test_training_writes_retired_before_body_and_history_is_read_only(api,tmp_path):
    request,_=api
    with patch.object(server.NajdiLabHandler,'_body',side_effect=AssertionError('body must not be read')):
        for method in ('POST','PATCH','DELETE'):
            status,result=request('/api/v1/training/jobs/train-20261031-001/start-full-training',{},method=method)
            assert status==410 and result['code']=='TRAINING_EXTERNAL_ONLY'
    assert request('/api/v1/training/jobs/train-20261031-001/execution-gate')[0]==410
    with patch('app.training_control.TRAINING_ROOT',tmp_path/'legacy'), patch('app.training_control.JOBS_ROOT',tmp_path/'legacy/jobs'):
        assert request('/api/v1/training/jobs')[1]=={'items':[]}
        assert not (tmp_path/'legacy').exists()


def test_hardware_requires_explicit_read_only_approval(api):
    request,_=api
    assert request('/api/v1/chat/hardware',{})[0]==403
    with patch('app.chat_workspace.hardware_snapshot',return_value={'read_only':True,'recommendation':{'recommended_context':None}}) as probe:
        assert request('/api/v1/chat/hardware',{'approved':True})[0]==200
        assert probe.call_count==1


def test_selected_model_hardware_uses_read_only_limits_and_survives_runtime_failure(api):
    request,http=api
    body={'approved':True,'provider':'lmstudio','model':'fixture','selection_revision':2}
    status,result=request('/api/v1/chat/hardware',body)
    assert status==200 and result['read_only'] is True
    assert result['recommendation']['model_max_context']==8192
    assert request('/api/v1/chat/hardware',{**body,'selection_revision':1})[1]['warnings'][-1]=='STALE_SELECTION'
    assert request('/api/v1/chat/hardware',{**body,'path':'C:/secrets'})[0]==400


def test_status_reads_stay_live_during_a_turn_and_disconnect_waits_for_it(api):
    request,http=api
    data={'provider':'lmstudio','model':'fixture','selection_revision':2,'context_budget':512,'reply_reserve':32,'load_approved':False}
    session=request('/api/v1/chat/sessions',data)[1]
    engine=http.chat.engine_factory.__self__
    engine.started,engine.release=threading.Event(),threading.Event()
    from uuid import uuid4
    results=[]
    turn=threading.Thread(target=lambda:results.append(request('/api/v1/chat/sessions/'+session['id']+'/send',
        {'request_id':str(uuid4()),'revision':session['revision'],'selection_revision':2,'text':'x'})))
    turn.start()
    assert engine.started.wait(3)
    assert request('/api/v1/integrations')[0]==200
    assert http.integrations.snapshot()['ok'] is True
    with pytest.raises(IntegrationError) as busy:
        with http.integrations.chat_lease('lmstudio','fixture',2):
            pass
    assert busy.value.code=='ENGINE_BUSY'
    done=threading.Event()
    def disconnect():
        http.integrations.action('lmstudio','disconnect',{'approved':True})
        done.set()
    closer=threading.Thread(target=disconnect)
    closer.start()
    assert not done.wait(.3)
    engine.release.set()
    turn.join(4);closer.join(4)
    assert done.is_set() and results[0][1]['status']=='COMPLETED'
