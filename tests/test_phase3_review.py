from __future__ import annotations

import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from app import phase3_review as review
from app import training_control as training


class Phase3ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.reports=self.root/"reports"; self.exports=self.root/"exports"; self.jobs=self.root/"jobs"; self.run=self.reports/"phase3-train-20261006-001"; self.run.mkdir(parents=True)
        dataset=self.exports/"gold-v008-split-clean"; dataset.mkdir(parents=True)
        samples=[]; base=[]; adapter=[]
        for i in range(24):
            eval_id=f"case:{i}"; file="tool_eval.jsonl" if i>=21 else "text_sft_eval.jsonl"; row={"id":eval_id,"messages":[{"role":"user","content":f"prompt {i}"},{"role":"assistant","content":f"gold {i}"}],"target_message_index":1,"message_loss_mask":[0,1]}
            with (dataset/file).open("a",encoding="utf-8") as h: h.write(json.dumps(row)+"\n")
            base.append({"id":eval_id,"response":"base","gold":f"gold {i}"}); adapter.append({"id":eval_id,"response":"adapter","gold":f"gold {i}"}); samples.append({"id":eval_id,"evaluation_file":file,"category":"tool" if i>=21 else "text","gold":f"gold {i}","base_response":"base","adapter_response":"adapter","automatic":{"base_similarity":.1,"adapter_similarity":.2}})
        for name in ("vision_eval.jsonl","runtime_agent_eval.jsonl"): (dataset/name).write_text("",encoding="utf-8")
        (self.run/"comparison.json").write_text(json.dumps({"samples":samples}),encoding="utf-8"); (self.run/"base-benchmark.jsonl").write_text("\n".join(json.dumps(x) for x in base)+"\n",encoding="utf-8"); (self.run/"adapter-benchmark.jsonl").write_text("\n".join(json.dumps(x) for x in adapter)+"\n",encoding="utf-8"); (self.run/"adapter-benchmark.meta.json").write_text(json.dumps({"output_sha256":"out","adapter_config_sha256":"cfg","model_config_sha256":"model"}),encoding="utf-8")
        attempt=self.jobs/"train-20261006-001"/"attempts"/"attempt-002"; attempt.mkdir(parents=True); (attempt/"attempt.json").write_text(json.dumps({"result":{"adapter_result":{"adapter_path":"/adapter"}}}),encoding="utf-8")
        self.adapter_sha=patch.object(review,"_adapter_tree_sha",return_value="a"*64)
        self.patches=[patch.object(review,"REPORTS_ROOT",self.reports),patch.object(review,"EXPORTS_ROOT",self.exports),patch.object(training,"JOBS_ROOT",self.jobs),patch.object(training,"get_job",return_value={"dataset_fingerprint":"dataset"}),self.adapter_sha]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_load_save_resume_and_summary(self):
        originals={n:(self.run/n).read_bytes() for n in ("comparison.json","base-benchmark.jsonl","adapter-benchmark.jsonl")}; state=review.get_review("phase3-train-20261006-001"); self.assertEqual(len(state["records"]),24); self.assertEqual(state["summary"]["remaining"],24)
        state=review.save_case("phase3-train-20261006-001","case:21",{"decision":"BASE_WIN","severity":"MAJOR","critical_fail":True,"error_tags":["tool_behavior","tool_behavior"],"notes":"ملاحظة عربية\n\"سطر ثانٍ\"."})
        self.assertEqual(state["summary"]["critical_cases"],1); self.assertEqual(state["summary"]["adapter_critical_regressions"],1); self.assertEqual(state["summary"]["breakdown"]["tool"]["BASE_WIN"],1)
        record=review.get_review("phase3-train-20261006-001")["records"][21]; self.assertEqual(record["severity"],"CRITICAL"); self.assertEqual(record["error_tags"],["tool_behavior"]); self.assertIn("ملاحظة عربية",record["notes"]); self.assertEqual(state["summary"]["reviewed"],1); self.assertEqual(state["summary"]["remaining"],23)
        state=review.save_case("phase3-train-20261006-001","case:21",{"decision":"TIE","severity":"MINOR","critical_fail":False,"error_tags":[],"notes":"updated"}); self.assertEqual(state["summary"]["reviewed"],1); self.assertEqual(state["summary"]["ties"],1); self.assertEqual(state["summary"]["base_wins"],0)
        self.assertTrue(all((self.run/n).read_bytes()==value for n,value in originals.items()))
    def test_blind_mapping_is_stable_and_server_resolves_choices(self):
        state=review.get_review("phase3-train-20261006-001"); a=state["records"][0]; b=next(r for r in state["records"] if r["blind_mapping"]!=a["blind_mapping"])
        for record,expected in ((a,f"{a['blind_mapping']['B']}_WIN"),(b,f"{b['blind_mapping']['B']}_WIN")):
            state=review.save_case("phase3-train-20261006-001",record["eval_id"],{"blind_choice":"B","severity":"NONE","critical_fail":False,"error_tags":[],"dimension_scores":{},"notes":""}); self.assertEqual(next(r for r in state["records"] if r["eval_id"]==record["eval_id"])["decision"],expected)
        reloaded=review.get_review("phase3-train-20261006-001"); self.assertEqual(next(r for r in reloaded["records"] if r["eval_id"]==a["eval_id"])["blind_mapping"],a["blind_mapping"])
        state=review.save_case("phase3-train-20261006-001",a["eval_id"],{"blind_choice":"TIE","severity":"NONE","critical_fail":False,"error_tags":[],"dimension_scores":{},"notes":""}); self.assertEqual(state["records"][0]["decision"],"TIE")
    def test_validation_unknown_case_invalid_values_and_atomic_replace(self):
        review.get_review("phase3-train-20261006-001")
        with self.assertRaises(review.Phase3ReviewError) as missing: review.save_case("phase3-train-20261006-001","../missing",{})
        self.assertEqual(missing.exception.code,"REVIEW_CASE_NOT_FOUND")
        valid={"decision":"ADAPTER_WIN","severity":"NONE","critical_fail":False,"error_tags":[],"dimension_scores":{},"notes":""}
        for bad in ({**valid,"decision":"RESPONSE_A_WIN"},{**valid,"error_tags":["unknown"]},{**valid,"severity":"BAD"},{**valid,"critical_fail":"true"},{**valid,"dimension_scores":{"relevance":3}}):
            with self.assertRaises(review.Phase3ReviewError) as invalid: review.save_case("phase3-train-20261006-001","case:0",bad)
            self.assertEqual(invalid.exception.code,"INVALID_REVIEW_DECISION")
        with patch.object(review.os,"replace",wraps=review.os.replace) as replace: review.save_case("phase3-train-20261006-001","case:0",valid); self.assertTrue(replace.called)
    def test_summary_separates_adapter_regressions_from_base_and_tie_failures(self):
        records=[
            {"decision":"ADAPTER_WIN","severity":"CRITICAL","critical_fail":True,"error_tags":[],"evaluation_type":"text"},
            {"decision":"BASE_WIN","severity":"CRITICAL","critical_fail":False,"error_tags":[],"evaluation_type":"text"},
            {"decision":"ADAPTER_WIN","severity":"MAJOR","critical_fail":False,"error_tags":[],"evaluation_type":"text"},
            {"decision":"BASE_WIN","severity":"MAJOR","critical_fail":False,"error_tags":[],"evaluation_type":"text"},
            {"decision":"TIE","severity":"CRITICAL","critical_fail":True,"error_tags":[],"evaluation_type":"text"},
        ]
        summary=review._summary(records)
        self.assertEqual(summary["adapter_critical_regressions"],1)
        self.assertEqual(summary["adapter_major_regressions"],1)
        self.assertEqual(summary["base_critical_failures"],1)
        self.assertEqual(summary["base_major_failures"],1)
        self.assertEqual(summary["tie_critical_cases"],1)
        self.assertEqual(summary["critical_cases"],2)
        self.assertEqual(summary["regression_rate"],0.4)
    def test_incomplete_cannot_finalize(self):
        review.get_review("phase3-train-20261006-001")
        with self.assertRaises(review.Phase3ReviewError) as caught: review.submit_final_decision("phase3-train-20261006-001","APPROVE")
        self.assertEqual(caught.exception.code,"REVIEW_INCOMPLETE")
    def _complete(self):
        for i in range(24): review.save_case("phase3-train-20261006-001",f"case:{i}",{"decision":["ADAPTER_WIN","TIE","BASE_WIN"][i%3],"severity":"NONE","error_tags":[],"notes":""})
    def test_final_decisions_gate_phase4(self):
        for decision,phase4 in (("NEEDS_RETRAINING","BLOCKED"),("REJECT","BLOCKED"),("APPROVE","READY")):
            (self.run/"human-review.json").unlink(missing_ok=True); self._complete(); state=review.submit_final_decision("phase3-train-20261006-001",decision); self.assertEqual(state["final_gate"]["phase4a"],phase4)
    def test_stale_artifact_blocks_approval_and_originals_are_otherwise_unchanged(self):
        originals={n:(self.run/n).read_bytes() for n in ("comparison.json","base-benchmark.jsonl","adapter-benchmark.jsonl")}; self._complete(); (self.run/"comparison.json").write_text("{}",encoding="utf-8")
        with self.assertRaises(review.Phase3ReviewError) as caught: review.submit_final_decision("phase3-train-20261006-001","APPROVE")
        self.assertEqual(caught.exception.code,"STALE_PHASE3_ARTIFACT"); self.assertEqual((self.run/"base-benchmark.jsonl").read_bytes(),originals["base-benchmark.jsonl"]); self.assertEqual((self.run/"adapter-benchmark.jsonl").read_bytes(),originals["adapter-benchmark.jsonl"])
    def test_changed_adapter_artifact_blocks_approval(self):
        self._complete(); review._adapter_tree_sha.return_value="b"*64
        with self.assertRaises(review.Phase3ReviewError) as caught: review.submit_final_decision("phase3-train-20261006-001","APPROVE")
        self.assertEqual(caught.exception.code,"ADAPTER_FINGERPRINT_MISMATCH")


if __name__=="__main__": unittest.main()
