"""Keep browser fixtures off the default application database."""
from __future__ import annotations

from pathlib import Path

from app.db import DB_PATH as DEFAULT_DB


def refuse_default_database(connect):
    """Wrap a connect function so any route a fixture forgot to redirect fails loudly."""
    def guarded(db_path=DEFAULT_DB, *args, **kwargs):
        if Path(db_path).resolve() == Path(DEFAULT_DB).resolve():
            raise RuntimeError("browser fixture attempted to use the default application database")
        return connect(db_path, *args, **kwargs)
    return guarded
