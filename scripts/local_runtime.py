"""Shared, side-effect-free checks for local setup and launch."""
import sys


def check_runtime():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ is required; choose a supported interpreter with NAJDILAB_PYTHON.')
    try:
        import sqlite3
        with sqlite3.connect(':memory:') as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('SQLite integrity check failed')
        if sqlite3.sqlite_version_info < (3, 24):
            raise RuntimeError('SQLite 3.24+ is required for registry UPSERT support')
    except (ImportError, RuntimeError) as exc:
        raise SystemExit('Python needs working SQLite support: ' + str(exc)) from exc
