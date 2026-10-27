from __future__ import annotations

import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from app import phase38_dataset as p38
from app.native_tool_data import validate_native_tool_record
from app.tool_runtime import load_registry
from scripts.train_najdi_sft import IGNORE_INDEX, encode_masked_native_tool_record

class CharTokenizer:
    chat_template="tools tool_calls"
    def apply_chat_template(self,messages,tools=None,tokenize=False,add_generation_prompt=False,**kwargs):
        out="[AVAILABLE_TOOLS]"+json.dumps(tools or [],ensure_ascii=False,sort_keys=True,separators=(",",":"))+"[/AVAILABLE_TOOLS]"
        for m in messages:
            if m["role"]=="user": out+="[INST]"+m["content"]+"[/INST]"
            elif m["role"]=="system": out+="[SYSTEM_PROMPT]"+m["content"]+"[/SYSTEM_PROMPT]"
            elif m["role"]=="assistant":
                out+=m.get("content") or ""
                for c in m.get("tool_calls") or []: out+="[TOOL_CALLS]"+c["function"]["name"]+"[ARGS]"+c["function"]["arguments"]
                out+="<eos>"
            elif m["role"]=="tool": out+="[TOOL_RESULTS]"+m["content"]+"[/TOOL_RESULTS]"
        return [ord(c) for c in out] if tokenize else out
    def __call__(self,text,**kwargs): return {"input_ids":[ord(c) for c in text],"offset_mapping":[(i,i+1) for i in range(len(text))]}
    def decode(self,ids,**kwargs): return "".join(chr(i) for i in ids)

from tests.private_artifacts import requires_private_artifacts

@requires_private_artifacts('datasets/eval/fresh-remediation-holdout-v001/manifest.json',
                            'datasets/gold-v009-remediation-draft/manifest.json',
                            'exports/gold-v008-split-clean/manifest.json')
class Phase38Tests(unittest.TestCase):
    def setUp(self):
        self.hmanifest=json.loads((p38.HOLDOUT/"manifest.json").read_text(encoding="utf-8")); self.vmanifest=json.loads((p38.V009/"manifest.json").read_text(encoding="utf-8")); self.registry=load_registry(p38.V009/"capability-registry.json")
    def test_fresh_holdout_is_independent_eval_only(self):
        self.assertEqual(self.hmanifest["state"],"FROZEN_EVAL_ONLY"); self.assertEqual(self.hmanifest["counts"],{"text":14,"native_tool":6,"general_sanity":4,"total":24,"training":0})
        quality=json.loads((p38.REPORTS/"fresh-holdout-quality.json").read_text(encoding="utf-8")); self.assertEqual(quality["status"],"PASS"); self.assertEqual(sum(quality["checks"][x] for x in ("exact_overlap","normalized_overlap","conversation_overlap","near_duplicate_prompt_overlap")),0)
    def test_holdout_cannot_become_training_data(self):
        holdout_ids={r["id"] for name in ("text_eval.jsonl","tool_eval.jsonl","general_sanity_eval.jsonl") for r in p38.read_jsonl(p38.HOLDOUT/name)}
        train_ids={r["id"] for name in ("sft.jsonl","multi_turn.jsonl","native_tool_use.jsonl") for r in p38.read_jsonl(p38.V009/name)}
        self.assertFalse(holdout_ids & train_ids); self.assertNotIn("fresh-remediation-holdout-v001",json.dumps(self.vmanifest))
    def test_v009_derived_without_v008_mutation_and_counts(self):
        self.assertEqual(self.vmanifest["state"],"Frozen"); self.assertEqual(self.vmanifest["provenance"]["parent_manifest_sha256"],p38.sha(p38.V008/"manifest.json")); self.assertEqual(self.vmanifest["new_remediation_counts"],{"sft":12,"multi_turn":16,"native_tool_use":8,"total":36})
        for name in ("direct_language.jsonl","preference_pairs.jsonl"): self.assertEqual(p38.sha(p38.V009/name),p38.sha(p38.V008/name))
    def test_coverage_targets_met(self):
        self.assertFalse({k for k,v in self.vmanifest["coverage_targets"].items() if self.vmanifest["coverage"][k]<v})
    def test_native_tool_validation_and_loss_masks(self):
        rows=p38.read_jsonl(p38.V009/"native_tool_use.jsonl"); self.assertEqual(len(rows),8)
        for row in rows:
            self.assertTrue(validate_native_tool_record(row,self.registry)["valid"]); encoded=encode_masked_native_tool_record(row,CharTokenizer(),self.registry); self.assertTrue(any(x!=IGNORE_INDEX for x in encoded["labels"])); self.assertTrue(encoded["tool_results_masked"]); self.assertIn("final_response",encoded["supervised_segments"])
        mask=json.loads((p38.V009/"native-tool-loss-mask-validation.json").read_text(encoding="utf-8")); self.assertEqual((mask["passed"],mask["total"]),(8,8))
    def test_contamination_gates_and_near_duplicate_queue(self):
        report=json.loads((p38.REPORTS/"v009-contamination.json").read_text(encoding="utf-8")); self.assertEqual(report["status"],"PASS"); self.assertEqual(report["phase3"]["exact"]+report["fresh_holdout"]["normalized"],0)
        candidate=[{"id":"c","messages":[{"role":"user","content":"هذه جملة طويلة مخصصة لاختبار التشابه القريب جدًا"}]}]; protected=[{"id":"p","messages":[{"role":"user","content":"هذه جملة طويلة مخصصة لاختبار التشابه القريب جدا"}]}]
        self.assertTrue(p38.scan(candidate,protected)["normalized"])
        near=p38.scan(candidate,[{"id":"p","messages":[{"role":"user","content":"هذه جملة طويلة مخصصة لاختبار التشابه القريب للغاية"}]}],.7); self.assertTrue(near["near_duplicate_queue"])
    def test_conversation_overlap_detection_basis(self):
        hold={r["conversation_id"] for n in ("text_eval.jsonl","tool_eval.jsonl","general_sanity_eval.jsonl") for r in p38.read_jsonl(p38.HOLDOUT/n)}; train={r["conversation_id"] for n in ("sft.jsonl","multi_turn.jsonl","native_tool_use.jsonl") for r in p38.read_jsonl(p38.V009/n) if r.get("conversation_id")}; self.assertFalse(hold&train)
    def test_review_freeze_gate_incomplete_rejected_and_contamination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); records=[{"record_id":str(i),"decision":None} for i in range(36)]; state={"summary":{"total":36,"reviewed":0,"rejected":0},"records":records}; p38.write_json(root/"v009-human-review.json",state); p38.write_json(root/"v009-contamination.json",{"status":"PASS"}); p38.write_json(root/"v009-dataset-health.json",{"status":"PASS_WITH_HUMAN_REVIEW_PENDING"})
            with patch.object(p38,"REPORTS",root):
                self.assertIn("HUMAN_REVIEW_INCOMPLETE",p38.freeze_gate()["blockers"])
                state["summary"]={"total":36,"reviewed":36,"rejected":1}; p38.write_json(root/"v009-human-review.json",state); self.assertIn("UNRESOLVED_REJECT",p38.freeze_gate()["blockers"])
                state["summary"]["rejected"]=0; p38.write_json(root/"v009-human-review.json",state); p38.write_json(root/"v009-contamination.json",{"status":"BLOCKED_MANUAL_REVIEW"}); self.assertIn("CONTAMINATION_BLOCKER",p38.freeze_gate()["blockers"])
    def test_inherited_and_phase3_fingerprints_valid(self):
        old=json.loads((p38.V008/"manifest.json").read_text(encoding="utf-8")); self.assertTrue(all(p38.sha(p38.V008/name)==digest for name,digest in old["sha256"].items()))
        hard=json.loads((p38.PHASE3/"tool-runtime-hardening.json").read_text(encoding="utf-8")); self.assertTrue(all(p38.sha(p38.PHASE3/name)==digest for name,digest in hard["immutable_evidence"]["phase3_artifacts"].items()))

if __name__=="__main__": unittest.main()
