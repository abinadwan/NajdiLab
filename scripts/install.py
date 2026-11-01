"""Prepare local standard-library runtime without database writes or downloads."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

from local_runtime import check_runtime

ROOT = Path(__file__).resolve().parents[1]


def install(check_only=False):
    check_runtime()
    for name in ('app/server.py', 'static/index.html', '.env.example'):
        if not (ROOT / name).is_file():
            raise SystemExit('Missing source file: ' + name + '; restore the complete source checkout.')
    if not list((ROOT / 'migrations').glob('*.sql')):
        raise SystemExit('Missing migrations; restore the complete source checkout.')
    if check_only:
        print('PASS: Python, SQLite and source layout. No database, migrations or services were changed.')
        return
    environment = ROOT / '.venv'
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if environment.exists():
        if not executable.is_file():
            raise SystemExit('Existing .venv is incomplete. Preserve it and select a clean checkout; setup will not replace it.')
    else:
        venv.EnvBuilder(with_pip=False).create(environment)
    subprocess.run([str(executable), str(ROOT / 'scripts/install.py'), '--check'], check=True)
    for name in ('data', 'datasets', 'exports', 'reports', 'backups'):
        (ROOT / name).mkdir(exist_ok=True)
    try:
        with (ROOT / '.env').open('xb') as target:
            target.write((ROOT / '.env.example').read_bytes())
    except FileExistsError:
        pass
    print('Local setup complete. Core dependencies: Python standard library only; nothing downloaded.')
    print('.env is a private reference and is not automatically loaded; set variables in your shell.')
    print('Default URL: http://127.0.0.1:8770 (or NAJDILAB_PORT).')
    print('Start this checkout with .\\run.ps1 on Windows or sh ./run.sh on Linux/WSL.')
    print('Launch applies approved source migrations; inspect them before upgrading existing data.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only runtime/source verification')
    arguments = parser.parse_args()
    try:
        install(arguments.check)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('Setup failed. Use a writable checkout with working Python venv support; existing settings and data were preserved. ' + str(exc)) from exc
