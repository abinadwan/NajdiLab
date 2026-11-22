"""Synthetic-only Gold ownership, deletion recovery and raw-download boundaries."""
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app import dataset_platform as platform
from app.db import apply_migrations
from app.service import add_manual_sft, create_export, list_exports


@pytest.fixture
def gold(tmp_path, monkeypatch):
    db = tmp_path / 'synthetic.db'
    apply_migrations(db)
    add_manual_sft({'messages': [{'role': 'user', 'content': 'synthetic question'},
                                 {'role': 'assistant', 'content': 'synthetic answer'}],
                    'language_layer': 'msa', 'origin': 'manual', 'training_eligible': True}, db)
    exports = tmp_path / 'exports'
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    from app import unsloth_export
    monkeypatch.setattr(unsloth_export, 'HANDOFFS', exports / 'unsloth-handoffs')
    result = create_export(db, exports)
    return db, exports, result


def management():
    assert importlib.util.find_spec('app.gold_management'), 'Gold lifecycle service must exist'
    from app import gold_management
    return gold_management


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir()}


def test_preview_is_read_only_and_delete_is_isolated_with_retained_history(gold):
    db, exports, result = gold
    module = management()
    version = result['version']
    directory = Path(result['path'])
    second = create_export(db, exports)
    before = snapshot(directory)
    other_before = snapshot(Path(second['path']))
    preview = module.deletion_preview(version, db_path=db)
    assert preview['allowed'] is True
    assert preview['blockers'] == []
    assert {item['name'] for item in preview['files']} == set(before)
    assert all(item['bytes'] == len(before[item['name']]) for item in preview['files'])
    assert snapshot(directory) == before
    assert module.deletion_preview(version, db_path=db)['token'] == preview['token']
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM gold_version_deletions').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM gold_deletion_audit').fetchone()[0] == 0
    deleted = module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    assert deleted == {'ok': True, 'version': version, 'deleted': True}
    assert not directory.exists()
    assert snapshot(Path(second['path'])) == other_before
    assert [row['version'] for row in list_exports(db)] == [second['version']]
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM dataset_versions').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM manual_data_export_history').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM manual_sft_items WHERE deleted_at IS NULL').fetchone()[0] == 1
        assert conn.execute('SELECT status FROM gold_version_deletions').fetchone()[0] == 'deleted'
        assert [r[0] for r in conn.execute('SELECT action FROM gold_deletion_audit ORDER BY id')] == ['started', 'completed']
    assert create_export(db, exports)['version'] == 'gold-v003'


def test_confirmation_and_stale_preview_never_remove_files(gold):
    db, _, result = gold
    module = management()
    version = result['version']
    directory = Path(result['path'])
    preview = module.deletion_preview(version, db_path=db)
    for payload in ({}, {'token': preview['token'], 'confirm_version': 'another'}):
        with pytest.raises(platform.DatasetPlatformError, match='confirmation'):
            module.delete_version(version, payload, db_path=db)
    (directory / 'unexpected.txt').write_text('unowned')
    with pytest.raises(platform.DatasetPlatformError):
        module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    assert (directory / 'unexpected.txt').read_text() == 'unowned'
    assert (directory / 'sft.jsonl').is_file()


@pytest.mark.parametrize('tamper', ['file', 'manifest', 'db_path', 'extra_file', 'missing_hash', 'hardlink', 'nested'])
def test_unprovable_ownership_refuses_deletion(gold, tmp_path, tamper):
    db, exports, result = gold
    module = management()
    directory = Path(result['path'])
    if tamper == 'file':
        (directory / 'sft.jsonl').write_text('changed')
    elif tamper == 'manifest':
        manifest = result['manifest'].copy()
        manifest['version'] = 'gold-v999'
        (directory / 'manifest.json').write_text(json.dumps(manifest))
    elif tamper == 'db_path':
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE dataset_versions SET export_path=?', (str(tmp_path),))
    elif tamper == 'extra_file':
        (directory / 'unexpected.txt').write_text('unowned')
    elif tamper == 'missing_hash':
        manifest = result['manifest'].copy()
        manifest['sha256'] = {'sft.jsonl': 'invalid'}
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE dataset_versions SET manifest_json=?', (json.dumps(manifest),))
    elif tamper == 'hardlink':
        os.link(directory / 'sft.jsonl', exports / 'shared.jsonl')
    else:
        (directory / 'nested').mkdir()
    before = snapshot(directory) if tamper != 'nested' else None
    preview = module.deletion_preview(result['version'], db_path=db)
    assert preview['allowed'] is False
    assert preview['blockers']
    assert preview['token'] is None
    with pytest.raises(platform.DatasetPlatformError):
        module.delete_version(result['version'], {'token': 'forged', 'confirm_version': result['version']}, db_path=db)
    assert directory.is_dir()
    if before is not None:
        assert snapshot(directory) == before


@pytest.mark.parametrize('reference', ['derived', 'handoff', 'shared_db'])
def test_dependencies_and_shared_database_references_block_delete(gold, reference):
    db, exports, result = gold
    module = management()
    version = result['version']
    if reference == 'derived':
        dependent = exports / 'derived-v1'
        dependent.mkdir()
        (dependent / 'manifest.json').write_text(json.dumps({'version': dependent.name, 'source_version': version}))
    elif reference == 'handoff':
        dependent = exports / 'unsloth-handoffs' / ('a' * 32)
        dependent.mkdir(parents=True)
        (dependent / 'manifest.json').write_text(json.dumps({'source_version': version}))
    else:
        with sqlite3.connect(db) as conn:
            conn.execute('INSERT INTO dataset_versions(version,created_at,record_count,manifest_json,export_path,filters_json) '
                         'SELECT ?,created_at,record_count,manifest_json,export_path,filters_json FROM dataset_versions', ('shared-v1',))
    assert module.deletion_preview(version, db_path=db)['allowed'] is False
    assert Path(result['path']).is_dir()


def test_deletion_preview_matches_an_aliased_handoff_catalog(gold, monkeypatch):
    from app import unsloth_export

    db, exports, source = gold
    unsloth_export.create_handoff(source['version'])
    other = create_export(db, exports)
    handoffs = unsloth_export.HANDOFFS
    monkeypatch.setattr(unsloth_export, 'HANDOFFS', Path(source['path']) / '..' / handoffs.name)

    preview = management().deletion_preview(other['version'], db_path=db)
    assert preview['allowed'] is True, preview['blockers']
    assert preview['files']
    source_preview = management().deletion_preview(source['version'], db_path=db)
    assert source_preview['allowed'] is False
    assert any('handoff reference' in message for message in source_preview['blockers'])


def test_partial_file_failure_is_audited_and_can_retry_safely(gold, monkeypatch):
    db, exports, result = gold
    module = management()
    version = result['version']
    preview = module.deletion_preview(version, db_path=db)
    original = Path.unlink
    failed = False
    def locked(path, *args, **kwargs):
        nonlocal failed
        if path.name == 'sft.jsonl' and not failed:
            failed = True
            raise PermissionError('synthetic locked file')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', locked)
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    assert exc.value.code == 'GOLD_DELETE_IO_ERROR'
    assert not Path(result['path']).exists()
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT status FROM gold_version_deletions').fetchone()[0] == 'deleting'
        assert conn.execute("SELECT COUNT(*) FROM gold_deletion_audit WHERE action='failed'").fetchone()[0] == 1
    retry = module.deletion_preview(version, db_path=db)
    assert retry['allowed']
    module.delete_version(version, {'token': retry['token'], 'confirm_version': version}, db_path=db)
    assert not list(exports.glob('.gold-delete-*'))


def test_raw_options_only_offer_frozen_attested_files_and_supported_profiles(gold):
    db, _, result = gold
    module = management()
    options = module.export_options(result['version'], db_path=db)
    assert options['version'] == result['version']
    names = {item['name'] for item in options['files']}
    assert {'sft.jsonl', 'manifest.json'} <= names
    assert 'full_archive.json' not in names
    assert {item['id'] for item in options['profiles']} == {'studio_chat', 'studio_alpaca', 'trl_prompt_completion'}
    assert all(item['compatible'] for item in options['profiles'])
    for item in options['files']:
        path = module.resolve_download(result['version'], item['name'], db_path=db)
        assert path.parent == Path(result['path'])
        assert item['url'].endswith('/files/' + item['name'])
    for name in ('full_archive.json', '../manifest.json', 'sft.jsonl/../../secret', 'unknown.jsonl'):
        with pytest.raises(platform.DatasetPlatformError):
            module.resolve_download(result['version'], name, db_path=db)


def test_raw_hash_tamper_is_rejected(gold):
    db, _, result = gold
    module = management()
    path = Path(result['path']) / 'sft.jsonl'
    path.write_bytes(b'tampered')
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(result['version'], path.name, db_path=db)


def test_raw_download_rejects_a_symlinked_version_directory(gold):
    db, exports, result = gold
    module = management()
    original = Path(result['path'])
    moved = exports.parent / 'outside-catalog'
    original.rename(moved)
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(original), str(moved)], check=True, capture_output=True)
    else:
        os.symlink(moved, original, target_is_directory=True)
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(result['version'], 'sft.jsonl', db_path=db)
    assert (moved / 'sft.jsonl').is_file()


def test_manifest_download_rejects_a_changed_registered_manifest(gold):
    db, _, result = gold
    module = management()
    path = Path(result['path']) / 'manifest.json'
    manifest = result['manifest'].copy()
    manifest['record_count'] = 10000
    path.write_text(json.dumps(manifest))
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(result['version'], 'manifest.json', db_path=db)


def test_stale_token_for_changed_but_re_attested_files_refuses_deletion(gold):
    db, _, result = gold
    module = management()
    version = result['version']
    token = module.deletion_preview(version, db_path=db)['token']
    directory = Path(result['path'])
    path = directory / 'sft.jsonl'
    path.write_bytes(path.read_bytes() + b'\n')
    manifest = result['manifest'].copy()
    manifest['sha256'] = {**manifest['sha256'], path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE dataset_versions SET manifest_json=?', (json.dumps(manifest),))
    assert module.deletion_preview(version, db_path=db)['allowed']
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.delete_version(version, {'token': token, 'confirm_version': version}, db_path=db)
    assert exc.value.code == 'STALE_DELETE_PREVIEW'
    assert directory.is_dir()


def test_raw_nonconversational_types_stay_separate_without_sft_profile(tmp_path, monkeypatch):
    from app.service import add_direct_text, add_preference_pair
    db = tmp_path / 'types.db'
    apply_migrations(db)
    add_direct_text({'text': 'independent synthetic language sample', 'source_type': 'human_written',
                     'language_layer': 'msa', 'origin': 'manual', 'training_eligible': True}, db)
    add_preference_pair({'prompt_context': 'synthetic choice', 'rejected_response': 'declined synthetic answer',
                         'preferred_response': 'preferred synthetic answer', 'origin': 'manual', 'training_eligible': True}, db)
    exports = tmp_path / 'exports'
    monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    result = create_export(db, exports)
    module = management()
    options = module.export_options(result['version'], db_path=db)
    counts = {item['name']: item['count'] for item in options['files']}
    assert counts['direct_language.jsonl'] == counts['preference_pairs.jsonl'] == 1
    assert 'sft.jsonl' not in counts
    assert all(not item['compatible'] and 'Direct Language, DPO, and Evaluation' in item['reason'] for item in options['profiles'])


def test_two_concurrent_deletes_never_affect_other_versions(gold):
    from concurrent.futures import ThreadPoolExecutor
    db, exports, result = gold
    module = management()
    second = create_export(db, exports)
    version = result['version']
    payload = {'token': module.deletion_preview(version, db_path=db)['token'], 'confirm_version': version}
    before = snapshot(Path(second['path']))
    def remove():
        try:
            return module.delete_version(version, payload, db_path=db)
        except platform.DatasetPlatformError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: remove(), range(2)))
    assert sum(isinstance(item, dict) and item['deleted'] for item in results) == 1
    assert 'GOLD_ALREADY_DELETED' in results
    assert snapshot(Path(second['path'])) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM gold_deletion_audit WHERE action='completed'").fetchone()[0] == 1


def test_unproven_legacy_catalog_and_bad_hash_download_fail_closed(gold):
    db, _, result = gold
    module = management()
    version = result['version']
    path = Path(result['path']) / 'manifest.json'
    manifest = result['manifest'].copy()
    manifest['sha256'] = {'sft.jsonl': 'not-a-sha256'}
    path.write_text(json.dumps(manifest))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE dataset_versions SET manifest_json=?', (json.dumps(manifest),))
    assert not module.deletion_preview(version, db_path=db)['allowed']
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(version, 'sft.jsonl', db_path=db)


def test_unknown_catalog_reference_manifest_fails_closed(gold):
    db, exports, result = gold
    module = management()
    (exports / 'unverified-legacy').mkdir()
    assert not module.deletion_preview(result['version'], db_path=db)['allowed']


def test_deleted_version_cannot_be_downloaded_if_a_directory_reappears(gold):
    db, _, result = gold
    module = management()
    directory = Path(result['path'])
    before = snapshot(directory)
    version = result['version']
    preview = module.deletion_preview(version, db_path=db)
    module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    directory.mkdir()
    for name, raw in before.items():
        (directory / name).write_bytes(raw)
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(version, 'sft.jsonl', db_path=db)


def test_linked_primary_root_blocks_raw_download(gold, monkeypatch):
    db, exports, result = gold
    module = management()
    alias = exports.parent / 'linked-exports'
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(exports)], check=True, capture_output=True)
    else:
        os.symlink(exports, alias, target_is_directory=True)
    monkeypatch.setattr(platform, 'EXPORTS_DIR', alias)
    with pytest.raises(platform.DatasetPlatformError):
        module.resolve_download(result['version'], 'sft.jsonl', db_path=db)


def test_profile_compatibility_reuses_actual_conversion_duplicate_rules(gold):
    db, _, result = gold
    module = management()
    directory = Path(result['path'])
    row = json.loads((directory / 'sft.jsonl').read_text())
    multi = {**row, 'id': 'synthetic:multi', 'messages': [
        {'role': 'user', 'content': 'A'}, {'role': 'assistant', 'content': 'B'},
        {'role': 'user', 'content': 'C'}, {'role': 'assistant', 'content': 'synthetic target'}],
        'target_message_index': 3, 'message_loss_mask': [0, 0, 0, 1]}
    single = {**row, 'id': 'synthetic:single', 'messages': [
        {'role': 'user', 'content': 'User: A\nAssistant: B\nUser: C'},
        {'role': 'assistant', 'content': 'synthetic target'}]}
    manifest = result['manifest'].copy()
    manifest['sha256'] = dict(manifest['sha256'])
    for filename, value in (('sft.jsonl', single), ('multi_turn.jsonl', multi)):
        path = directory / filename
        path.write_text(json.dumps(value) + '\n')
        manifest['sha256'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE dataset_versions SET manifest_json=?', (json.dumps(manifest),))
    profiles = {item['id']: item for item in module.export_options(result['version'], db_path=db)['profiles']}
    assert profiles['studio_chat']['compatible'] is False
    assert 'duplicate' in profiles['studio_chat']['reason'].lower()
    assert profiles['trl_prompt_completion']['compatible'] is True


def test_preview_token_is_scoped_to_the_database(gold, tmp_path):
    from app.db import backup_db
    db, _, result = gold
    module = management()
    version = result['version']
    token = module.deletion_preview(version, db_path=db)['token']
    clone = backup_db(db, tmp_path / 'another-synthetic.db')
    assert module.deletion_preview(version, db_path=clone)['allowed']
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.delete_version(version, {'token': token, 'confirm_version': version}, db_path=clone)
    assert exc.value.code == 'STALE_DELETE_PREVIEW'
    assert Path(result['path']).is_dir()


def test_new_handoff_after_preview_is_revalidated_before_deletion(gold):
    db, exports, result = gold
    module = management()
    version = result['version']
    preview = module.deletion_preview(version, db_path=db)
    handoff = exports / 'unsloth-handoffs' / ('b' * 32)
    handoff.mkdir(parents=True)
    (handoff / 'manifest.json').write_text(json.dumps({'source_version': version}))
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    assert exc.value.code == 'GOLD_DELETE_BLOCKED'
    assert Path(result['path']).is_dir()
    assert (handoff / 'manifest.json').is_file()


@pytest.mark.skipif(os.name != 'nt', reason='Windows denies deletion of an open file without delete-sharing')
def test_real_windows_file_lock_is_recoverable(gold):
    db, _, result = gold
    module = management()
    version = result['version']
    preview = module.deletion_preview(version, db_path=db)
    with (Path(result['path']) / 'sft.jsonl').open('rb'):
        with pytest.raises(platform.DatasetPlatformError) as exc:
            module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
        assert exc.value.code == 'GOLD_DELETE_IO_ERROR'
    retry = module.deletion_preview(version, db_path=db)
    assert retry['allowed']
    assert module.delete_version(version, {'token': retry['token'], 'confirm_version': version}, db_path=db)['deleted']


def test_manifest_only_legacy_version_has_no_proven_dataset_file_ownership(gold):
    db, exports, _ = gold
    module = management()
    directory = exports / 'gold-legacy-empty'
    directory.mkdir()
    manifest = {'version': directory.name, 'state': 'Frozen', 'sha256': {}}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(db) as conn:
        conn.execute('INSERT INTO dataset_versions(version,created_at,record_count,manifest_json,export_path,filters_json) '
                     "VALUES(?,'synthetic',0,?,?,'{}')", (directory.name, json.dumps(manifest), str(directory)))
    preview = module.deletion_preview(directory.name, db_path=db)
    assert preview['allowed'] is False
    assert preview['token'] is None
    assert (directory / 'manifest.json').is_file()


def test_separate_process_deletions_are_serialized_by_database(gold, tmp_path):
    db, exports, result = gold
    second = create_export(db, exports)
    before = snapshot(Path(second['path']))
    worker = '''
import json,sys,time
from pathlib import Path
from app import dataset_platform as p, unsloth_export as u, gold_management as g
db,root,version,ready,release=sys.argv[1:]
p.EXPORTS_DIR=Path(root)
u.HANDOFFS=Path(root)/'unsloth-handoffs'
preview=g.deletion_preview(version,db_path=db)
Path(ready).write_text('ready')
deadline=time.monotonic()+15
while not Path(release).exists() and time.monotonic()<deadline:
    time.sleep(.01)
try:
    value=g.delete_version(version,{'token':preview['token'],'confirm_version':version},db_path=db)
except g.DatasetPlatformError as exc:
    value={'code':exc.code}
print(json.dumps(value))
'''
    release = tmp_path / 'release'
    processes = []
    for i in range(2):
        ready = tmp_path / f'ready-{i}'
        processes.append(subprocess.Popen([sys.executable, '-c', worker, str(db), str(exports), result['version'], str(ready), str(release)],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    deadline = time.monotonic() + 15
    while len(list(tmp_path.glob('ready-*'))) != 2 and time.monotonic() < deadline:
        time.sleep(.01)
    release.write_text('start')
    outputs = [process.communicate(timeout=20) for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    values = [json.loads(stdout) for stdout, _ in outputs]
    assert sum(value.get('deleted') is True for value in values) == 1
    assert {value.get('code') for value in values} <= {None, 'GOLD_ALREADY_DELETED', 'STALE_DELETE_PREVIEW'}
    assert snapshot(Path(second['path'])) == before


def test_cross_process_publication_waits_for_reentrant_deletion_lock(gold, tmp_path):
    db, exports, result = gold
    module = management()
    ready = tmp_path / 'publisher-ready'
    published = tmp_path / 'publication'
    worker = '''
import json,sys
from pathlib import Path
from app import dataset_platform as p, gold_management as g
root,version,ready,published=sys.argv[1:]
p.EXPORTS_DIR=Path(root)
Path(ready).write_text('ready')
with g.lifecycle_lock:
    Path(published).write_text(json.dumps({'source_exists':(Path(root)/version).exists()}))
'''
    with module.lifecycle_lock:
        with module.lifecycle_lock:
            process = subprocess.Popen([sys.executable, '-c', worker, str(exports), result['version'], str(ready), str(published)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert ready.is_file()
            time.sleep(.15)
            assert not published.exists(), 'Another process must not enter the publication critical phase'
            preview = module.deletion_preview(result['version'], db_path=db)
            module.delete_version(result['version'], {'token': preview['token'], 'confirm_version': result['version']}, db_path=db)
            assert not published.exists()
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, (stdout, stderr)
    assert json.loads(published.read_text()) == {'source_exists': False}
    assert (exports / '.gold-lifecycle.lock').is_file(), 'The shared lock inode is never unlinked'


@pytest.mark.parametrize('kind', ['hardlink', 'directory'])
def test_unsafe_shared_lock_path_fails_closed(gold, kind, tmp_path, monkeypatch):
    db, exports, result = gold
    module = management()
    if kind == 'directory':
        exports = tmp_path / 'unsafe-lock-root'
        exports.mkdir()
        monkeypatch.setattr(platform, 'EXPORTS_DIR', exports)
    lock = exports / '.gold-lifecycle.lock'
    if kind == 'hardlink':
        lock.write_text('synthetic lock')
        os.link(lock, exports / 'another-link')
    else:
        lock.mkdir()
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.deletion_preview(result['version'], db_path=db)
    assert exc.value.code == 'GOLD_LIFECYCLE_LOCK_FAILED'
    assert Path(result['path']).is_dir()


@pytest.mark.parametrize('mutation', ['handoff', 'derive', 'export', 'freeze', 'regenerate', 'overlap'])
def test_public_mutation_waits_for_actual_cross_process_deletion(gold, tmp_path, mutation):
    db, exports, result = gold
    second = create_export(db, exports)
    other_before = snapshot(Path(second['path']))
    deleting = tmp_path / 'deleting'
    release = tmp_path / 'release-delete'
    mutation_ready = tmp_path / 'mutation-ready'
    outcome = tmp_path / 'mutation-outcome'
    deletion_worker = '''
import json,sys,time
from pathlib import Path
from app import dataset_platform as p, unsloth_export as u, gold_management as g
db,root,version,ready,release=sys.argv[1:]
p.EXPORTS_DIR=Path(root)
u.HANDOFFS=Path(root)/'unsloth-handoffs'
original=Path.unlink
def paused(path,*args,**kwargs):
    if path.name=='sft.jsonl':
        Path(ready).write_text('deleting')
        deadline=time.monotonic()+15
        while not Path(release).exists() and time.monotonic()<deadline:
            time.sleep(.01)
    return original(path,*args,**kwargs)
Path.unlink=paused
preview=g.deletion_preview(version,db_path=db)
print(json.dumps(g.delete_version(version,{'token':preview['token'],'confirm_version':version},db_path=db)))
'''
    mutation_worker = '''
import json,sys
from pathlib import Path
from app import dataset_platform as p, unsloth_export as u, service
db,root,version,action,ready,outcome=sys.argv[1:]
p.EXPORTS_DIR=Path(root)
u.HANDOFFS=Path(root)/'unsloth-handoffs'
Path(ready).write_text('ready')
try:
    if action=='handoff':
        u.create_handoff(version,output_root=Path(root)/'unsloth-handoffs')
    elif action=='derive':
        p.create_derived_version(version,'gold-derived')
    elif action=='freeze':
        p.freeze_dataset_version(version)
    elif action=='regenerate':
        p.regenerate_training_diagnostics(version)
    elif action=='overlap':
        p.apply_overlap_plan(version,'synthetic-plan','synthetic-fingerprint')
    else:
        service.create_export(db,Path(root))
    value={'ok':True}
except Exception as exc:
    value={'ok':False,'code':getattr(exc,'code',type(exc).__name__)}
Path(outcome).write_text(json.dumps(value))
'''
    deleting_process = subprocess.Popen([sys.executable, '-c', deletion_worker, str(db), str(exports), result['version'], str(deleting), str(release)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not deleting.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert deleting.is_file()
    mutation_process = subprocess.Popen([sys.executable, '-c', mutation_worker, str(db), str(exports), result['version'], mutation, str(mutation_ready), str(outcome)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not mutation_ready.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    time.sleep(.15)
    overlapped = outcome.exists()
    release.write_text('continue')
    delete_stdout, delete_stderr = deleting_process.communicate(timeout=20)
    mutation_stdout, mutation_stderr = mutation_process.communicate(timeout=20)
    assert deleting_process.returncode == 0, (delete_stdout, delete_stderr)
    assert mutation_process.returncode == 0, (mutation_stdout, mutation_stderr)
    assert not overlapped, 'Supported mutation must wait until actual deletion finishes'
    assert json.loads(delete_stdout)['deleted']
    value = json.loads(outcome.read_text())
    assert value == ({'ok': True} if mutation == 'export' else {'ok': False, 'code': 'DATASET_NOT_FOUND'})
    assert snapshot(Path(second['path'])) == other_before


def test_custom_export_root_does_not_lock_default_storage(gold, tmp_path, monkeypatch):
    import inspect
    from app import service
    db, exports, _ = gold
    default_root = tmp_path / 'unused-default-root'
    configured_root = tmp_path / 'unused-configured-root'
    monkeypatch.setattr(service, 'ROOT', default_root)
    monkeypatch.setattr(platform, 'EXPORTS_DIR', configured_root)
    result = service.create_export(db, exports_dir=exports)
    assert Path(result['path']).parent == exports
    assert not default_root.exists()
    assert not configured_root.exists()
    assert service.create_export.__module__ == 'app.service'
    assert inspect.signature(service.create_export) == inspect.signature(service.create_export.__wrapped__)
    assert 'db_path' in inspect.signature(service.create_export).parameters


def test_custom_handoff_output_locks_only_configured_source_storage(gold, tmp_path, monkeypatch):
    from app import unsloth_export
    db, exports, result = gold
    unused = tmp_path / 'unused-default-handoffs'
    target = tmp_path / 'custom-handoffs'
    monkeypatch.setattr(unsloth_export, 'HANDOFFS', unused)
    handoff = unsloth_export.create_handoff(result['version'], output_root=target)
    assert Path(handoff['directory']).parent == target
    assert (exports / '.gold-lifecycle.lock').is_file()
    assert not unused.exists()


def test_custom_handoff_publication_persists_a_dependency_outside_frozen_files(gold, tmp_path):
    from app import unsloth_export
    db, exports, result = gold
    module = management()
    before = snapshot(Path(result['path']))
    target = tmp_path / 'independent-handoffs'
    handoff = unsloth_export.create_handoff(result['version'], output_root=target)
    preview = module.deletion_preview(result['version'], db_path=db)
    assert preview['allowed'] is False
    assert any('handoff reference' in message.lower() for message in preview['blockers'])
    ledger = exports / '.gold-handoff-references.jsonl'
    reference = json.loads(ledger.read_text())
    assert reference['source_version'] == result['version']
    assert reference['reference_id'] == handoff['id']
    assert reference['output_root'] == str(target.resolve())
    assert snapshot(Path(result['path'])) == before
    assert Path(handoff['directory']).is_dir()


def test_reference_ledger_fsync_failure_prevents_handoff_publication(gold, tmp_path, monkeypatch):
    from app import unsloth_export
    db, exports, result = gold
    module = management()
    target = tmp_path / 'failed-handoffs'
    before = snapshot(Path(result['path']))
    def fail_fsync(_):
        raise OSError('synthetic ledger durability failure')
    monkeypatch.setattr(os, 'fsync', fail_fsync)
    with pytest.raises(platform.DatasetPlatformError) as exc:
        unsloth_export.create_handoff(result['version'], output_root=target)
    assert exc.value.code == 'GOLD_REFERENCE_LEDGER_FAILED'
    assert not list(target.glob('*/manifest.json'))
    assert snapshot(Path(result['path'])) == before
    assert not module.deletion_preview(result['version'], db_path=db)['allowed']


def test_factory_gold_without_reference_ownership_marker_cannot_be_deleted(gold):
    db, _, result = gold
    module = management()
    version = result['version']
    directory = Path(result['path'])
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest.pop('ownership', None)
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE dataset_versions SET manifest_json=?', (json.dumps(manifest),))
    preview = module.deletion_preview(version, db_path=db)
    assert preview['allowed'] is False
    assert any('managed handoff reference' in message.lower() for message in preview['blockers'])
    assert module.resolve_download(version, 'sft.jsonl', db_path=db).is_file()


def test_fresh_factory_gold_records_reference_ownership_policy_in_manifest_and_database(gold):
    db, _, result = gold
    module = management()
    assert result['manifest']['ownership'] == {'managed_reference_policy': 1}
    with sqlite3.connect(db) as conn:
        stored = json.loads(conn.execute('SELECT manifest_json FROM dataset_versions').fetchone()[0])
    assert stored['ownership'] == result['manifest']['ownership']
    assert module.deletion_preview(result['version'], db_path=db)['allowed']


@pytest.mark.parametrize('content', ['broken-json', '{}\n', '{"source_version":"some-other-version"}\n'])
def test_unreadable_reference_ledger_blocks_deletion(gold, content):
    db, exports, result = gold
    module = management()
    (exports / '.gold-handoff-references.jsonl').write_text(content)
    preview = module.deletion_preview(result['version'], db_path=db)
    assert preview['allowed'] is False
    assert any('reference ledger' in message.lower() for message in preview['blockers'])
    assert Path(result['path']).is_dir()


def test_lock_ownership_is_revalidated_after_waiting_for_os_lock(gold, monkeypatch):
    db, exports, result = gold
    module = management()
    if os.name == 'nt':
        import msvcrt
        original = msvcrt.locking
        def acquire(descriptor, mode, length):
            original(descriptor, mode, length)
            if mode == msvcrt.LK_LOCK:
                os.link(exports / '.gold-lifecycle.lock', exports / 'shared-while-waiting')
        monkeypatch.setattr(msvcrt, 'locking', acquire)
    else:
        import fcntl
        original = fcntl.flock
        def acquire(descriptor, mode):
            original(descriptor, mode)
            if mode == fcntl.LOCK_EX:
                os.link(exports / '.gold-lifecycle.lock', exports / 'shared-while-waiting')
        monkeypatch.setattr(fcntl, 'flock', acquire)
    with pytest.raises(platform.DatasetPlatformError) as exc:
        module.deletion_preview(result['version'], db_path=db)
    assert exc.value.code == 'GOLD_LIFECYCLE_LOCK_FAILED'
    assert Path(result['path']).is_dir()


def test_deleted_identity_cannot_be_reused_by_derivation_or_another_database(gold, tmp_path):
    db, exports, result = gold
    module = management()
    other = create_export(db, exports)
    preview = module.deletion_preview(result['version'], db_path=db)
    module.delete_version(result['version'], {'token': preview['token'], 'confirm_version': result['version']}, db_path=db)
    with pytest.raises(platform.DatasetPlatformError) as error:
        platform.create_derived_version(other['version'], result['version'])
    assert error.value.code == 'VERSION_ALREADY_EXISTS'
    second_db = tmp_path / 'another-synthetic.db'
    apply_migrations(second_db)
    add_manual_sft({'messages': [{'role': 'user', 'content': 'another question'},
                                 {'role': 'assistant', 'content': 'another answer'}],
                    'language_layer': 'msa', 'origin': 'manual', 'training_eligible': True}, second_db)
    with pytest.raises(ValueError, match='already exists'):
        create_export(second_db, exports)
    assert not Path(result['path']).exists()


@pytest.mark.parametrize('empty_remainder', [False, True])
def test_interrupted_deletion_remains_in_catalog_and_can_finish_after_reload(gold, monkeypatch, empty_remainder):
    db, _, result = gold
    module = management()
    version = result['version']
    preview = module.deletion_preview(version, db_path=db)
    original_unlink, original_rmdir = Path.unlink, Path.rmdir
    def stop_unlink(path, *args, **kwargs):
        if path.parent.name.startswith('.gold-delete-'):
            raise PermissionError('synthetic locked file')
        return original_unlink(path, *args, **kwargs)
    def stop_rmdir(path, *args, **kwargs):
        if path.name.startswith('.gold-delete-'):
            raise PermissionError('synthetic interrupted final cleanup')
        return original_rmdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'rmdir' if empty_remainder else 'unlink', stop_rmdir if empty_remainder else stop_unlink)
    with pytest.raises(platform.DatasetPlatformError) as error:
        module.delete_version(version, {'token': preview['token'], 'confirm_version': version}, db_path=db)
    assert error.value.code == 'GOLD_DELETE_IO_ERROR'
    monkeypatch.setattr(Path, 'unlink', original_unlink)
    monkeypatch.setattr(Path, 'rmdir', original_rmdir)
    catalog = module.version_catalog(db_path=db)
    pending = next(item for item in catalog if item['version'] == version)
    assert pending['deletion_pending'] is True and pending['readable'] is False
    refreshed = module.deletion_preview(version, db_path=db)
    assert refreshed['allowed'] is True and refreshed['recovery'] is True
    assert bool(refreshed['files']) is not empty_remainder
    module.delete_version(version, {'token': refreshed['token'], 'confirm_version': version}, db_path=db)
    assert all(item['version'] != version for item in module.version_catalog(db_path=db))
