"""Validate a private local backup and restore only into a new separate directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.core_datasets import checked_version
ALLOWED = {'manifest.json','sft.jsonl','multi_turn.jsonl','direct_language.jsonl','preference_pairs.jsonl','evaluation_holdout.jsonl','full_archive.json','dedup_report.json','loss-mask-validation.json','balancing_report.json'}
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


def restore(backup, output):
    backup, output = Path(backup), Path(output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT):raise ValueError('Separate new output required')
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in output.parents):raise ValueError('Linked output parent')
    if backup.is_symlink() or not backup.is_file():raise ValueError('Regular backup file required')
    with zipfile.ZipFile(backup) as archive:
        infos = archive.infolist();names = [x.filename for x in infos]
        if len(infos)>10000 or len(set(names))!=len(names) or len({x.casefold() for x in names})!=len(names) or sum(x.file_size for x in infos)>MAX_TOTAL:raise ValueError('Backup size/name policy')
        for info in infos:
            p=PurePosixPath(info.filename);mode=stat.S_IFMT(info.external_attr>>16)
            if info.is_dir() or mode not in (0,stat.S_IFREG) or p.is_absolute() or '..' in p.parts or '\\' in info.filename or ':' in info.filename or info.file_size>MAX_FILE:raise ValueError('Unsafe backup entry')
            if info.filename=='data/najdilab.db':continue
            if len(p.parts)!=3 or p.parts[0]!='exports' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}',p.parts[1]) or p.parts[2] not in ALLOWED:raise ValueError('Unexpected backup entry')
        if 'data/najdilab.db' not in names:raise ValueError('Database snapshot missing')
        output.parent.mkdir(parents=True,exist_ok=True)
        # Normalize only our newly created staging directory (e.g. Windows
        # short-name aliases). Output-parent symlink/junction rejection above
        # remains unchanged; managed file checks still reject linked paths.
        stage=Path(tempfile.mkdtemp(prefix='.core-restore-',dir=output.parent)).resolve()
        try:
            for info in infos:
                data=archive.read(info)
                if len(data)!=info.file_size or len(data)>MAX_FILE:raise ValueError('Unexpected uncompressed size')
                target=stage/info.filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            conn=sqlite3.connect((stage/'data/najdilab.db').as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
            try:
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Database integrity failed')
                expected={'data/najdilab.db'}
                for row in conn.execute('SELECT version,manifest_json FROM dataset_versions'):
                    version=row['version']
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}',version):raise ValueError('Invalid version')
                    _,manifest,_=checked_version(version,registered_manifest=row['manifest_json'],exports_root=stage/'exports')
                    expected.add(f'exports/{version}/manifest.json')
                    expected.update(f'exports/{version}/{name}' for name in manifest['sha256'])
                if set(names)!=expected:raise ValueError('Missing or unregistered backup files')
                counts={table:conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('conversations','messages','reviews')}
            finally:conn.close()
            # Atomically claim a never-before-existing destination. Copy with
            # exclusive file creation; never rename over another directory.
            output.mkdir(mode=0o700,exist_ok=False)
            marker=output/'.RESTORE_INCOMPLETE'
            with marker.open('x',encoding='utf-8') as handle:handle.write('Private restore in progress; do not launch from this directory.\n')
            for source in sorted(stage.rglob('*')):
                target=output/source.relative_to(stage)
                if source.is_dir():target.mkdir(exist_ok=False)
                else:
                    with target.open('xb') as handle:handle.write(source.read_bytes())
            marker.unlink()
            return counts
        finally:
            if stage.exists():shutil.rmtree(stage)  # Only this newly created staging directory.


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('backup',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--confirm-disposable',action='store_true');args=parser.parse_args()
    if not args.confirm_disposable:raise SystemExit('Explicit --confirm-disposable required; no state changed.')
    try:counts=restore(args.backup,args.output)
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,NotImplementedError,sqlite3.Error,zipfile.BadZipFile):raise SystemExit('RESTORE_BLOCKED: backup or destination did not meet the local integrity policy.') from None
    print('PASS: restored separate private snapshot; integrity/FKs/manifest hashes checked; counts='+json.dumps(counts,sort_keys=True))

if __name__=='__main__':main()
