"""Product boundary checks; execution absence is checked structurally, not by a word ban."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOVED_MODULES = {
    'training_control', 'runtime_control', 'evaluation_guard', 'phase3_review',
    'phase35_analysis', 'phase36_readiness', 'phase37_hardening', 'generation_hardening',
    'train_najdi_sft', 'smoke_train_najdi_sft', 'najdilab_training_adapter',
    'run_gold_v004_controlled', 'run_gold_v006_controlled', 'run_gold_v007_balanced',
    'run_gold_v007_epoch2', 'phase3_benchmark', 'export_v007_e1_ollama',
}


def test_no_internal_training_modules_or_runtime_dependencies():
    for folder in ('app', 'scripts'):
        for path in (ROOT / folder).glob('*.py'):
            assert path.stem not in REMOVED_MODULES, path
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                             else [node.module or '', *[a.name for a in node.names]])
                    assert not any(set(n.split('.')) & REMOVED_MODULES for n in names), (path, names)
                    assert not any(n.split('.')[0] in {'torch', 'peft', 'unsloth', 'bitsandbytes', 'accelerate', 'trl'} for n in names), (path, names)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    assert node.name not in {'run_training', 'start_smoke', 'start_full_training', 'deploy_adapter', 'Trainer', 'MaskedSFTDataCollator', 'tool_benchmark_verdict'}, (path, node.name)


def test_only_dataset_and_chat_endpoints_are_registered():
    tree = ast.parse((ROOT / 'app/server.py').read_text(encoding='utf-8'))
    routes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, str) and n.value.startswith('/api/')]
    assert not any(p.startswith(('/api/v1/training', '/api/v1/phase3/', '/api/v1/evaluation/')) for p in routes)
    assert '/api/v1/dataset-records' in routes
    assert '/api/v1/unsloth-exports' in routes
    assert not any(isinstance(n, ast.FunctionDef) and n.name == '_training_retired' for n in ast.walk(tree))


def test_local_module_imports_resolve_without_removed_compatibility_modules():
    # Candidate imports resolve through the independently verified destination mapping.
    for folder in ('app', 'scripts', 'tests'):
        for path in (ROOT / folder).rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.level:
                    base = path.parent
                    for _ in range(node.level - 1):
                        base = base.parent
                    modules = [node.module] if node.module else [a.name for a in node.names]
                    for module in modules:
                        target = base.joinpath(*module.split('.'))
                        assert target.with_suffix('.py').is_file() or (target / '__init__.py').is_file(), (path, module)
                elif node.module in {'app', 'scripts'}:
                    for alias in node.names:
                        target = ROOT / node.module / alias.name
                        assert target.with_suffix('.py').is_file() or target.is_dir(), (path, alias.name)
                elif node.module and node.module.startswith(('app.', 'scripts.')):
                    target = ROOT.joinpath(*node.module.split('.'))
                    assert target.with_suffix('.py').is_file() or target.is_dir(), (path, node.module)


def test_applied_migrations_are_byte_preserved_and_replay_is_compatible(tmp_path):
    from app.db import apply_migrations, connect
    inventory = json.loads((ROOT / 'docs/cleanup-inventory.json').read_text(encoding='utf-8'))
    expected = {p: r['sha256'] for p, r in inventory['base_files'].items() if p.startswith('migrations/')}
    actual = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in (ROOT / 'migrations').glob('*.sql')}
    assert actual == expected
    db = tmp_path / 'synthetic.db'
    apply_migrations(db)
    with connect(db) as conn:
        conn.execute("INSERT INTO conversations(external_conversation_id,title,source,channel,created_at,updated_at) VALUES('synthetic','Synthetic','manual','manual','now','now')")
        before = [tuple(r) for r in conn.execute('SELECT * FROM conversations')]
    apply_migrations(db)
    with connect(db) as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM conversations')] == before
        assert conn.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == len(expected)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert {'training_eligible', 'exclude_from_training'} <= {r[1] for r in conn.execute('PRAGMA table_info(reviews)')}


def test_chat_security_implementation_and_export_contract_are_preserved():
    inventory = json.loads((ROOT / 'docs/cleanup-inventory.json').read_text(encoding='utf-8'))
    for name in ('app/chat_engine.py', 'app/chat_engine_worker.py', 'app/chat_workspace.py', 'app/integrations.py', 'app/unsloth_export.py'):
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == inventory['base_files'][name]['sha256'], name
