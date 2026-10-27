"""Candidate-only installation failures and launcher checks; all storage disposable."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from tests.package import copy_candidate

ROOT=Path(__file__).resolve().parents[1]

class CandidateInstallation(unittest.TestCase):
    def test_readonly_check_shell_install_repeat_and_existing_state(self):
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp)/'candidate with spaces';copy_candidate(ROOT,work)
            def run(args,env=None):return subprocess.run(args,cwd=work,env=env,capture_output=True,timeout=45)
            self.assertEqual(run([sys.executable,'scripts/install.py','--check']).returncode,0)
            self.assertFalse((work/'data').exists());self.assertFalse((work/'.venv').exists())
            (work/'data').mkdir();(work/'data/najdilab.db').write_bytes(b'fictional opaque preserve sentinel');(work/'.env').write_text('FICTIONAL_SETTING=preserve')
            env={**os.environ,'NAJDILAB_PYTHON':sys.executable}
            command=['powershell','-NoProfile','-File','scripts/install.ps1'] if os.name=='nt' else ['sh','scripts/install.sh']
            self.assertEqual(run(command,env).returncode,0)
            executable=work/('.venv/Scripts/python.exe' if os.name=='nt' else '.venv/bin/python');stamp=executable.stat().st_mtime_ns
            self.assertEqual(run(command,env).returncode,0);self.assertEqual(executable.stat().st_mtime_ns,stamp)
            self.assertEqual((work/'data/najdilab.db').read_bytes(),b'fictional opaque preserve sentinel');self.assertEqual((work/'.env').read_text(),'FICTIONAL_SETTING=preserve')

    def test_unsupported_python_stops_before_application_import_or_storage(self):
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp)/'candidate';copy_candidate(ROOT,work)
            code="import sys;sys.path.insert(0,'scripts');from local_runtime import check_runtime;sys.version_info=(3,10,0);check_runtime()"
            result=subprocess.run([sys.executable,'-c',code],cwd=work,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertIn(b'Python 3.11+',result.stderr);self.assertFalse((work/'data').exists())

    def test_port_conflict_stops_before_sqlite_initialization(self):
        with tempfile.TemporaryDirectory() as temp,socket.socket() as listener:
            work=Path(temp)/'candidate';copy_candidate(ROOT,work);listener.bind(('127.0.0.1',0));listener.listen()
            env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'};env['NAJDILAB_PORT']=str(listener.getsockname()[1])
            result=subprocess.run([sys.executable,'-m','app.server'],cwd=work,env=env,capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertFalse((work/'data/najdilab.db').exists())
