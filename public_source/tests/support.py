"""Disposable exact-candidate HTTP fixtures; never imports the parent checkout."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.package import copy_candidate

ROOT = Path(__file__).resolve().parents[1]

class CandidateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='core acceptance ')
        cls.work = Path(cls.temp.name) / 'candidate'
        copy_candidate(ROOT, cls.work)
        cls.env = {k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','NAJDILAB_PYTHON','NAJDILAB_ALLOW_LEGACY_INGEST','NAJDILAB_INGEST_TOKEN'}}
        cls.env['NAJDILAB_INGEST_TOKEN'] = 'fictional-acceptance-only'
        cls.start()

    @classmethod
    def start(cls):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); cls.port=s.getsockname()[1]
        cls.env['NAJDILAB_PORT']=str(cls.port)
        cls.proc=subprocess.Popen([sys.executable,'-m','app.server'],cwd=cls.work,env=cls.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.base=f'http://127.0.0.1:{cls.port}'
        for _ in range(100):
            try:
                with urlopen(cls.base+'/api/v1/session',timeout=1) as r:cls.csrf=json.loads(r.read())['csrf_token'];return
            except OSError:time.sleep(.05)
        raise AssertionError('Disposable candidate did not start')

    @classmethod
    def stop(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate() if os.name=='nt' else cls.proc.send_signal(signal.SIGINT)
            cls.proc.wait(timeout=10)

    @classmethod
    def tearDownClass(cls):
        cls.stop();cls.temp.cleanup()

    @classmethod
    def request(cls,path,body=None,headers=None,method=None,raw=False):
        headers={**({'Content-Type':'application/json','X-NajdiLab-CSRF':cls.csrf} if body is not None else {}),**(headers or {})}
        req=Request(cls.base+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers=headers,method=method)
        try:response=urlopen(req,timeout=10)
        except HTTPError as exc:response=exc
        with response:
            data=response.read()
            return response.status,(data if raw else json.loads(data))

    @classmethod
    def rows(cls,sql,params=()):
        c=sqlite3.connect(cls.work/'data/najdilab.db');c.row_factory=sqlite3.Row
        try:return [dict(r) for r in c.execute(sql,params)]
        finally:c.close()

    def new_review(self,name=None,**extra):
        import uuid
        key=name or uuid.uuid4().hex
        payload={'conversation_id':key,'source':'import','title':'ورشة بطاقات خيالية','user_message':'وش أكتب على بطاقة الورشة؟','assistant_response':'اكتب عنوان تجريبي.','demo':True,'metadata':{'synthetic':True},**extra}
        code,_=self.request('/api/v1/turn',payload,{'Authorization':'Bearer fictional-acceptance-only'})
        self.assertEqual(code,201)
        return self.rows('SELECT r.* FROM reviews r JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id WHERE c.external_conversation_id=?',(key,))[0]

    def snapshot(self,rid):return self.rows('SELECT * FROM reviews WHERE id=?',(rid,))[0]
