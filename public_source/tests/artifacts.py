"""Downloads are explicit manifest-authorized data, never a general file server."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from urllib.request import urlopen
import zipfile
from tests.support import CandidateCase
from tests import test_candidate_datasets as dataset_fixtures

class ArtifactAccess(CandidateCase):
    seed_valid = dataset_fixtures.DatasetWorkflow.seed_valid
    prepare = dataset_fixtures.DatasetWorkflow.prepare
    def setUp(self):
        dataset_fixtures.DatasetWorkflow.setUp(self);self.seed_valid();self.version=self.prepare()

    def test_explicit_data_download_matches_hash_and_safe_headers(self):
        detail=self.request('/api/v1/dataset-versions/'+self.version)[1]
        for file in detail['files']:
            with self.subTest(name=file['name']),urlopen(self.base+f"/api/v1/dataset-versions/{self.version}/files/{file['name']}") as r:
                self.assertEqual(r.status,200);self.assertEqual(hashlib.sha256(r.read()).hexdigest(),file['sha256'])
                self.assertEqual(r.headers['Content-Type'],'application/octet-stream');self.assertIn('attachment;',r.headers['Content-Disposition']);self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')

    def test_archives_database_credentials_models_and_traversal_denied(self):
        for name in ['full_archive.json','dedup_report.json','manifest.json','.env','najdilab.db','weights.safetensors','../data/najdilab.db','%2e%2e%2fdata%2fnajdilab.db','%2Fetc%2Fpasswd','..%5Cdata%5Cnajdilab.db','missing.jsonl']:
            with self.subTest(name=name):self.assertIn(self.request(f'/api/v1/dataset-versions/{self.version}/files/{name}')[0],[400,403,404])
        self.assertEqual(self.request('/api/v1/dataset-versions/unknown/files/sft.jsonl')[0],404)

    def test_linked_file_and_version_cannot_escape(self):
        directory=self.work/'exports'/self.version;file=directory/'sft.jsonl';outside=self.work.parent/'fictional-outside.jsonl';outside.write_bytes(file.read_bytes());saved=self.work.parent/'preserved-sft.jsonl';file.rename(saved)
        try:
            file.symlink_to(outside);self.assertEqual(self.request(f'/api/v1/dataset-versions/{self.version}/files/sft.jsonl')[0],403)
        finally:file.unlink();saved.rename(file)
        outside_dir=self.work.parent/'preserved-version';directory.rename(outside_dir)
        try:
            directory.symlink_to(outside_dir,target_is_directory=True);self.assertEqual(self.request(f'/api/v1/dataset-versions/{self.version}/files/sft.jsonl')[0],403)
        finally:directory.unlink();outside_dir.rename(directory)

    def test_changed_bytes_never_download(self):
        file=self.work/'exports'/self.version/'sft.jsonl';file.write_text('fictional tampering')
        code,data=self.request(f'/api/v1/dataset-versions/{self.version}/files/sft.jsonl');self.assertEqual(code,409);self.assertEqual(data['code'],'DATASET_INTEGRITY_FAILED')

    def test_online_backup_and_separate_restore_preserve_current_decisions(self):
        r=self.rows('SELECT * FROM reviews ORDER BY id LIMIT 1')[0];self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/correct",{'expected_updated_at':r['updated_at'],'review_status':'FULL_CORRECTION','corrected_response':'تصحيح خيالي محفوظ في النسخة الاحتياطية.','contains_personal_data':True})[0],200)
        before_reviews=self.rows('SELECT * FROM reviews ORDER BY id');before_messages=self.rows('SELECT * FROM messages ORDER BY id')
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.work/'exports'/self.version).iterdir()}
        subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,check=True,capture_output=True)
        backup=next((self.work/'backups').glob('*.zip'));restore=self.work.parent/'restore'
        result=subprocess.run([sys.executable,'scripts/restore_backup.py',str(backup),'--output',str(restore),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode());c=sqlite3.connect(restore/'data/najdilab.db');c.row_factory=sqlite3.Row
        try:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall());self.assertEqual([dict(x) for x in c.execute('SELECT * FROM reviews ORDER BY id')],before_reviews);self.assertEqual([dict(x) for x in c.execute('SELECT * FROM messages ORDER BY id')],before_messages)
        finally:c.close()
        self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (restore/'exports'/self.version).iterdir()},hashes)
        self.assertNotEqual(subprocess.run([sys.executable,'scripts/restore_backup.py',str(backup),'--output',str(restore),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True).returncode,0)
        bad=self.work.parent/'bad.zip'
        with zipfile.ZipFile(backup) as source,zipfile.ZipFile(bad,'w') as z:
            for info in source.infolist():z.writestr(info,source.read(info))
            z.writestr('../escape.txt','fictional forbidden path')
        target=self.work.parent/'bad-restore';self.assertNotEqual(subprocess.run([sys.executable,'scripts/restore_backup.py',str(bad),'--output',str(target),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True).returncode,0);self.assertFalse(target.exists());self.assertFalse((self.work.parent/'escape.txt').exists())

    def test_backup_ignores_unregistered_staging_and_rejects_links(self):
        staging=self.work/'exports/.fictional-stage';staging.mkdir();(staging/'unregistered.jsonl').write_text('{}\n')
        result=subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,capture_output=True);self.assertEqual(result.returncode,0)
        archives=list((self.work/'backups').glob('*.zip'))
        with zipfile.ZipFile(archives[0]) as z:self.assertFalse(any('.fictional-stage' in x for x in z.namelist()))
        file=self.work/'exports'/self.version/'sft.jsonl';saved=self.work.parent/'saved-backup-source';file.rename(saved)
        try:
            file.symlink_to(saved);self.assertNotEqual(subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,capture_output=True).returncode,0)
            self.assertEqual(len(list((self.work/'backups').glob('*.zip'))),len(archives))
        finally:file.unlink();saved.rename(file)

    def test_restore_incomplete_registered_version_is_not_accepted(self):
        subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,check=True,capture_output=True);archive=next((self.work/'backups').glob('*.zip'))
        snapshot=self.work.parent/'incomplete.db'
        with zipfile.ZipFile(archive) as z:snapshot.write_bytes(z.read('data/najdilab.db'));manifest=json.loads(z.read(f'exports/{self.version}/manifest.json'))
        manifest['sha256']={};manifest['files']={};c=sqlite3.connect(snapshot);c.execute('UPDATE dataset_versions SET manifest_json=? WHERE version=?',(json.dumps(manifest),self.version));c.commit();c.close()
        bad=self.work.parent/'incomplete.zip'
        with zipfile.ZipFile(bad,'w') as z:z.write(snapshot,'data/najdilab.db');z.writestr(f'exports/{self.version}/manifest.json',json.dumps(manifest))
        output=self.work.parent/'incomplete-restore';result=subprocess.run([sys.executable,'scripts/restore_backup.py',str(bad),'--output',str(output),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertFalse(output.exists())

    def test_restore_refuses_existing_empty_destination(self):
        subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,check=True,capture_output=True);archive=next((self.work/'backups').glob('*.zip'));output=self.work.parent/'already-owned';output.mkdir()
        result=subprocess.run([sys.executable,'scripts/restore_backup.py',str(archive),'--output',str(output),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertTrue(output.is_dir());self.assertFalse(list(output.iterdir()))

    def test_backup_name_collision_preserves_unowned_incomplete_file(self):
        from scripts import backup
        from unittest.mock import patch
        from datetime import datetime,timezone
        from types import SimpleNamespace
        # Snapshot with no registered versions isolates publication ownership.
        c=sqlite3.connect(self.work/'data/najdilab.db');c.execute('DELETE FROM dataset_versions');c.commit();c.close()
        folder=self.work/'backups';folder.mkdir(exist_ok=True);name=folder/'najdilab-backup-20000101T000000-0123456789ab.zip.incomplete';name.write_bytes(b'pre-existing synthetic evidence')
        class Clock:
            @staticmethod
            def now(*args):return datetime(2000,1,1,tzinfo=timezone.utc)
        with patch.object(backup,'ROOT',self.work),patch.object(backup,'datetime',Clock),patch.object(backup.uuid,'uuid4',return_value=SimpleNamespace(hex='0123456789abcdef0123456789abcdef')):
            with self.assertRaises(FileExistsError):backup.create_backup()
        self.assertEqual(name.read_bytes(),b'pre-existing synthetic evidence')

    def test_backup_rejects_database_size_before_reading_it(self):
        from scripts import backup
        from unittest.mock import patch
        original=Path.read_bytes
        def guarded(path):
            if path.name=='najdilab.db':raise AssertionError('unbounded database read')
            return original(path)
        with patch.object(backup,'ROOT',self.work),patch.object(backup,'MAX_FILE',1,create=True),patch.object(Path,'read_bytes',guarded):
            with self.assertRaises(ValueError):backup.create_backup()

    def test_online_backup_is_restorable_during_preparation(self):
        from concurrent.futures import ThreadPoolExecutor
        def backup_now():return subprocess.run([sys.executable,'scripts/backup.py'],cwd=self.work,env=self.env,capture_output=True).returncode
        with ThreadPoolExecutor(max_workers=2) as pool:
            backup=pool.submit(backup_now);preparation=pool.submit(self.request,'/api/v1/exports',{'include_demo':True})
            self.assertEqual(backup.result(),0);self.assertEqual(preparation.result()[0],201)
        archive=next((self.work/'backups').glob('*.zip'));output=self.work.parent/'concurrent-restore';result=subprocess.run([sys.executable,'scripts/restore_backup.py',str(archive),'--output',str(output),'--confirm-disposable'],cwd=self.work,env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode());c=sqlite3.connect(output/'data/najdilab.db')
        try:self.assertGreaterEqual(c.execute('SELECT COUNT(*) FROM dataset_versions').fetchone()[0],1)
        finally:c.close()
