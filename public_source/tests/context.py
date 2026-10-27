"""Context/readback and inspection filters must reflect actual saved decisions."""
from tests.support import CandidateCase

class ContextualReview(CandidateCase):
    def test_detail_exposes_context_original_and_persisted_flags(self):
        r=self.new_review();code,item=self.request(f"/api/v1/reviews/{r['id']}")
        self.assertEqual(code,200);self.assertEqual(item['original_response'],'اكتب عنوان تجريبي.');self.assertTrue(any(m['role']=='user' for m in item['context']))
        self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/correct",{'expected_updated_at':item['updated_at'],'review_status':'DIALECT_CORRECTION','corrected_response':'اكتب عنوان واضح.','contains_personal_data':True})[0],200)
        code,saved=self.request(f"/api/v1/reviews/{r['id']}");self.assertEqual(saved['corrected_response'],'اكتب عنوان واضح.');self.assertEqual(saved['contains_personal_data'],1)

    def test_filtered_review_listing_and_search(self):
        r=self.new_review(title='Distinct fictional shelf');self.assertEqual(self.request(f"/api/v1/reviews/{r['id']}/exclude",{'expected_updated_at':r['updated_at'],'reason':'Fictional exclusion'})[0],200)
        code,data=self.request('/api/v1/reviews?scope=excluded&search=Distinct');self.assertEqual(code,200);self.assertIn(r['id'],[x['id'] for x in data['items']])
        self.assertEqual(self.request('/api/v1/reviews?scope=unknown')[0],400)
        self.assertEqual(self.request('/api/v1/reviews/999999')[0],404)

    def test_context_inspection_does_not_change_database_records(self):
        r=self.new_review();before=self.rows('SELECT * FROM reviews ORDER BY id')
        for path in ['/api/v1/reviews',f"/api/v1/reviews/{r['id']}",f"/api/v1/conversations/{self.request('/api/v1/conversations')[1]['items'][0]['id']}"]:
            self.assertEqual(self.request(path)[0],200)
        self.assertEqual(self.rows('SELECT * FROM reviews ORDER BY id'),before)

    def test_missing_database_detail_does_not_create_state(self):
        import shutil
        data=self.work/'data';saved=self.work/'preserved-synthetic-data';data.rename(saved)
        try:
            self.assertEqual(self.request('/api/v1/reviews/1')[0],503)
            self.assertFalse(data.exists(),'GET must not initialize database storage')
        finally:
            if data.exists():shutil.rmtree(data)
            saved.rename(data)
