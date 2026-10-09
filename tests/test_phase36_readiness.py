from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import phase36_readiness as audit


class Phase36ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.reports = self.project / "reports"
        self.run = self.reports / "phase3-train-20261006-001"
        self.run.mkdir(parents=True)
        dataset = self.project / "exports" / "gold-v008-split-clean"
        attempt = self.project / "training" / "jobs" / "train-20261006-001" / "attempts" / "attempt-002"
        dataset.mkdir(parents=True); attempt.mkdir(parents=True)
        self._write(self.run / "human-review.json", {"summary": {"reviewed": 24}, "final_gate": {"final_decision": "REJECT"}})
        self._write(self.run / "failure-analysis.json", {"summary": {"failure_count_per_root_cause_cluster": {"tool_behavior": 1, "instruction_following": 2}, "severity_per_cluster": {"tool_behavior": {"CRITICAL": 1}, "instruction_following": {"MAJOR": 2}}}})
        self._write(dataset / "manifest.json", {"state": "Frozen", "version": "gold-v008-split-clean", "files": {"sft.jsonl": 12, "multi_turn.jsonl": 18, "direct_language.jsonl": 12, "preference_pairs.jsonl": 10, "text_sft_eval.jsonl": 21, "tool_eval.jsonl": 3}})
        self._write(attempt / "execution-manifest.json", {"dataset_fingerprint": "dataset-fp", "adapter_sha256": "adapter-sha", "staged_dataset": {"manifest": {"staged_files": ["sft.jsonl", "multi_turn.jsonl", "manifest.json", "loss-mask-validation.json"]}}})
        self._write(attempt / "result.json", {"adapter_result": {"training_records": 30}})
        for name in ("base-benchmark.meta.json", "adapter-benchmark.meta.json"):
            self._write(self.run / name, {"generation": {"do_sample": False, "max_new_tokens": 384}})
        self.root_patch = patch.object(audit, "PROJECT_ROOT", self.project); self.root_patch.start()
        self.report_patch = patch.object(audit, "REPORTS_ROOT", self.reports); self.report_patch.start()

    def tearDown(self):
        self.report_patch.stop(); self.root_patch.stop(); self.temp.cleanup()

    @staticmethod
    def _write(path: Path, value: dict):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_audit_distinguishes_assets_from_trained_records(self):
        report = audit.build_readiness("phase3-train-20261006-001")
        types = {x["record_type"]: x for x in report["production_pipeline"]["record_types"]}
        self.assertEqual(report["production_pipeline"]["trained_records"], {"SFT": 12, "Multi-turn": 18})
        self.assertTrue(types["SFT"]["gradient_updates"]); self.assertTrue(types["Multi-turn"]["gradient_updates"])
        self.assertFalse(types["Direct Language"]["consumed"]); self.assertFalse(types["Preference/DPO"]["gradient_updates"])
        self.assertFalse(report["production_pipeline"]["preference_optimization"]["dpo"])
        self.assertEqual(types["Native tool-use"]["future_remediation"], "BLOCKED_UNTIL_IMPLEMENTED")

    def test_unique_counts_are_coverage_counts_and_generation_is_fair(self):
        report = audit.build_readiness("phase3-train-20261006-001")
        self.assertEqual(report["unique_dataset_plan"]["minimum_defensible_unique_records"], 28)
        self.assertEqual(report["unique_dataset_plan"]["recommended_unique_records"], 36)
        self.assertTrue(report["generation_audit"]["identical_base_adapter"])
        tool = next(x for x in report["remediation_support_matrix"] if x["cluster"] == "tool_behavior")
        self.assertEqual(tool["currently_supported"], "BLOCKED")

    def test_writes_reports_without_mutating_sources(self):
        source = self.run / "human-review.json"; before = source.read_bytes()
        json_path, md_path, report = audit.write_readiness("phase3-train-20261006-001")
        self.assertTrue(json_path.is_file()); self.assertTrue(md_path.is_file())
        self.assertEqual(report["gates"]["phase4a"], "BLOCKED")
        self.assertIn("No retraining or dataset mutation occurred", md_path.read_text(encoding="utf-8"))
        self.assertEqual(source.read_bytes(), before)

    def test_requires_final_reject(self):
        self._write(self.run / "human-review.json", {"summary": {"reviewed": 24}, "final_gate": {"final_decision": "APPROVE"}})
        with self.assertRaises(ValueError): audit.build_readiness("phase3-train-20261006-001")


if __name__ == "__main__":
    unittest.main()
