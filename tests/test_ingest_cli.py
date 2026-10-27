import pathlib, subprocess, os

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_ingest_cli_requires_explicit_secret_before_any_network_call():
    environment = {key: value for key, value in os.environ.items() if key != 'NAJDILAB_INGEST_TOKEN'}
    command = "import runpy,urllib.request; urllib.request.urlopen=lambda *a,**k: (_ for _ in ()).throw(AssertionError('NETWORK_MUST_NOT_BE_USED')); runpy.run_path(" + repr(str(REPO / 'scripts/ingest_test.py')) + ",run_name='__main__')"
    result = subprocess.run([os.sys.executable, '-c', command], capture_output=True, text=True, env=environment, timeout=15)
    assert result.returncode != 0
    assert 'NAJDILAB_INGEST_TOKEN' in result.stderr
    assert 'NETWORK_MUST_NOT_BE_USED' not in result.stderr

def test_ingest_cli_rejects_a_different_checkout_before_writing(tmp_path):
    import json
    environment = dict(os.environ, NAJDILAB_INGEST_TOKEN='synthetic-cli-only', NAJDILAB_PORT='8870')
    command = "import runpy,urllib.request,io,json; events=[]; "
    command += "def_placeholder=0\n"
    command += "def fake_open(request,*a,**k):\n url=getattr(request,'full_url',request)\n method=request.get_method() if hasattr(request,'get_method') else 'GET'\n assert method=='GET', 'NETWORK_WRITE_MUST_NOT_BE_USED'\n assert url=='http://127.0.0.1:8870/api/v1/health', url\n return io.BytesIO(json.dumps({'ok':True,'service':'NajdiLab','database':" + repr(str(tmp_path/'different.db')) + "}).encode())\n"
    command += "urllib.request.urlopen=fake_open\nrunpy.run_path(" + repr(str(REPO/'scripts/ingest_test.py')) + ",run_name='__main__')"
    result = subprocess.run([os.sys.executable, '-c', command], capture_output=True, text=True, env=environment, timeout=15)
    assert result.returncode != 0
    assert 'different NajdiLab checkout' in result.stderr
    assert 'NETWORK_WRITE_MUST_NOT_BE_USED' not in result.stderr

def test_ingest_cli_uses_the_selected_port_and_credential_for_a_matching_checkout():
    environment = dict(os.environ, NAJDILAB_INGEST_TOKEN='synthetic-cli-only', NAJDILAB_PORT='8870')
    expected_db = str(REPO / 'data/najdilab.db')
    command = "import runpy,urllib.request,io,json; calls=[]\n"
    command += "def fake_open(request,*a,**k):\n url=getattr(request,'full_url',request)\n method=request.get_method() if hasattr(request,'get_method') else 'GET'\n calls.append((method,url))\n if method=='GET':\n  assert url=='http://127.0.0.1:8870/api/v1/health'\n  return io.BytesIO(json.dumps({'ok':True,'service':'NajdiLab','database':" + repr(expected_db) + "}).encode())\n assert url=='http://127.0.0.1:8870/api/v1/turn'\n assert request.get_header('Authorization')=='Bearer synthetic-cli-only'\n return io.BytesIO(b'{\"ok\":true}')\n"
    command += "urllib.request.urlopen=fake_open\nrunpy.run_path(" + repr(str(REPO/'scripts/ingest_test.py')) + ",run_name='__main__')\nassert len(calls)==2"
    result = subprocess.run([os.sys.executable, '-c', command], capture_output=True, text=True, env=environment, timeout=15)
    assert result.returncode == 0, result.stderr
    assert 'synthetic-cli-only' not in result.stdout + result.stderr
