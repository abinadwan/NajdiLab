"""Attested Gold downloads and recoverable, explicitly confirmed owned-file deletion.

Deletion retains the dataset row and source history. A committed tombstone records
the complete plan before filesystem changes. Files move together to a hidden sibling
directory, then only still-attested plan members are unlinked. A failure keeps the
remaining files and durable plan available for a newly confirmed retry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import dataset_platform as platform
from .db import DB_PATH, connect, json_dumps, transaction, utc_now
from .dataset_platform import DatasetPlatformError
from .gold_lifecycle import lifecycle_lock, linked_path as _linked, reserve_deleted_identity

_TOKEN_KEY = secrets.token_bytes(32)
_HASH = re.compile(r'^[0-9a-f]{64}$')
_DIAGNOSTICS = ('loss-mask-validation.json', 'balancing_report.json', 'dedup_report.json')
DOWNLOAD_FILES = frozenset(platform.KNOWN_FILES + (platform.NATIVE_TRAIN_FILE, 'manifest.json') + _DIAGNOSTICS)
_OWNED_FILES = DOWNLOAD_FILES | {'full_archive.json'}


def _error(code: str, message: str, version: str) -> DatasetPlatformError:
    return DatasetPlatformError(code, message, dataset=version)


def _safe_file(path: Path, directory: Path, version: str) -> None:
    if _linked(path) or path.resolve().parent != directory.resolve() or not path.is_file() or path.stat().st_nlink != 1:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'A file is missing, linked, shared, or outside its owned directory.', version)


def _read_manifest(directory: Path, version: str) -> dict[str, Any]:
    path = directory / 'manifest.json'
    _safe_file(path, directory, version)
    manifest = platform._json(path, {}, dataset=version, required=True)
    if manifest.get('version') != version or not isinstance(manifest.get('sha256'), dict):
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The manifest version or recorded hashes are invalid.', version)
    for name, digest in manifest['sha256'].items():
        if name not in _OWNED_FILES or name == 'manifest.json' or not isinstance(digest, str) or not _HASH.fullmatch(digest):
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The manifest contains an unsupported filename or malformed hash.', version)
    return manifest


def _recorded_files(directory: Path, manifest: dict[str, Any], version: str) -> list[dict[str, Any]]:
    hashes = manifest['sha256']
    names = set(hashes) | {'manifest.json'}
    if {item.name for item in directory.iterdir()} != names:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The directory does not match the complete recorded owned file set.', version)
    files = []
    for name in sorted(names):
        path = directory / name
        _safe_file(path, directory, version)
        digest = platform._sha256(path)
        if name != 'manifest.json' and digest != hashes[name]:
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'A file no longer matches its recorded SHA-256.', version)
        files.append({'name': name, 'bytes': path.stat().st_size, 'sha256': digest})
    return files


def _references(conn, version: str, directory: Path) -> None:
    """Refuse shared DB paths and uninspectable or dependent filesystem catalogs."""
    from . import unsloth_export
    from .gold_lifecycle import handoff_references
    for reference in handoff_references(Path(platform.EXPORTS_DIR).resolve()):
        if reference['source_version'] == version:
            raise _error('GOLD_DELETE_BLOCKED', 'A managed handoff reference depends on this version.', version)
    for row in conn.execute('SELECT version,export_path,manifest_json FROM dataset_versions WHERE version<>?', (version,)):
        try:
            other = json.loads(row['manifest_json'])
        except (ValueError, TypeError):
            raise _error('GOLD_DELETE_BLOCKED', 'Another recorded version has an unreadable manifest.', version) from None
        if not isinstance(other, dict):
            raise _error('GOLD_DELETE_BLOCKED', 'Another recorded version has an invalid manifest structure.', version)
        provenance = other.get('provenance')
        source = provenance.get('source_version') if isinstance(provenance, dict) else None
        if Path(row['export_path']).resolve() == directory or other.get('source_version') == version or source == version:
            raise _error('GOLD_DELETE_BLOCKED', 'Another version references this version or its directory.', version)
    handoffs = Path(unsloth_export.HANDOFFS)
    roots = tuple(dict.fromkeys(platform._registry_roots() + (handoffs,)))
    for root in roots:
        if _linked(root):
            raise _error('GOLD_DELETE_BLOCKED', 'A reference catalog is linked and cannot be proven safe.', version)
        if not root.exists():
            continue
        for folder in root.iterdir():
            if folder == directory or folder == handoffs or folder.name.startswith('.gold-delete-'):
                continue
            if _linked(folder):
                raise _error('GOLD_DELETE_BLOCKED', 'A reference catalog contains a linked entry.', version)
            if not folder.is_dir():
                continue
            manifest_path = folder / 'manifest.json'
            if not manifest_path.is_file() or _linked(manifest_path) or manifest_path.stat().st_nlink != 1:
                raise _error('GOLD_DELETE_BLOCKED', 'Another directory has no verifiable reference manifest.', version)
            other = platform._json(manifest_path, {}, dataset=version, required=True)
            provenance = other.get('provenance')
            source = provenance.get('source_version') if isinstance(provenance, dict) else None
            if other.get('source_version') == version or source == version:
                raise _error('GOLD_DELETE_BLOCKED', 'A derived version or Unsloth handoff references this version.', version)


def _owned_plan(conn, version: str) -> dict[str, Any]:
    if not isinstance(version, str) or not platform.SAFE_VERSION.fullmatch(version):
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'Invalid Gold version identifier.', str(version))
    row = conn.execute('SELECT * FROM dataset_versions WHERE version=?', (version,)).fetchone()
    if row is None:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'This version has no recorded export ownership.', version)
    root_path = Path(platform.EXPORTS_DIR)
    root = root_path.resolve()
    directory = root / version
    if _linked(root_path) or _linked(directory) or Path(row['export_path']).resolve() != directory:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The recorded export is not an owned primary-root directory.', version)
    tombstone = conn.execute('SELECT * FROM gold_version_deletions WHERE dataset_version_id=?', (row['id'],)).fetchone()
    if tombstone:
        if tombstone['status'] == 'deleted':
            raise _error('GOLD_ALREADY_DELETED', 'This Gold version has already been deleted.', version)
        plan = json.loads(tombstone['plan_json'])
        quarantine = Path(tombstone['quarantine_path'])
        if quarantine.parent != root or not re.fullmatch(r'\.gold-delete-[0-9a-f]{32}', quarantine.name) or _linked(quarantine):
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The recovery directory is unsafe.', version)
        if directory.exists() and quarantine.exists():
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'Both the original and recovery directory exist.', version)
        active = quarantine if quarantine.exists() else directory
        if not active.exists():
            # All files may have been removed before a process stopped before completion.
            plan['remaining'] = []
        else:
            if _linked(active) or not active.is_dir():
                raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The recovery directory is unavailable.', version)
            expected = {item['name']: item for item in plan['files']}
            remaining = []
            for path in sorted(active.iterdir()):
                _safe_file(path, active, version)
                item = expected.get(path.name)
                if item is None or path.stat().st_size != item['bytes'] or platform._sha256(path) != item['sha256']:
                    raise _error('GOLD_OWNERSHIP_UNPROVEN', 'A recovery file does not match the recorded deletion plan.', version)
                remaining.append(item)
            if active == directory and len(remaining) != len(expected):
                raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The original directory no longer has all owned files.', version)
            plan['remaining'] = remaining
        plan['quarantine'] = str(quarantine)
        _references(conn, version, directory)
        return plan
    if not directory.is_dir() or platform._version_dir(version) != directory:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The owned primary-root directory is unavailable or ambiguous.', version)
    manifest = _read_manifest(directory, version)
    try:
        recorded = json.loads(row['manifest_json'])
    except (ValueError, TypeError):
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The recorded export manifest is unreadable.', version) from None
    if recorded != manifest or platform._state(manifest, version) != 'Frozen':
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The frozen manifest differs from the recorded export manifest.', version)
    counts = manifest.get('files')
    dataset_names = set(platform.KNOWN_FILES + (platform.NATIVE_TRAIN_FILE,))
    if (not isinstance(counts, dict) or not counts or not set(counts) <= dataset_names
            or not set(counts) <= set(manifest['sha256'])
            or any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in counts.values())):
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'This legacy version has no complete recorded dataset file ownership.', version)
    if manifest.get('ownership') != {'managed_reference_policy': 1}:
        raise _error('GOLD_OWNERSHIP_UNPROVEN', 'This legacy version has no managed handoff reference ownership proof.', version)
    files = _recorded_files(directory, manifest, version)
    _references(conn, version, directory)
    return {'dataset_version_id': row['id'], 'version': version, 'directory': str(directory), 'files': files, 'remaining': files}


def _token(plan: dict[str, Any], db_path: Path | str) -> str:
    scope = {'db': str(Path(db_path).resolve()), 'root': str(Path(platform.EXPORTS_DIR).resolve()), 'plan': plan}
    return hmac.new(_TOKEN_KEY, json_dumps(scope).encode('utf-8'), hashlib.sha256).hexdigest()


def deletion_preview(version: str, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    with lifecycle_lock:
        conn = connect(db_path)
        try:
            with transaction(conn):
                plan = _owned_plan(conn, version)
                return {'version': version, 'allowed': True, 'blockers': [], 'files': plan['remaining'],
                        'recovery': 'quarantine' in plan, 'token': _token(plan, db_path)}
        except (DatasetPlatformError, OSError, ValueError) as exc:
            return {'version': version, 'allowed': False, 'blockers': [str(exc)], 'files': [], 'token': None}
        finally:
            conn.close()


def _audit(conn, plan: dict[str, Any], action: str, details: dict[str, Any]) -> None:
    conn.execute('INSERT INTO gold_deletion_audit(dataset_version_id,version,action,created_at,details_json) VALUES(?,?,?,?,?)',
                 (plan['dataset_version_id'], plan['version'], action, utc_now(), json_dumps(details)))


def delete_version(version: str, payload: dict[str, Any], *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get('confirm_version') != version or not isinstance(payload.get('token'), str) or not payload['token']:
        raise _error('DELETE_CONFIRMATION_REQUIRED', 'Explicit version confirmation and a current preview token are required.', version)
    with lifecycle_lock:
        conn = connect(db_path)
        plan = None
        try:
            with transaction(conn):
                plan = _owned_plan(conn, version)
                if not hmac.compare_digest(payload['token'], _token(plan, db_path)):
                    raise _error('STALE_DELETE_PREVIEW', 'The deletion preview is stale. Review the current files again.', version)
                if 'quarantine' not in plan:
                    plan['quarantine'] = str(Path(plan['directory']).parent / ('.gold-delete-' + uuid4().hex))
                    conn.execute('INSERT INTO gold_version_deletions(dataset_version_id,version,status,original_path,quarantine_path,plan_json,started_at) '
                                 "VALUES(?,?,'deleting',?,?,?,?)", (plan['dataset_version_id'], version, plan['directory'], plan['quarantine'], json_dumps(plan), utc_now()))
                    _audit(conn, plan, 'started', {'files': plan['files']})
            # A committed plan makes recovery possible after any following filesystem step.
            with transaction(conn):
                plan = _owned_plan(conn, version)
                directory, quarantine = Path(plan['directory']), Path(plan['quarantine'])
                reserve_deleted_identity(directory.parent, version)
                if directory.exists():
                    os.rename(directory, quarantine)
                if quarantine.exists():
                    for item in plan['remaining']:
                        path = quarantine / item['name']
                        _safe_file(path, quarantine, version)
                        if path.stat().st_size != item['bytes'] or platform._sha256(path) != item['sha256']:
                            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'A file changed during deletion.', version)
                        path.unlink()
                    quarantine.rmdir()
                conn.execute("UPDATE gold_version_deletions SET status='deleted',completed_at=? WHERE dataset_version_id=?", (utc_now(), plan['dataset_version_id']))
                _audit(conn, plan, 'completed', {'files': plan['files']})
            return {'ok': True, 'version': version, 'deleted': True}
        except (OSError, DatasetPlatformError) as exc:
            if plan and conn.execute('SELECT 1 FROM gold_version_deletions WHERE dataset_version_id=?', (plan['dataset_version_id'],)).fetchone():
                with transaction(conn):
                    _audit(conn, plan, 'failed', {'code': getattr(exc, 'code', 'GOLD_DELETE_IO_ERROR')})
            if isinstance(exc, DatasetPlatformError):
                raise
            raise _error('GOLD_DELETE_IO_ERROR', 'File deletion stopped safely. Close files in use and preview this version again to retry.', version) from exc
        finally:
            conn.close()


def version_catalog(*, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Retain UI access to interrupted deletions after quarantine hides the files."""
    with lifecycle_lock:
        versions = {item['version']: item for item in platform.list_dataset_versions()}
        if not Path(db_path).is_file():
            return list(versions.values())
        conn = connect(db_path)
        try:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gold_version_deletions'").fetchone():
                return list(versions.values())
            pending = conn.execute("SELECT version,started_at FROM gold_version_deletions WHERE status='deleting'")
            for row in pending:
                versions[row['version']] = {'version': row['version'], 'name': row['version'],
                    'created_at': row['started_at'], 'counts': {}, 'state': 'Deletion interrupted',
                    'readable': False, 'health_available': False, 'deletion_pending': True,
                    'error': 'Deletion stopped safely. Review the remaining files to retry.'}
        finally:
            conn.close()
        return sorted(versions.values(), key=lambda item: item['version'], reverse=True)


def resolve_download(version: str, filename: str, *, db_path: Path | str = DB_PATH) -> Path:
    """Return a literal allowlisted, manifest-attested file for local attachment delivery."""
    if filename not in DOWNLOAD_FILES:
        raise _error('GOLD_FILE_NOT_ALLOWED', 'This filename is not available for raw download.', version)
    with lifecycle_lock:
        if _linked(Path(platform.EXPORTS_DIR)):
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The primary exports root is linked.', version)
        for root in platform._registry_roots():
            if _linked(root) or _linked(root / version):
                raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The version root or directory is linked.', version)
        directory = platform._version_dir(version)
        if _linked(directory):
            raise _error('GOLD_OWNERSHIP_UNPROVEN', 'The version directory is linked.', version)
        manifest = _read_manifest(directory, version)
        # The manifest cannot hash itself. For registered exports, its immutable
        # database snapshot supplies the independent attestation.
        if Path(db_path).is_file():
            conn = sqlite3.connect(f'file:{Path(db_path).resolve().as_posix()}?mode=ro', uri=True)
            try:
                row = conn.execute('SELECT d.manifest_json,d.export_path,g.status FROM dataset_versions d '
                                   'LEFT JOIN gold_version_deletions g ON g.dataset_version_id=d.id WHERE d.version=?', (version,)).fetchone()
                if row and row[2] is not None:
                    raise _error('GOLD_ALREADY_DELETED', 'This Gold version is deleted or awaiting deletion recovery.', version)
                if row and (json.loads(row[0]) != manifest or Path(row[1]).resolve() != directory):
                    raise _error('GOLD_HASH_MISMATCH', 'The frozen manifest differs from its recorded export snapshot.', version)
            finally:
                conn.close()
        if platform._state(manifest, version) != 'Frozen':
            raise _error('GOLD_NOT_FROZEN', 'Raw export requires a frozen version.', version)
        path = directory / filename
        _safe_file(path, directory, version)
        if filename != 'manifest.json' and platform._sha256(path) != manifest['sha256'].get(filename):
            raise _error('GOLD_HASH_MISMATCH', 'The requested file no longer matches its frozen manifest hash.', version)
        return path


def _profile_reason(directory: Path, manifest: dict[str, Any]) -> str | None:
    from .service import TRAINING_REVIEW_STATUSES, ValidationError, _validate_sft_record
    from .dataset_quality import analyze_directory
    if manifest.get('privacy_policy') != 'no_flagged_or_excluded_context_v1':
        return 'This historical version has no verified context privacy policy. Create a fresh reviewed Gold version.'
    rows = []
    for name in platform.KNOWN_FILES + (platform.NATIVE_TRAIN_FILE,):
        path = directory / name
        if not path.exists():
            if name in manifest['sha256']:
                return 'A recorded dataset input is missing.'
            continue
        _safe_file(path, directory, manifest['version'])
        if path.stat().st_size > 128 * 1024 * 1024:
            return 'A dataset input exceeds the supported Unsloth handoff size limit.'
        if platform._sha256(path) != manifest['sha256'].get(name):
            return 'A dataset input no longer matches its frozen hash.'
        if name not in ('sft.jsonl', 'multi_turn.jsonl'):
            continue
        for row in platform._jsonl(path):
            try:
                _validate_sft_record(row, name)
            except ValidationError as exc:
                return str(exc)
            if (any(row.get(k) for k in ('evaluation_only', 'exclude_from_training', 'contains_personal_data', 'contains_sensitive_data', 'demo', 'deleted_at', 'ignored_at', 'archived'))
                    or row.get('training_eligible') in (False, 0) or ('review_status' in row and row['review_status'] not in TRAINING_REVIEW_STATUSES)
                    or not row.get('origin') or not row.get('id')):
                return 'A conversational row is not eligible for reviewed training export.'
            messages = row['messages']
            if any(set(m) != {'role', 'content'} or m['role'] not in {'user', 'assistant'} or not isinstance(m['content'], str) for m in messages):
                return 'Conversational profiles support plain user/assistant text only.'
            if [m['role'] for m in messages] != ['user' if i % 2 == 0 else 'assistant' for i in range(len(messages))]:
                return 'Conversational roles must alternate and end with the approved assistant target.'
            rows.append(row)
    if not rows:
        return 'No supported SFT or multi-turn targets are present. Direct Language, DPO, and Evaluation use their separate raw JSONL files.'
    seen = set()
    for row in rows:
        value = json_dumps(row['messages'])
        if value in seen:
            return 'Duplicate conversational targets must be reviewed before Unsloth export.'
        seen.add(value)
    if analyze_directory(directory, version=manifest['version'])['counts']['confirmed_blocker']:
        return 'Dataset quality or train/evaluation leakage checks have confirmed blockers.'
    return None


def export_options(version: str, *, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    from .unsloth_export import PROFILES, convert
    with lifecycle_lock:
        directory = platform._version_dir(version)
        manifest = _read_manifest(directory, version)
        files = []
        for name in sorted(DOWNLOAD_FILES):
            if not (directory / name).exists():
                continue
            path = resolve_download(version, name, db_path=db_path)
            count = len(platform._jsonl(path)) if name.endswith('.jsonl') else None
            if count == 0:
                continue
            files.append({'name': name, 'count': count, 'url': f'/api/v1/dataset-versions/{version}/files/{name}'})
        reason = _profile_reason(directory, manifest)
        rows = []
        if reason is None:
            for name in ('sft.jsonl', 'multi_turn.jsonl'):
                rows.extend(platform._jsonl(directory / name))
        profiles = []
        for profile, spec in PROFILES.items():
            profile_reason = reason
            if profile_reason is None:
                converted = [json_dumps(convert(row['messages'], profile)) for row in rows]
                if len(set(converted)) != len(converted):
                    profile_reason = 'This profile produces duplicate training examples. Review deduplication before export.'
            profiles.append({'id': profile, 'label': f"{spec['trainer']} ({spec['format']})",
                             'compatible': profile_reason is None, 'reason': profile_reason})
        return {'version': version, 'files': files, 'profiles': profiles}
