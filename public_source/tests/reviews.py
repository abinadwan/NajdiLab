"""Regression: candidate writes must preserve privacy and serialize decisions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
from tests.support import CandidateCase

class ReviewWrites(CandidateCase):
    def correct(self,row,**fields):
        return self.request(f"/api/v1/reviews/{row['id']}/correct",{'review_status':'FULL_CORRECTION','corrected_response':'اكتب عنوان البطاقة بخط واضح.','expected_updated_at':row['updated_at'],**fields})

    def test_omitted_flags_notes_and_tags_survive_correction(self):
        r=self.new_review();c=sqlite3.connect(self.work/'data/najdilab.db')
        c.execute('UPDATE reviews SET contains_personal_data=1,contains_sensitive_data=1,evaluation_only=1,exclude_from_training=1,review_notes=?,needs_fact_check=1 WHERE id=?',('fictional restriction',r['id']))
        c.execute('INSERT INTO review_tags(review_id,tag) VALUES (?,?)',(r['id'],'dialect_issue'));c.commit();c.close()
        self.assertEqual(self.correct(r)[0],200);after=self.snapshot(r['id'])
        for f in ['contains_personal_data','contains_sensitive_data','evaluation_only','exclude_from_training','needs_fact_check']:self.assertEqual(after[f],1,f)
        self.assertEqual(after['review_notes'],'fictional restriction');self.assertEqual(after['training_eligible'],0)
        self.assertEqual(self.rows('SELECT tag FROM review_tags WHERE review_id=?',(r['id'],)),[{'tag':'dialect_issue'}])

    def test_token_required_and_stale_save_no_writes(self):
        r=self.new_review();before=self.snapshot(r['id'])
        status,data=self.request(f"/api/v1/reviews/{r['id']}/approve",{'training_eligible':True})
        self.assertEqual(status,428);self.assertEqual(self.snapshot(r['id']),before)
        self.assertEqual(self.correct(r)[0],200);saved=self.snapshot(r['id']);self.assertNotEqual(saved['updated_at'],r['updated_at'])
        status,data=self.correct(r,contains_personal_data=True,corrected_response='كتابة أخرى متعارضة.')
        self.assertEqual(status,409);self.assertEqual(data['code'],'REVIEW_CONFLICT');self.assertEqual(self.snapshot(r['id']),saved)

    def test_two_clients_same_token_only_one_wins(self):
        r=self.new_review()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda text:self.correct(r,corrected_response=text)[0],['خيار خيالي أول.','خيار خيالي ثانٍ.']))
        self.assertEqual(sorted(statuses),[200,409])

    def test_explicit_flags_and_repeated_saves_preserve_original(self):
        r=self.new_review();original_hash=hashlib.sha256(r['original_response'].encode()).hexdigest()
        self.assertEqual(self.correct(r,contains_personal_data=True,training_eligible=True)[0],200)
        r=self.snapshot(r['id']);self.assertEqual(r['training_eligible'],0)
        self.assertEqual(self.correct(r,contains_personal_data=False,training_eligible=True)[0],200)
        r=self.snapshot(r['id']);self.assertEqual(r['contains_personal_data'],0);self.assertEqual(r['training_eligible'],1)
        self.assertEqual(self.correct(r)[0],200);r=self.snapshot(r['id']);self.assertEqual(r['training_eligible'],1)
        self.assertEqual(hashlib.sha256(r['original_response'].encode()).hexdigest(),original_hash)
        self.stop();self.start();self.assertEqual(self.snapshot(r['id']),r)

    def test_bad_correction_and_flag_types_have_no_effect(self):
        for fields in [{'corrected_response':''},{'corrected_response':{}},{'contains_personal_data':'false'},{'training_eligible':None},{'corrected_response':['oops']}]:
            with self.subTest(fields=fields):
                r=self.new_review();self.assertEqual(self.correct(r,**fields)[0],400);self.assertEqual(self.snapshot(r['id']),r)

    def test_restore_preserves_restrictions_and_requires_rereview(self):
        r=self.new_review();self.assertEqual(self.correct(r,evaluation_only=True,contains_sensitive_data=True)[0],200)
        r=self.snapshot(r['id']);self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/exclude",{'expected_updated_at':r['updated_at'],'reason':'Fictional exclusion'})[0],200)
        r=self.snapshot(r['id']);self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/restore",{'expected_updated_at':r['updated_at'],'reason':'Inspect again'})[0],200)
        r=self.snapshot(r['id']);self.assertEqual(r['review_status'],'PENDING');self.assertEqual(r['training_eligible'],0);self.assertEqual(r['evaluation_only'],1);self.assertEqual(r['contains_sensitive_data'],1);self.assertTrue(r['corrected_response'])

    def test_no_action_can_discard_saved_correction_by_approving(self):
        r=self.new_review();self.assertEqual(self.correct(r)[0],200);r=self.snapshot(r['id'])
        for suffix in ['', '/approve', '/correct']:
            with self.subTest(suffix=suffix):
                code,_=self.request(f"/api/v1/reviews/{r['id']}{suffix}",{'expected_updated_at':r['updated_at'],'review_status':'APPROVED'})
                self.assertEqual(code,400);self.assertEqual(self.snapshot(r['id']),r)

    def test_all_mutation_routes_require_revision(self):
        r=self.new_review()
        for suffix in ['', '/approve','/correct','/exclude','/restore','/ignore','/delete']:
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}{suffix}",{'reason':'fictional'})[0],428)
                self.assertEqual(self.snapshot(r['id']),r)

    def test_fresh_lifecycle_actions_persist_reason_and_restore(self):
        for action in ['exclude','ignore','delete']:
            with self.subTest(action=action):
                r=self.new_review();status,data=self.request(f"/api/v1/reviews/{r['id']}/{action}",{'expected_updated_at':r['updated_at'],'reason':'Fictional action reason'})
                self.assertEqual(status,200);r=self.snapshot(r['id']);self.assertEqual(r['training_eligible'],0)
                self.assertTrue(r['deleted_at'] if action=='delete' else r['ignored_at']);self.assertEqual(r['ignored_reason'],'Fictional action reason')
                self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/restore",{'expected_updated_at':r['updated_at'],'reason':'Inspect again'})[0],200)
                restored=self.snapshot(r['id']);self.assertEqual(restored['review_status'],'PENDING');self.assertEqual(restored['training_eligible'],0)

    def test_reviewer_is_preserved_or_explicitly_changed(self):
        r=self.new_review();c=sqlite3.connect(self.work/'data/najdilab.db');c.execute("UPDATE reviews SET reviewer='import' WHERE id=?",(r['id'],));c.commit();c.close()
        self.assertEqual(self.correct(r)[0],200);r=self.snapshot(r['id']);self.assertEqual(r['reviewer'],'import')
        self.assertEqual(self.correct(r,reviewer_identity='human')[0],200);r=self.snapshot(r['id']);self.assertEqual(r['reviewer'],'human')
        self.assertEqual(self.correct(r,reviewer_identity='unknown')[0],400);self.assertEqual(self.snapshot(r['id']),r)

    def test_restored_overlay_requires_resolution_before_reexclude(self):
        r=self.new_review();self.assertEqual(self.correct(r)[0],200)
        for action in ['exclude','restore']:
            r=self.snapshot(r['id']);self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/{action}",{'expected_updated_at':r['updated_at'],'reason':'Fictional workflow'})[0],200)
        r=self.snapshot(r['id']);code,_=self.request(f"/api/v1/reviews/{r['id']}/exclude",{'expected_updated_at':r['updated_at'],'reason':'Repeat exclusion'})
        self.assertEqual(code,400);self.assertEqual(self.snapshot(r['id']),r)
        self.assertEqual(self.correct(r,exclude_from_training=True)[0],200)
        self.assertEqual(self.snapshot(r['id'])['training_eligible'],0)

    def test_native_hmac_ingestion_and_browser_csrf_are_independent(self):
        import hashlib,hmac,http.client,json
        raw=json.dumps({'conversation_id':'fictional-hmac','source':'import','user_message':'وين البطاقة الخيالية؟','assistant_response':'على الرف التجريبي.','demo':True,'metadata':{'synthetic':True}},ensure_ascii=False).encode()
        signature='sha256='+hmac.new(b'fictional-acceptance-only',raw,hashlib.sha256).hexdigest()
        def send(headers):
            c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
            try:
                c.request('POST','/api/v1/turn',raw,{'Content-Type':'application/json',**headers});r=c.getresponse();r.read();return r.status
            finally:c.close()
        before=self.rows('select count(*) n from conversations')[0]['n']
        self.assertEqual(send({'X-Hermes-Signature-256':signature+'bad'}),401)
        self.assertEqual(send({'X-Hermes-Signature-256':signature,'Authorization':'Bearer fictional-acceptance-only'}),401)
        self.assertEqual(send({'X-Hermes-Signature-256':signature,'Origin':self.base}),403)
        self.assertEqual(self.rows('select count(*) n from conversations')[0]['n'],before)
        self.assertEqual(send({'X-Hermes-Signature-256':signature}),201)

    def test_legacy_override_cannot_bypass_native_auth_or_write_rows(self):
        before={t:self.rows('select count(*) n from '+t)[0]['n'] for t in ('conversations','messages','reviews')}
        self.stop();self.env['NAJDILAB_ALLOW_LEGACY_INGEST']='1';self.start()
        try:
            payload={'conversation_id':'fictional-legacy-refusal','source':'import','user_message':'وين البطاقة الخيالية؟','assistant_response':'على الرف التجريبي.','demo':True}
            for path in ['/api/v1/turn','/api/v1/hermes-hook']:
                for headers in [{},{'Authorization':'Bearer fictional-acceptance-only'}]:
                    with self.subTest(path=path,credential=bool(headers)):
                        status,data=self.request(path,payload,headers)
                        self.assertEqual(status,409 if path.endswith('hermes-hook') else 503)
                        self.assertEqual(data['code'],'HERMES_UNSAFE_SOURCE' if path.endswith('hermes-hook') else 'LEGACY_INGEST_DISABLED')
            self.assertEqual({t:self.rows('select count(*) n from '+t)[0]['n'] for t in before},before)
        finally:
            self.stop();self.env.pop('NAJDILAB_ALLOW_LEGACY_INGEST',None);self.start()
