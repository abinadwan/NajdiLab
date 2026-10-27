"""Coherent private backup: SQLite snapshot plus only its registered versions."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import uuid
import zipfile

MAX_FILE=16*1024*1024
MAX_TOTAL=64*1024*1024
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.core_datasets import checked_version
from app.core_storage import validate_storage


def create_backup():
    validate_storage()
    database=ROOT/'data/najdilab.db'
    if not database.is_file():raise ValueError('Initialize local storage before backup')
    if database.stat().st_size>MAX_FILE:raise ValueError('Database exceeds bounded backup policy')
    backups=ROOT/'backups';backups.mkdir(mode=0o700,exist_ok=True)
    archive_name='najdilab-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]+'.zip'
    target=backups/archive_name
    with tempfile.TemporaryDirectory(prefix='.core-backup-',dir=backups) as temp:
        temp=Path(temp);snapshot=temp/'najdilab.db'
        source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True);dest=sqlite3.connect(snapshot)
        try:source.backup(dest)
        finally:dest.close();source.close()
        if snapshot.stat().st_size>MAX_FILE:raise ValueError('Database snapshot exceeds backup size policy')
        blobs={'data/najdilab.db':snapshot.read_bytes()}
        total=len(blobs['data/najdilab.db'])
        conn=sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        try:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Snapshot integrity')
            for row in conn.execute('SELECT version,manifest_json FROM dataset_versions ORDER BY version'):
                directory,manifest,files=checked_version(row['version'],registered_manifest=row['manifest_json'],exports_root=ROOT/'exports',byte_budget=MAX_TOTAL-total)
                total += sum(map(len,files.values()))
                blobs.update({f"exports/{row['version']}/{name}":data for name,data in files.items()})
        finally:conn.close()
        if any(len(data)>16*1024*1024 for data in blobs.values()) or sum(map(len,blobs.values()))>64*1024*1024:raise ValueError('Bounded backup size policy')
        staged=temp/'snapshot.zip'
        with zipfile.ZipFile(staged,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for member_name,data in sorted(blobs.items()):archive.writestr(member_name,data)
        # The unique destination is reserved before copying, never overwritten.
        incomplete=backups/(archive_name+'.incomplete')
        owned=False
        try:
            fd=os.open(incomplete,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            owned=True
            with os.fdopen(fd,'wb') as handle:handle.write(staged.read_bytes())
            os.link(incomplete,target)  # Atomic no-replace publication in this private directory.
        finally:
            if owned and incomplete.exists():incomplete.unlink()
    return target


def main():
    try:target=create_backup()
    except (ValueError,OSError,RuntimeError,sqlite3.Error):raise SystemExit('BACKUP_BLOCKED: local state is linked, changed, unavailable or outside the bounded backup policy.') from None
    print('PASS: coherent private backup created as '+target.name+'; only snapshot-registered versions included.')

if __name__=='__main__':main()
