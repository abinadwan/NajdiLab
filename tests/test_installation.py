"""Exercise onboarding in disposable checkouts, including paths containing spaces."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path):
    root = tmp_path / 'checkout with spaces'
    root.mkdir()
    for name in ('scripts', 'app', 'static', 'config', 'migrations'):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('run.ps1', 'run.sh', '.env.example'):
        shutil.copy2(ROOT / name, root / name)
    return root


def invoke(root, *args):
    return subprocess.run([sys.executable, str(root / 'scripts/install.py'), *args], cwd=root.parent,
                          capture_output=True, text=True, timeout=40)


def test_install_check_does_not_create_database_or_environment(tmp_path):
    root = project(tmp_path)
    result = invoke(root, '--check')
    assert result.returncode == 0, result.stderr
    assert not (root / 'data').exists()
    assert not (root / '.venv').exists()
    assert not (root / '.env').exists()


def test_install_repeat_preserves_database_settings_and_interpreter(tmp_path):
    root = project(tmp_path)
    (root / 'data').mkdir()
    database = root / 'data/najdilab.db'
    database.write_bytes(b'existing-private-state-sentinel')
    settings = root / '.env'
    settings.write_text('CUSTOM_SETTING=preserve-me')
    first = invoke(root)
    assert first.returncode == 0, first.stderr
    interpreter = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    stamp = interpreter.stat().st_mtime_ns
    second = invoke(root)
    assert second.returncode == 0, second.stderr
    assert interpreter.stat().st_mtime_ns == stamp
    assert database.read_bytes() == b'existing-private-state-sentinel'
    assert settings.read_text() == 'CUSTOM_SETTING=preserve-me'
    assert not list((root / 'data').glob('*-wal'))


def test_install_copies_only_example_configuration(tmp_path):
    root = project(tmp_path)
    result = invoke(root)
    assert result.returncode == 0, result.stderr
    assert (root / '.env').read_bytes() == (root / '.env.example').read_bytes()
    assert not (root / 'data/najdilab.db').exists()
    assert 'not automatically loaded' in result.stdout


def test_install_rejects_incomplete_existing_environment(tmp_path):
    root = project(tmp_path)
    (root / '.venv').mkdir()
    result = invoke(root)
    assert result.returncode != 0
    assert 'incomplete' in result.stderr.lower()
    assert not (root / '.env').exists()


def test_launch_rejects_unsupported_python_before_import_or_writes(tmp_path):
    root = project(tmp_path)
    command = "import sys,runpy;sys.path.insert(0," + repr(str(root/'scripts')) + ");sys.version_info=(3,10,0);runpy.run_path(" + repr(str(root/'scripts/launch.py')) + ",run_name='__main__')"
    result = subprocess.run([sys.executable, '-c', command], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Python 3.11+' in result.stderr
    assert not (root / 'data').exists()


def test_launcher_defaults_to_no_demo_and_preserves_explicit_choice(tmp_path):
    root = project(tmp_path)
    (root / 'app/server.py').write_text('import os; print("SEED="+os.environ["NAJDILAB_NO_DEMO"])')
    for value, expected in ((None, '1'), ('0', '0')):
        env = {k:v for k,v in os.environ.items() if k != 'NAJDILAB_NO_DEMO'}
        if value is not None:
            env['NAJDILAB_NO_DEMO'] = value
        result = subprocess.run([sys.executable, str(root/'scripts/launch.py')], env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert 'SEED='+expected in result.stdout


def test_install_permission_failure_is_actionable(tmp_path):
    root = project(tmp_path)
    command = "import sys,runpy,pathlib;sys.path.insert(0," + repr(str(root/'scripts')) + ");pathlib.Path.mkdir=lambda *a,**k: (_ for _ in ()).throw(PermissionError('denied'));runpy.run_path("+repr(str(root/'scripts/install.py'))+",run_name='__main__')"
    result = subprocess.run([sys.executable,'-c',command],capture_output=True,text=True,timeout=10)
    assert result.returncode != 0
    assert 'writable' in result.stderr.lower()
    assert 'Traceback' not in result.stderr


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell launcher check')
def test_powershell_launcher_selects_local_environment_and_propagates_exit(tmp_path):
    root = project(tmp_path)
    result = invoke(root)
    assert result.returncode == 0, result.stderr
    (root / 'app/server.py').write_text('import sys;print(sys.prefix);raise SystemExit(7)')
    env = {k:v for k,v in os.environ.items() if k != 'NAJDILAB_PYTHON'}
    result = subprocess.run(['powershell','-NoProfile','-File',str(root/'run.ps1')],env=env,
                            capture_output=True,text=True,timeout=20)
    assert result.returncode == 7, result.stderr
    assert str(root / '.venv') in result.stdout
