"""Chat V2 / NajdiLab Native acceptance runner for the owner's Windows + RTX machine.

Safe by construction:
- Run it from an ISOLATED development checkout, never from the permanent
  installation folder. It refuses to run inside a folder that contains the
  given --database.
- The permanent database is only ever opened READ-ONLY to take an online copy
  (SQLite backup API) into a new temporary folder. Migrations run on the copy.
- Real model steps need explicit flags (--ollama-model with --approve-model-load,
  --llama-server with --gguf). Without them those steps are NOT TESTED.
- No memory stress test: each context is tried once; a failure is reported.

Every step is reported as PASS, FAIL, BLOCKED, NOT TESTED or SKIPPED, with
details, into a JSON and a Markdown report.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list[dict] = []
TABLES = ('chat_sessions', 'chat_turns', 'chat_requests', 'chat_session_bindings', 'conversations', 'messages',
          'reviews', 'review_events', 'manual_sft_items', 'direct_language_texts', 'preference_pairs')


def record(step, status, detail=''):
    RESULTS.append({'step': step, 'status': status, 'detail': detail})
    print(f'[{status}] {step}' + (f' — {detail}' if detail else ''), flush=True)


def run(step, command, env=None, timeout=1800):
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=ROOT, env={**os.environ, **(env or {})}, capture_output=True, text=True,
                              timeout=timeout, encoding='utf-8', errors='replace')
    except (OSError, subprocess.TimeoutExpired) as error:
        record(step, 'FAIL', f'{type(error).__name__}')
        return None
    tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
    record(step, 'PASS' if done.returncode == 0 else 'FAIL', f'{time.monotonic() - started:.0f}s · ' + ' | '.join(tail))
    return done


def environment():
    info = {'os': platform.platform(), 'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
            'node': shutil.which('node'), 'nvidia_smi': shutil.which('nvidia-smi')}
    if info['nvidia_smi']:
        try:
            info['gpus'] = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
                                          capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            info['gpus'] = 'unavailable'
    record('environment', 'PASS', json.dumps(info, ensure_ascii=False))
    return info


def counts(db):
    conn = sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES if t in names}
    finally:
        conn.close()


def migration_copy(database, work):
    """Copy the permanent DB read-only, migrate the copy, prove nothing was lost."""
    from app.db import apply_migrations, backup_db
    from app.chat_history import saved_sessions_page
    source = Path(database).resolve()
    if not source.is_file():
        record('migration 008 on a copy', 'BLOCKED', 'database not found')
        return
    copy = work / 'copy' / 'najdilab.db'
    backup_db(source, copy)  # opens the source read-only
    before = counts(copy)
    apply_migrations(copy)
    after = counts(copy)
    conn = sqlite3.connect(copy)
    integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
    fk = conn.execute('PRAGMA foreign_key_check').fetchall()
    applied = [r[0] for r in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    conn.close()
    lost = {t: (before[t], after.get(t)) for t in before if after.get(t) != before[t]}
    ok = not lost and integrity == 'ok' and not fk and '008_chat_experience_v2.sql' in applied
    record('migration 008 on a copy', 'PASS' if ok else 'FAIL',
           f'counts {before} → unchanged={not lost}; integrity={integrity}; fk={len(fk)}; source untouched')
    items, total = saved_sessions_page(copy, 200, 0)
    opened = 0
    from app.chat_workspace import ChatWorkspace
    from app.integrations import IntegrationManager
    ws = ChatWorkspace(IntegrationManager(home=work), copy, artifact_roots=[], backups_root=None)
    try:
        for item in items:
            ws.get(item['id'])
            opened += 1
    finally:
        ws.close()
    record('existing conversations open after migration (copy)', 'PASS' if opened == len(items) else 'FAIL',
           f'{opened} of {total} listed sessions opened')


def native(server, gguf, contexts, layers, work):
    from app.native_runtime import NativeRuntime
    from app.chat_workspace import ChatWorkspace
    from app.db import apply_migrations
    from app.integrations import IntegrationManager
    model = Path(gguf).resolve()
    runtime = NativeRuntime(server, model.parent)
    devices = runtime.devices()
    # A GPU run needs a device; a CPU-only run (gpu_layers 0) does not.
    record('native: devices seen by llama-server', 'PASS' if devices or layers == '0' else 'FAIL',
           json.dumps(devices, ensure_ascii=False) or 'none (CPU build)')
    db = work / 'native.db'
    apply_migrations(db)
    ws = ChatWorkspace(IntegrationManager(home=work), db, native=runtime, engine_factory=runtime.engine_factory(),
                       artifact_roots=[], backups_root=None)
    try:
        for context in contexts:
            step = f'native: {model.name} at {context} (gpu_layers={layers})'
            try:
                status = runtime.start({'approved': True, 'model': model.name, 'context_budget': context, 'gpu_layers': layers})
            except Exception as error:  # noqa: BLE001 — report every start failure, including OOM
                record(step, 'FAIL', f'{getattr(error, "code", type(error).__name__)}: {error}')
                continue
            events = []
            try:
                session = ws.create({'provider': 'native', 'model': model.name, 'selection_revision': runtime.revision,
                                     'context_budget': context, 'reply_reserve': min(1024, context // 4), 'load_approved': False})
                result = ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                                 'selection_revision': runtime.revision,
                                                 'text': 'Reply with one short sentence about the weather.'}, on_event=events.append)
                turn = result['session']['turns'][-1]
                thinking = sum(1 for e in events if e['type'] == 'thinking')
                record(step, 'PASS', f"tokens {turn['input_tokens']}+{turn['output_tokens']}; streamed deltas "
                       f"{sum(1 for e in events if e['type'] == 'content')}; thinking deltas {thinking}; "
                       f"measured VRAM {runtime.status().get('measured_vram_bytes')}")
            except Exception as error:  # noqa: BLE001
                record(step, 'FAIL', f'{getattr(error, "code", type(error).__name__)} {getattr(error, "check", "") or ""}')
            # Stop during generation never saves.
            try:
                session = ws.create({'provider': 'native', 'model': model.name, 'selection_revision': runtime.revision,
                                     'context_budget': context, 'reply_reserve': min(1024, context // 4), 'load_approved': False})
                sid = session['id']
                # Stop as soon as the first answer or thinking token arrives.
                stopper = lambda e, sid=sid: ws.stop(sid) if e['type'] in {'content', 'thinking'} else None
                timer = threading.Timer(60, lambda: None)
                try:
                    ws.send(sid, {'request_id': str(uuid4()), 'revision': session['revision'],
                                  'selection_revision': runtime.revision, 'text': 'Count slowly from 1 to 500.'},
                            on_event=stopper)
                    record(step + ' stop', 'FAIL', 'reply finished before Stop; rerun with a longer prompt')
                except Exception as error:  # noqa: BLE001
                    saved = len(ws.get(session['id'])['turns'])
                    record(step + ' stop', 'PASS' if getattr(error, 'code', '') == 'STOPPED' and saved == 0 else 'FAIL',
                           f'{getattr(error, "code", "")}; saved turns {saved}')
                finally:
                    timer.cancel()
            finally:
                runtime.stop({'approved': True})
                record(step + ' unload', 'PASS' if runtime.status()['state'] == 'STOPPED' else 'FAIL', runtime.status()['state'])
    finally:
        runtime.shutdown()
        ws.close()


def ollama(model, contexts, work):
    from app.chat_engine import open_engine
    from app.chat_workspace import ChatWorkspace
    from app.db import apply_migrations
    from app.integrations import IntegrationManager
    manager = IntegrationManager(home=Path.home())
    manager.action('ollama', 'connect', {'approved': True})
    manager.action('ollama', 'select', {'approved': True, 'model': model})
    db = work / 'ollama.db'
    apply_migrations(db)
    ws = ChatWorkspace(manager, db, engine_factory=open_engine, artifact_roots=[], backups_root=None)
    try:
        revision = manager.snapshot()['items']
        revision = next(i for i in revision if i['id'] == 'ollama')['selection_revision']
        for context in contexts:
            step = f'ollama: {model} at {context}'
            events = []
            try:
                session = ws.create({'provider': 'ollama', 'model': model, 'selection_revision': revision,
                                     'context_budget': context, 'reply_reserve': min(3072, context // 3), 'load_approved': True})
                result = ws.send(session['id'], {'request_id': str(uuid4()), 'revision': session['revision'],
                                                 'selection_revision': revision,
                                                 'text': 'Reply with one short sentence about the weather.'}, on_event=events.append)
                turn = result['session']['turns'][-1]
                record(step, 'PASS', f"tokens {turn['input_tokens']}+{turn['output_tokens']}; content deltas "
                       f"{sum(1 for e in events if e['type'] == 'content')}; thinking deltas "
                       f"{sum(1 for e in events if e['type'] == 'thinking')}; timings {json.dumps(result.get('timings'))}")
            except Exception as error:  # noqa: BLE001
                record(step, 'FAIL', f'{getattr(error, "code", type(error).__name__)} {getattr(error, "check", "") or ""} '
                       f'{getattr(error, "hint", "") or ""}')
    finally:
        ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', default='acceptance-report', help='output folder for the JSON/Markdown report')
    parser.add_argument('--skip-tests', action='store_true', help='skip the Python/Node regression suites')
    parser.add_argument('--browser', help='path to Chrome/Chromium for the browser suites (needs NODE_PATH with puppeteer-core)')
    parser.add_argument('--database', help='permanent najdilab.db to COPY read-only for the migration test')
    parser.add_argument('--llama-server', help='existing llama-server binary for NajdiLab Native')
    parser.add_argument('--gguf', help='existing GGUF model file for NajdiLab Native')
    parser.add_argument('--gpu-layers', default='all', help='auto, all, 0 or a layer count (default all)')
    parser.add_argument('--ollama-model', help='installed Ollama model name, e.g. gemma4-local:e4b')
    parser.add_argument('--approve-model-load', action='store_true', help='required for --ollama-model: Ollama may load the model')
    parser.add_argument('--contexts', default='4096,8192,16384', help='comma-separated contexts to try once each')
    args = parser.parse_args()
    if args.database and ROOT in Path(args.database).resolve().parents:
        raise SystemExit('Refusing: run from an isolated checkout, not the folder that holds the permanent database.')
    contexts = [int(c) for c in args.contexts.split(',') if c.strip()]
    work = Path(tempfile.mkdtemp(prefix='najdilab-acceptance-'))
    report = Path(args.report).resolve()
    report.mkdir(parents=True, exist_ok=True)
    info = environment()
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    record('tested commit', 'PASS', head or 'unknown')
    if args.skip_tests:
        record('python and node regression suites', 'SKIPPED', '--skip-tests')
    else:
        env = {'NAJDILAB_NATIVE_TEST_SERVER': args.llama_server} if args.llama_server else {}
        run('pytest tests', [sys.executable, '-m', 'pytest', '-q', 'tests', '-rs'], env)
        run('pytest public_source builder', [sys.executable, '-m', 'pytest', '-q', 'public_source/tests/test_builder.py'])
        node = shutil.which('node')
        if node:
            run('node unit tests', [node, '--test', *sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').glob('*.test.cjs'))])
        else:
            record('node unit tests', 'BLOCKED', 'node not found')
        if args.browser:
            env = {'NAJDILAB_BROWSER_EXECUTABLE': args.browser, 'PYTHON': sys.executable}
            for script in ('chat-browser.cjs', 'chat-enhancements-browser.cjs'):
                run(f'chromium {script}', [node, f'tests/{script}'], env, 600)
            for script in ('review-restrictions-browser.cjs', 'i18n-browser.cjs', 'a11y-browser.cjs'):
                run(f'chromium {script}', [node, '--test', f'tests/{script}'], env, 900)
        else:
            record('browser suites (Arabic/English, keyboard, 320/390px)', 'NOT TESTED', 'pass --browser')
    if args.database:
        migration_copy(args.database, work)
    else:
        record('migration 008 on a copy of the real database', 'NOT TESTED', 'pass --database')
    if args.llama_server and args.gguf:
        native(args.llama_server, args.gguf, contexts, args.gpu_layers, work)
    else:
        record('NajdiLab Native with a real GGUF (CUDA/RTX)', 'NOT TESTED', 'pass --llama-server and --gguf')
    if args.ollama_model and args.approve_model_load:
        ollama(args.ollama_model, contexts, work)
    else:
        record('Ollama real model streaming', 'NOT TESTED', 'pass --ollama-model and --approve-model-load')
    record('LM Studio real model', 'NOT TESTED', 'manual: see docs/development/WINDOWS_ACCEPTANCE.md')
    (report / 'acceptance.json').write_text(json.dumps({'environment': info, 'results': RESULTS}, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['| Step | Status | Detail |', '|---|---|---|'] + [
        f"| {r['step']} | {r['status']} | {r['detail'].replace('|', '/')} |" for r in RESULTS]
    (report / 'acceptance.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    shutil.rmtree(work, ignore_errors=True)
    print(f'Report: {report}')
    raise SystemExit(1 if any(r['status'] == 'FAIL' for r in RESULTS) else 0)


if __name__ == '__main__':
    main()
