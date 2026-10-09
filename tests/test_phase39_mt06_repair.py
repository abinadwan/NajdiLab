import json, unittest
from app.phase39_edits import PHASE39, V009

class Mt06RepairTests(unittest.TestCase):
    def test_mt06_targets_turn_four_only_and_queue_is_updated(self):
        row=next(json.loads(x) for x in (V009/'multi_turn.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(x).get('id')=='p38-mt-06')
        self.assertIn(row['messages'][1]['content'], {'تم، برد عليك بالعربي.','تم، برد عليك بالعربي.\n'})
        self.assertEqual(row['target_message_index'],3)
        expected='النسخة مجرد نسخة إضافية من ملف أو بيانات، أما النسخ الاحتياطي فهو نسخة مخصصة للاستعادة إذا فقدت الأصل أو تلف.'
        self.assertEqual(row['messages'][3]['content'],expected)
        audit=json.loads((PHASE39/'edit-audit.json').read_text(encoding='utf-8'))
        correction=[x for x in audit['corrections'] if x['record_id']=='p38-mt-06'][-1]
        self.assertEqual(correction['corrected_target_message_index'],3)
        queue=json.loads((PHASE39/'post-edit-verification.json').read_text(encoding='utf-8'))
        q=next(x for x in queue['records'] if x['record_id']=='p38-mt-06')
        self.assertEqual(q['target_message_index'],3); self.assertEqual(q['final_assistant_messages'],expected)

if __name__=='__main__': unittest.main()
