#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import backup_db  # noqa: E402


def create_backup(root: Path = ROOT) -> Path:
    backups = root / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = backups / f"najdilab-backup-{stamp}.zip"
    collision = 1
    while target.exists():
        target = backups / f"najdilab-backup-{stamp}-{collision:03d}.zip"
        collision += 1
    database = root / "data" / "najdilab.db"
    with tempfile.TemporaryDirectory(prefix="najdilab-backup-") as temp:
        snapshot = Path(temp) / "najdilab.db"
        if database.exists():
            backup_db(database, snapshot)
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            if snapshot.exists():
                archive.write(snapshot, "data/najdilab.db")
            exports = root / "exports"
            if exports.exists():
                for path in exports.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(root).as_posix())
    return target


if __name__ == "__main__":
    print(create_backup())

