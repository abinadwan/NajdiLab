"""Dataset gates/inspection use exact synthetic source and unchanged split rules."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from tests.support import CandidateCase

class DatasetWorkflow(CandidateCase):
    def setUp(self):
        self.stop()
        for name in ['data','exports','datasets','backups']:
            p=self.work/name
            if p.exists():shutil.rmtree(p)
        self.start()

    def seed_valid(self,count=28):
        for n in range(count):
            r=self.new_review(user_message=f'وش عنوان بطاقة التجربة رقم {n}؟',assistant_response=f'بطاقة التجربة رقم {n} تنحط على الرف التجريبي رقم {n}.')
            self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/approve",{'expected_updated_at':r['updated_at'],'training_eligible':True})[0],200)

    def prepare(self):
        status,data=self.request('/api/v1/exports',{'include_demo':True});self.assertEqual(status,201,data);return data['export']['version']

    def test_empty_and_tiny_data_show_specific_readiness_blockers(self):
        self.assertFalse(self.request('/api/v1/exports/readiness')[1]['ok'])
        self.seed_valid(2);ready=self.request('/api/v1/exports/readiness?include_demo=1')[1]
        self.assertFalse(ready['ok']);self.assertIn('DATASET_SPLIT_GATE',[x['code'] for x in ready['blocking_findings']])
        self.assertEqual(self.request('/api/v1/exports',{'include_demo':True})[0],409)
        self.assertFalse(list((self.work/'exports').glob('gold-*')))

    def test_valid_version_readonly_detail_quality_and_holdout(self):
        self.seed_valid();before=self.rows('SELECT * FROM messages ORDER BY id')
        ready=self.request('/api/v1/exports/readiness?include_demo=1')[1];self.assertTrue(ready['ok'],ready)
        self.assertFalse(self.request('/api/v1/exports/readiness')[1]['ok'],'demo remains opt-in')
        version=self.prepare();directory=self.work/'exports'/version
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
        for suffix in ['', '/health','/quality-findings','/balance','/eval-sets','/release-validation']:
            code,detail=self.request('/api/v1/dataset-versions/'+version+suffix);self.assertEqual(code,200,detail)
            if suffix=='/eval-sets':self.assertTrue(detail['leakage_free']);self.assertGreaterEqual(detail['evaluation_conversations'],3)
        self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()},hashes)
        self.assertEqual(self.rows('SELECT * FROM messages ORDER BY id'),before)

    def test_duplicates_conflicts_and_source_staleness_are_visible(self):
        self.seed_valid();r=self.new_review(user_message='سؤال تجريبي متطابق؟',assistant_response='إجابة خيالية أولى.')
        self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/correct",{'expected_updated_at':r['updated_at'],'review_status':'FULL_CORRECTION','corrected_response':'تصحيح خيالي أول.','training_eligible':True})[0],200)
        other=self.new_review(user_message='سؤال تجريبي متطابق؟',assistant_response='إجابة خيالية ثانية.')
        self.assertEqual(self.request(f"/api/v1/reviews/{other['id']}/correct",{'expected_updated_at':other['updated_at'],'review_status':'FULL_CORRECTION','corrected_response':'تصحيح خيالي ثانٍ.','training_eligible':True})[0],200)
        ready=self.request('/api/v1/exports/readiness?include_demo=1')[1];self.assertFalse(ready['ok']);self.assertIn('CONTRADICTORY_TARGETS',[x['code'] for x in ready['blocking_findings']])
        c=sqlite3.connect(self.work/'data/najdilab.db');c.execute('UPDATE messages SET content=? WHERE id=?',('تغيير خيالي متعمد للمصدر.',r['message_id']));c.commit();c.close()
        self.assertIn('REVIEW_SOURCE_STALE',[x['code'] for x in self.request('/api/v1/exports/readiness?include_demo=1')[1]['blocking_findings']])
        self.assertEqual(self.request('/api/v1/exports',{'include_demo':True})[0],409)

    def test_excluded_and_evaluation_only_never_enter_training(self):
        self.seed_valid();r=self.new_review(user_message='سؤال تقييم خيالي مستقل.',assistant_response='جواب التقييم الخيالي مستقل.')
        self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/approve",{'expected_updated_at':r['updated_at'],'evaluation_only':True})[0],200)
        excluded=self.new_review();self.assertEqual(self.request(f"/api/v1/reviews/{excluded['id']}/exclude",{'expected_updated_at':excluded['updated_at'],'reason':'Fictional exclusion'})[0],200)
        version=self.prepare();manifest=json.loads((self.work/'exports'/version/'manifest.json').read_text())
        training=''.join((self.work/'exports'/version/name).read_text() for name in manifest['files'] if name!='evaluation_holdout.jsonl')
        self.assertNotIn(f'"id": "review:{r["id"]}"',training);self.assertNotIn(f'"id": "review:{excluded["id"]}"',training)
        self.assertIn(f'review:{r["id"]}',(self.work/'exports'/version/'evaluation_holdout.jsonl').read_text())

    def test_tampered_manifest_or_file_denies_diagnostics(self):
        self.seed_valid();version=self.prepare();manifest=self.work/'exports'/version/'manifest.json';raw=manifest.read_bytes();obj=json.loads(raw);obj['training_record_count']=999;manifest.write_text(json.dumps(obj))
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/health')[0],409)
        manifest.write_bytes(raw);(manifest.parent/'sft.jsonl').write_text('[]\n')
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/quality-findings')[0],409)
        for suffix in ['../data','%2e%2e','unknown-version']:
            self.assertIn(self.request('/api/v1/dataset-versions/'+suffix+'/health')[0],[400,403,404,409,422])

    def test_workshop_setup_requires_confirmation_and_never_approves(self):
        self.stop();shutil.rmtree(self.work/'data')
        env=self.env.copy()
        def run(*args):return subprocess.run([sys.executable,'scripts/synthetic_demo.py',*args],cwd=self.work,env=env,capture_output=True)
        self.assertNotEqual(run('--workshop').returncode,0);self.assertFalse((self.work/'data').exists())
        self.assertEqual(run('--confirm-disposable','--workshop').returncode,0)
        self.assertGreaterEqual(len(self.rows('SELECT * FROM reviews')),28);self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM reviews WHERE review_status!='PENDING'")[0]['n'],0)
        self.assertNotEqual(run('--confirm-disposable','--workshop').returncode,0);self.start()

    def test_restricted_prior_context_blocks_followup_export(self):
        self.seed_valid();r=self.new_review(name='fictional-context-chain',user_message='السؤال الخيالي الأول.',assistant_response='معلومة خيالية محمية في السياق.')
        self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/correct",{'expected_updated_at':r['updated_at'],'review_status':'FULL_CORRECTION','corrected_response':'تصحيح خيالي محمي.','contains_personal_data':True})[0],200)
        self.request('/api/v1/turn',{'conversation_id':'fictional-context-chain','source':'import','user_message':'وش الخطوة الثانية في التجربة؟','assistant_response':'هذه خطوة خيالية ثانية.','demo':True}, {'Authorization':'Bearer fictional-acceptance-only'})
        follow=self.rows('SELECT * FROM reviews ORDER BY id DESC LIMIT 1')[0]
        self.assertEqual(self.request(f"/api/v1/reviews/{follow['id']}/approve",{'expected_updated_at':follow['updated_at'],'training_eligible':True})[0],200)
        ready=self.request('/api/v1/exports/readiness?include_demo=1')[1]
        self.assertFalse(ready['ok']);self.assertIn('CONTEXT_REVIEW_REQUIRED',[x['code'] for x in ready['blocking_findings']]);self.assertEqual(self.request('/api/v1/exports',{'include_demo':True})[0],409)

    def test_manual_personal_flag_is_checked_even_without_manual_ui(self):
        from app import service
        self.seed_valid();service.add_direct_text({'text':'فقرة خيالية لفحص خصوصية المصدر اليدوي.','language_layer':'saudi_neutral','source_type':'synthetic_reviewed','source':'Fictional fixture','training_eligible':True,'contains_personal_data':True,'demo':True},db_path=self.work/'data/najdilab.db')
        ready=self.request('/api/v1/exports/readiness?include_demo=1')[1]
        self.assertFalse(ready['ok']);self.assertIn('PRIVACY_REVIEW_REQUIRED',[x['code'] for x in ready['blocking_findings']])

    def test_holdout_masks_and_balance_use_actual_export_format(self):
        self.seed_valid();version=self.prepare()
        code,balance=self.request(f'/api/v1/dataset-versions/{version}/balance');self.assertEqual(code,200);self.assertGreaterEqual(balance['record_counts']['evaluation'],3);self.assertEqual(balance['record_counts']['unknown'],0)
        directory=self.work/'exports'/version;file=directory/'evaluation_holdout.jsonl';rows=[json.loads(x) for x in file.read_text().splitlines()];rows[0]['message_loss_mask']=[0]*len(rows[0]['messages']);file.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
        # Deliberately register internally consistent bad synthetic content to test
        # structural validation separately from hash-tamper refusal.
        manifest=json.loads((directory/'manifest.json').read_text());manifest['sha256']['evaluation_holdout.jsonl']=hashlib.sha256(file.read_bytes()).hexdigest();(directory/'manifest.json').write_text(json.dumps(manifest))
        c=sqlite3.connect(self.work/'data/najdilab.db');c.execute('UPDATE dataset_versions SET manifest_json=? WHERE version=?',(json.dumps(manifest),version));c.commit();c.close()
        code,health=self.request(f'/api/v1/dataset-versions/{version}/health');self.assertEqual(code,200);self.assertEqual(health['status'],'BLOCKED')
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/quality-findings')[1]['status'],'BLOCKED')

    def test_linked_export_root_is_denied_before_writing(self):
        self.seed_valid();root=self.work/'exports';saved=self.work/'preserved-empty-exports';root.rename(saved);outside=self.work.parent/'fictional-outside';outside.mkdir()
        try:
            root.symlink_to(outside,target_is_directory=True)
            code,_=self.request('/api/v1/exports',{'include_demo':True});self.assertEqual(code,403);self.assertFalse(list(outside.iterdir()))
        finally:
            root.unlink();saved.rename(root)

    def test_demo_inclusion_requires_a_boolean(self):
        for value in ['false',1,None]:
            with self.subTest(value=value):self.assertEqual(self.request('/api/v1/exports',{'include_demo':value})[0],400)

    def test_duplicate_findings_available_without_silently_deleting_sources(self):
        self.seed_valid()
        for n in range(2):
            r=self.new_review(user_message=f'سؤال التكرار الخيالي رقم {n}؟',assistant_response='نفس الجواب الخيالي لاختبار التكرار فقط.')
            self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/approve",{'expected_updated_at':r['updated_at'],'training_eligible':True})[0],200)
        before=self.rows('SELECT * FROM messages ORDER BY id')
        code,data=self.request('/api/v1/exports/dedup-report?include_demo=1');self.assertEqual(code,200);self.assertTrue(data['exact_duplicate_groups'])
        self.assertEqual(self.rows('SELECT * FROM messages ORDER BY id'),before)

    def test_training_user_target_mask_cannot_be_ready(self):
        self.seed_valid();version=self.prepare();directory=self.work/'exports'/version;file=directory/'sft.jsonl';rows=[json.loads(x) for x in file.read_text().splitlines()];rows[0].update(target_message_index=0,message_loss_mask=[1,0],train_on_last_assistant_only=False);file.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
        manifest=json.loads((directory/'manifest.json').read_text());manifest['sha256']['sft.jsonl']=hashlib.sha256(file.read_bytes()).hexdigest();(directory/'manifest.json').write_text(json.dumps(manifest));c=sqlite3.connect(self.work/'data/najdilab.db');c.execute('UPDATE dataset_versions SET manifest_json=? WHERE version=?',(json.dumps(manifest),version));c.commit();c.close()
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/health')[1]['status'],'BLOCKED')

    def test_deferred_manual_kind_blocks_before_any_version_write(self):
        from app import service
        self.seed_valid();service.add_direct_text({'text':'نص يدوي خيالي لاختبار النطاق المؤجل.','language_layer':'saudi_neutral','source_type':'synthetic_reviewed','source':'Fictional fixture','training_eligible':True,'demo':True},db_path=self.work/'data/najdilab.db')
        ready=self.request('/api/v1/exports/readiness?include_demo=1')[1];self.assertFalse(ready['ok']);self.assertIn('UNSUPPORTED_RECORD_KIND',[x['code'] for x in ready['blocking_findings']]);self.assertEqual(self.request('/api/v1/exports',{'include_demo':True})[0],409);self.assertFalse(list((self.work/'exports').glob('gold-*')))

    def test_empty_holdout_never_reports_ready_even_with_matching_hashes(self):
        self.seed_valid();version=self.prepare();directory=self.work/'exports'/version;file=directory/'evaluation_holdout.jsonl';file.write_bytes(b'')
        manifest=json.loads((directory/'manifest.json').read_text());manifest['sha256']['evaluation_holdout.jsonl']=hashlib.sha256(b'').hexdigest();manifest['files']['evaluation_holdout.jsonl']=0;(directory/'manifest.json').write_text(json.dumps(manifest));c=sqlite3.connect(self.work/'data/najdilab.db');c.execute('UPDATE dataset_versions SET manifest_json=? WHERE version=?',(json.dumps(manifest),version));c.commit();c.close()
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/health')[1]['status'],'BLOCKED')
        self.assertEqual(self.request(f'/api/v1/dataset-versions/{version}/release-validation')[1]['status'],'BLOCKED')
