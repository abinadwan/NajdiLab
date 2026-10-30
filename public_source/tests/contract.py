"""Run inside the exact built candidate: python -m unittest discover -s tests."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.package import copy_candidate

ROOT = Path(__file__).resolve().parents[1]

class CandidateContract(unittest.TestCase):
    def test_independent_application(self):
        # Copy a pristine candidate; no imports/paths from its parent checkout.
        import shutil
        with tempfile.TemporaryDirectory(prefix='najdilab isolated ') as tmp:
            work=Path(tmp)/'app';copy_candidate(ROOT,work)
            env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','NAJDILAB_PYTHON','NAJDILAB_ALLOW_LEGACY_INGEST','NAJDILAB_INGEST_TOKEN'}}
            def run(*args,check=True):return subprocess.run([sys.executable,*args],cwd=work,env=env,capture_output=True,check=check,timeout=30)
            run('scripts/install.py','--check');run('scripts/install.py');run('scripts/install.py')
            self.assertFalse((work/'data/najdilab.db').exists())
            denied=run('scripts/synthetic_demo.py',check=False);self.assertNotEqual(denied.returncode,0);self.assertFalse((work/'data/najdilab.db').exists())
            run('scripts/synthetic_demo.py','--confirm-disposable')
            self.assertNotEqual(run('scripts/synthetic_demo.py','--confirm-disposable',check=False).returncode,0)
            s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close();env.update(NAJDILAB_PORT=str(port),NAJDILAB_INGEST_TOKEN='synthetic-test-only')
            launch=['powershell','-NoProfile','-File','run.ps1'] if os.name=='nt' else ['sh','run.sh']
            p=subprocess.Popen(launch,cwd=work,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            url=f'http://127.0.0.1:{port}'
            def request(path,body=None,headers=None):
                req=Request(url+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers=headers or {})
                try:
                    with urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())
                except HTTPError as e:return e.code,json.loads(e.read())
            try:
                for _ in range(100):
                    try:
                        status,health=request('/api/v1/health')
                        if status==200:break
                    except OSError:time.sleep(.1)
                else:self.fail('candidate startup failed')
                with urlopen(url) as r:self.assertIn(b'NajdiLab',r.read())
                session=request('/api/v1/session')[1]['csrf_token'];headers={'Content-Type':'application/json','X-NajdiLab-CSRF':session}
                turn={'conversation_id':'candidate-contract','source':'import','user_message':'كيف ألوّن بطاقة التجربة؟','assistant_response':'جرّب لون واضح.','demo':True,'metadata':{'synthetic':True}}
                self.assertEqual(request('/api/v1/turn',turn,{'Content-Type':'application/json'})[0],401)
                self.assertEqual(request('/api/v1/turn',turn,{'Content-Type':'application/json','Authorization':'Bearer synthetic-test-only'})[0],201)
                self.assertEqual(request('/api/v1/conversations',{}, {'Content-Type':'application/json'})[0],403)
                self.assertEqual(request('/api/v1/config',headers={'Origin':'https://untrusted.invalid'})[0],403)
                self.assertEqual(request('/api/v1/config',headers={'Host':'untrusted.invalid'})[0],403)
                self.assertEqual(request('/api/v1/conversations',{}, {**headers,'Content-Type':'text/plain'})[0],415)
                self.assertEqual(request('/api/v1/conversations',[],headers)[0],400)
                self.assertEqual(request('/%2e%2e/app/db.py')[0],403)
                for path in ['/api/v1/phase38/v009/human-review','/api/v1/training/models','/api/v1/phase39/readiness']:
                    st,data=request(path);self.assertEqual(st,503);self.assertEqual(data['code'],'EXTENSION_UNAVAILABLE')
                self.assertEqual(request('/api/v1/training/model-acquisition/acquire',{},headers)[0],503)
                q=request('/api/v1/review-queue')[1]['items'];self.assertTrue(q)
                rid=q[0]['id'];original=q[0]['original_response'];correction='رقّم البطاقة واكتب عنوانها بخط واضح.'
                st,_=request(f'/api/v1/reviews/{rid}/correct',{'expected_updated_at':q[0]['updated_at'],'review_status':'FULL_CORRECTION','corrected_response':correction,'reviewer_identity':'human','training_eligible':True},headers);self.assertEqual(st,200)
                conn=sqlite3.connect(work/'data/najdilab.db');row=conn.execute('select original_response,corrected_response from reviews where id=?',(rid,)).fetchone();conn.close();self.assertEqual(row,(original,correction))
                # Independently fictional numbered cards supply enough conversations for the
                # unchanged 10-15% / >=3-conversation evaluation split, not optimizer training.
                for number in range(24):
                    extra={**turn,'conversation_id':f'fictional-card-{number}',
                           'user_message':f'وش أكتب على بطاقة التجربة رقم {number}؟',
                           'assistant_response':f'اكتب بطاقة تجريبية رقم {number} بخط واضح.'}
                    self.assertEqual(request('/api/v1/turn',extra,{'Content-Type':'application/json','Authorization':'Bearer synthetic-test-only'})[0],201)
                # Approve remaining synthetic rows so the existing export-integrity gate is satisfied.
                for row in request('/api/v1/review-queue')[1]['items']:self.assertEqual(request(f"/api/v1/reviews/{row['id']}/approve",{'expected_updated_at':row['updated_at'],'training_eligible':True},headers)[0],200)
                self.assertTrue(request('/api/v1/training-dataset?include_demo=1')[1]['reviews'])
                st,export=request('/api/v1/exports',{'include_demo':True},headers);self.assertEqual(st,201,export)
                versions=request('/api/v1/dataset-versions')[1]['items'];self.assertTrue(versions)
                version=versions[0]['version'];self.assertEqual(request(f'/api/v1/dataset-versions/{version}/health')[0],200)
                self.assertEqual(request(f'/api/v1/dataset-versions/{version}/quality-findings')[0],200)
                run('scripts/backup.py');archive=next((work/'backups').glob('*.zip'))
                with zipfile.ZipFile(archive) as z:self.assertIsNone(z.testzip());z.extractall(Path(tmp)/'restore')
                c=sqlite3.connect(Path(tmp)/'restore/data/najdilab.db');self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('pragma foreign_key_check').fetchall());c.close()
            finally:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=10)
                else:p.send_signal(signal.SIGINT)
                p.wait(timeout=10)
            # A fresh isolated import must never touch historical modules.
            probe=run('-c',"import app.server,sys; assert not any(x.startswith(('app.phase','app.training_control','app.runtime_control','app.platform_state')) for x in sys.modules)")
            self.assertEqual(probe.returncode,0)
