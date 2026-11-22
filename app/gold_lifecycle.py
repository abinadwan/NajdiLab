"""Reentrant OS-backed ownership of Gold filesystem mutation critical sections."""
from __future__ import annotations

import os
import json
import stat
from functools import wraps
from pathlib import Path
from threading import RLock, local


def linked_path(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == 'nt' and path.exists():
        return bool(path.lstat().st_file_attributes & 0x400)
    return False


class _StorageLock:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._threads = RLock()
        self._local = local()

    def __enter__(self):
        self._threads.acquire()
        depth = getattr(self._local, 'depth', 0)
        if depth:
            self._local.depth = depth + 1
            return self
        descriptor = None
        try:
            if linked_path(self._root):
                raise OSError('The lifecycle root is linked.')
            self._root.mkdir(parents=True, exist_ok=True)
            path = self._root.resolve() / '.gold-lifecycle.lock'
            if linked_path(path):
                raise OSError('The lifecycle lock file is linked.')
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.set_inheritable(descriptor, False)
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or linked_path(path) or not os.path.samestat(opened, path.stat()):
                raise OSError('The lifecycle lock file is shared or unsafe.')
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            opened = os.fstat(descriptor)
            if linked_path(self._root) or linked_path(path) or opened.st_nlink != 1 or not os.path.samestat(opened, path.stat()):
                raise OSError('The lifecycle lock ownership changed while waiting.')
            self._local.descriptor = descriptor
            self._local.depth = 1
            return self
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            self._threads.release()
            from .dataset_platform import DatasetPlatformError
            raise DatasetPlatformError('GOLD_LIFECYCLE_LOCK_FAILED', 'The Gold storage lock is unavailable or unsafe. No operation was performed.') from exc

    def __exit__(self, *_):
        depth = self._local.depth
        try:
            if depth > 1:
                self._local.depth = depth - 1
                return
            descriptor = self._local.descriptor
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
                self._local.depth = 0
                del self._local.descriptor
        finally:
            self._threads.release()


_locks: dict[str, _StorageLock] = {}
_cache_lock = RLock()


def storage_lock(root: Path | str) -> _StorageLock:
    """Use the explicitly selected root, including isolated custom export roots."""
    key = os.path.normcase(os.path.abspath(root))
    with _cache_lock:
        if key not in _locks:
            _locks[key] = _StorageLock(Path(key))
        return _locks[key]


def deleted_identity_reserved(root: Path, version: str) -> bool:
    path = root / ('.gold-deleted-' + version)
    return path.exists() or linked_path(path)


def reserve_deleted_identity(root: Path, version: str) -> None:
    """Keep a durable flat reservation after the version's owned files are removed."""
    path = root / ('.gold-deleted-' + version)
    if linked_path(path):
        raise OSError('The deleted-version reservation is linked.')
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or linked_path(path)
                or not os.path.samestat(opened, path.stat())):
            raise OSError('The deleted-version reservation is shared or unsafe.')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _ConfiguredLock:
    def __init__(self) -> None:
        self._local = local()

    def __enter__(self):
        from .dataset_platform import EXPORTS_DIR
        selected = storage_lock(EXPORTS_DIR)
        selected.__enter__()
        if not hasattr(self._local, 'stack'):
            self._local.stack = []
        self._local.stack.append(selected)
        return selected

    def __exit__(self, *args):
        self._local.stack.pop().__exit__(*args)


lifecycle_lock = _ConfiguredLock()


def primary_exports_mutation(function):
    """Serialize public source-version mutations before they resolve or read files."""
    @wraps(function)
    def locked(*args, **kwargs):
        with lifecycle_lock:
            return function(*args, **kwargs)
    return locked


_REFERENCE_LEDGER = '.gold-handoff-references.jsonl'


def _reference_error():
    from .dataset_platform import DatasetPlatformError
    return DatasetPlatformError('GOLD_REFERENCE_LEDGER_FAILED', 'The handoff reference ledger is unavailable or malformed. Deletion is blocked.')


def handoff_references(root: Path) -> list[dict]:
    """Read the complete managed dependency ledger under the caller's storage lock."""
    path = root / _REFERENCE_LEDGER
    if not path.exists() and not linked_path(path):
        return []
    try:
        if linked_path(path) or not path.is_file() or path.stat().st_nlink != 1:
            raise _reference_error()
        lines = path.read_text(encoding='utf-8').splitlines()
        if not lines:
            raise _reference_error()
        records = []
        for line in lines:
            record = json.loads(line)
            if (not isinstance(record, dict) or record.get('policy') != 1
                    or not isinstance(record.get('source_version'), str) or not record['source_version']
                    or not isinstance(record.get('reference_id'), str) or len(record['reference_id']) != 32
                    or any(c not in '0123456789abcdef' for c in record['reference_id'])
                    or not isinstance(record.get('output_root'), str) or not Path(record['output_root']).is_absolute()
                    or not isinstance(record.get('created_at'), str) or not record['created_at']):
                raise _reference_error()
            records.append(record)
        return records
    except (OSError, ValueError, TypeError):
        raise _reference_error() from None


def record_handoff_reference(version: str, reference_id: str, output_root: Path) -> None:
    """Durably reserve a dependency before publishing any managed handoff, including custom roots."""
    from .dataset_platform import EXPORTS_DIR
    from .db import utc_now
    with lifecycle_lock:
        root = Path(EXPORTS_DIR).resolve()
        handoff_references(root)
        path = root / _REFERENCE_LEDGER
        descriptor = None
        try:
            if linked_path(path):
                raise _reference_error()
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.set_inheritable(descriptor, False)
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or linked_path(path)
                    or not os.path.samestat(opened, path.stat())):
                raise _reference_error()
            record = {'policy': 1, 'source_version': version, 'reference_id': reference_id,
                      'output_root': str(Path(output_root).resolve()), 'created_at': utc_now()}
            with os.fdopen(descriptor, 'a', encoding='utf-8') as handle:
                descriptor = None
                handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
                if linked_path(path) or not os.path.samestat(os.fstat(handle.fileno()), path.stat()) or path.stat().st_nlink != 1:
                    raise _reference_error()
        except OSError:
            raise _reference_error() from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
