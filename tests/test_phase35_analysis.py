from __future__ import annotations

import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from app import phase35_analysis as analysis


class Phase35AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.run=self.root/"phase3-train-20261006-001"; self.run.mkdir()
        records=[
            {"eval_id":"a","decision":"BASE_WIN","severity":"CRITICAL","critical_fail":True,"error_tags":["tool_behavior","hallucination"],"notes":"رفض قدرة متاحة وادعى تنفيذًا غير موثوق","category":"tool","evaluation_type":"tool","prompt":"SECRET PROMPT","gold_response":"SECRET GOLD","base_response":"SECRET BASE","adapter_response":"SECRET ADAPTER"},
            {"eval_id":"b","decision":"BASE_WIN","severity":"MAJOR","critical_fail":False,"error_tags":["context_failure","instruction_following"],"notes":"فقد السياق","category":"context_following","evaluation_type":"text"},
            {"eval_id":"c","decision":"BASE_WIN","severity":"NONE","critical_fail":False,"error_tags":[],"notes":"","category":None,"evaluation_type":"text"},
            {"eval_id":"d","decision":"ADAPTER_WIN","severity":"CRITICAL","critical_fail":True,"error_tags":["hallucination"],"notes":"Base failed","category":"text","evaluation_type":"text"},
        ]
        state={"production_job_id":"train-20261006-001","records":records,"summary":{"reviewed":4},"final_gate":{"final_decision":"REJECT"}}
        (self.run/"human-review.json").write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
        self.patcher=patch.object(analysis,"REPORTS_ROOT",self.root); self.patcher.start()
    def tearDown(self): self.patcher.stop(); self.temp.cleanup()
    def test_report_uses_only_base_wins_and_never_copies_holdout_content(self):
        report=analysis.build_failure_analysis("phase3-train-20261006-001"); encoded=json.dumps(report,ensure_ascii=False)
        self.assertEqual(report["summary"]["analyzed_regressions"],3); self.assertEqual(report["summary"]["major_or_critical_regressions"],2)
        self.assertEqual(report["summary"]["text_vs_tool_regressions"],{"tool":1,"text":2}); self.assertEqual(report["summary"]["failure_count_per_tag"]["hallucination"],1)
        self.assertNotIn("SECRET PROMPT",encoded); self.assertNotIn("SECRET GOLD",encoded); self.assertNotIn("SECRET BASE",encoded); self.assertNotIn("SECRET ADAPTER",encoded)
        self.assertEqual(next(x for x in report["base_win_cases"] if x["eval_id"]=="c")["likely_root_cause"],"insufficient_evidence")
    def test_severity_clusters_sizing_and_atomic_artifacts(self):
        source_before=(self.run/"human-review.json").read_bytes()
        json_path,md_path,report=analysis.write_failure_analysis("phase3-train-20261006-001")
        self.assertTrue(json_path.is_file()); self.assertTrue(md_path.is_file()); self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["phase4a"],"BLOCKED")
        tool=next(x for x in report["remediation_specification"]["clusters"] if x["cluster"]=="tool_behavior")
        self.assertEqual(tool["recommended_new_examples"],2); self.assertIn("No exact evaluation prompt",md_path.read_text(encoding="utf-8")); self.assertEqual((self.run/"human-review.json").read_bytes(),source_before)
    def test_requires_completed_reject(self):
        state=json.loads((self.run/"human-review.json").read_text(encoding="utf-8")); state["final_gate"]["final_decision"]=None; (self.run/"human-review.json").write_text(json.dumps(state),encoding="utf-8")
        with self.assertRaises(ValueError): analysis.build_failure_analysis("phase3-train-20261006-001")


if __name__=="__main__": unittest.main()
