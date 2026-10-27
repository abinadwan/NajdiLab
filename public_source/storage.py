"""One candidate server per storage root; no stale PID-file recovery or probing."""
from contextlib import contextmanager
import os
from pathlib import Path
from .db import ROOT, DB_PATH

class StorageError(RuntimeError):
    pass


def validate_storage():
    for name in ('data','exports','datasets','backups'):
        p = ROOT / name
        if p.resolve() != p or p.is_symlink() or getattr(p, 'is_junction', lambda: False)():
            raise StorageError('Candidate storage must use regular checkout-local directories.')
    if DB_PATH.resolve() != DB_PATH or DB_PATH.is_symlink() or (DB_PATH.exists() and DB_PATH.stat().st_nlink > 1):
        raise StorageError('Linked database files are not supported.')


@contextmanager
def instance_guard():
    validate_storage()
    directory = ROOT / 'data'; directory.mkdir(exist_ok=True)
    p = directory / '.core-instance.lock'
    if p.resolve() != p or p.is_symlink() or (p.exists() and p.stat().st_nlink > 1):
        raise StorageError('Linked storage lock files are not supported.')
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(p, flags, 0o600)
    handle = os.fdopen(fd, 'r+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0:handle.write(b'0');handle.flush()
            handle.seek(0)
            try:msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:raise StorageError('Another core server uses this storage. Stop it first; another port does not isolate data.') from None
        else:
            import fcntl
            try:fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:raise StorageError('Another core server uses this storage. Stop it first; another port does not isolate data.') from None
        yield
    finally:
        handle.close()  # OS releases the advisory lock, including after process exit.
