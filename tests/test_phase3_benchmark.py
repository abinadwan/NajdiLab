import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from phase3_benchmark import comparison


class Phase3BenchmarkTests(unittest.TestCase):
    def test_comparison_never_auto_approves_phase4(self):
        base=[{"id":"x","evaluation_file":"text_sft_eval.jsonl","category":"text","gold":"أ","response":"ب"}]
        adapter=[{"id":"x","evaluation_file":"text_sft_eval.jsonl","category":"text","gold":"أ","response":"أ"}]
        result=comparison(base,adapter)
        self.assertEqual(result["automatic_summary"]["adapter_exact"],1)
        self.assertEqual(result["status"],"PENDING_HUMAN_APPROVAL")
        self.assertFalse(result["approval_gate"]["phase4a_allowed"])


if __name__=="__main__": unittest.main()
