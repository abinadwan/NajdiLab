"""Dataset gate regressions retained independently of removed runtime control."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import dataset_platform as platform
from app import dataset_validation as validation


def row(record_id: str, conversation: str, target: str) -> dict:
    return {"id": record_id, "conversation_id": conversation, "messages": [{"role": "user", "content": f"سؤال {record_id}"}, {"role": "assistant", "content": target}], "target_message_index": 1, "message_loss_mask": [0, 1]}


class DatasetGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.exports = self.root / "exports"; self.exports.mkdir(); self.version = self.exports / "gold-v008-split-clean"; self.version.mkdir()
        platform._write_jsonl(self.version / "sft.jsonl", [row("s1", "c1", "أبشر واحد"), row("s2", "c1", "أبشر اثنين")])
        platform._write_jsonl(self.version / "multi_turn.jsonl", [row("m1", "c2", "ثلاثة")])
        platform._write_jsonl(self.version / "text_sft_eval.jsonl", [row("e1", "e1", "تقييم")])
        manifest = {"version": "gold-v008-split-clean", "state": "Frozen", "files": {"sft.jsonl": 2, "multi_turn.jsonl": 1, "text_sft_eval.jsonl": 1}, "sha256": {name: platform._sha256(self.version / name) for name in ("sft.jsonl", "multi_turn.jsonl", "text_sft_eval.jsonl")}}
        platform._generate_training_diagnostics(self.version, manifest); platform._write_json(self.version / "manifest.json", manifest)
        self.export_patch = patch.object(platform, "EXPORTS_DIR", self.exports)
        self.export_patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.export_patch.stop)

    def test_frozen_healthy_dataset_passes_with_warnings(self):
        gate = validation.quality_gate("gold-v008-split-clean")
        self.assertEqual(gate["status"], "PASS_WITH_WARNINGS")
        self.assertEqual(gate["blocking_issues"], [])

    def test_draft_and_stale_diagnostics_block(self):
        manifest = platform._json(self.version / "manifest.json", {}); manifest["state"] = "Draft"; platform._write_json(self.version / "manifest.json", manifest)
        self.assertEqual(validation.quality_gate("gold-v008-split-clean")["status"], "BLOCKED")
        manifest["state"] = "Frozen"; manifest["diagnostics"]["training_fingerprint"] = "bad"; platform._write_json(self.version / "manifest.json", manifest)
        codes = {x["code"] for x in validation.quality_gate("gold-v008-split-clean")["blocking_issues"]}
        self.assertIn("STALE_DIAGNOSTICS", codes)

    def test_checksum_and_loss_count_mismatch_block(self):
        manifest = platform._json(self.version / "manifest.json", {}); manifest["sha256"]["sft.jsonl"] = "bad"; manifest["loss_mask_validation"]["total"] = 33; platform._write_json(self.version / "manifest.json", manifest)
        codes = {x["code"] for x in validation.quality_gate("gold-v008-split-clean")["blocking_issues"]}
        self.assertIn("STALE_CHECKSUM", codes); self.assertIn("LOSS_MASK_COUNT_MISMATCH", codes)

    def test_leakage_and_target_overlap_block(self):
        platform._write_jsonl(self.version / "text_sft_eval.jsonl", [row("e1", "c1", "أبشر واحد")])
        gate = validation.quality_gate("gold-v008-split-clean"); codes = {x["code"] for x in gate["blocking_issues"]}
        self.assertIn("CONVERSATION_LEAKAGE", codes); self.assertIn("EXACT_TARGET_OVERLAP", codes)

    def test_draft_freeze_readiness_passes_without_weakening_integrity_checks(self):
        manifest = platform._json(self.version / "manifest.json", {})
        manifest["state"] = "Draft"
        platform._write_json(self.version / "manifest.json", manifest)
        quality = validation.quality_gate("gold-v008-split-clean")
        self.assertEqual(quality["status"], "BLOCKED")
        self.assertEqual({item["code"] for item in quality["blocking_issues"]}, {"DATASET_NOT_FROZEN"})
        freeze = validation.freeze_readiness_gate("gold-v008-split-clean")
        self.assertEqual(freeze["status"], "PASS_WITH_WARNINGS")
        self.assertEqual(freeze["blocking_issues"], [])
        self.assertEqual(freeze["dataset_fingerprint"], quality["dataset_fingerprint"])
        self.assertEqual(freeze["dataset_counts"], quality["dataset_counts"])

        manifest["diagnostics"]["training_fingerprint"] = "stale"
        platform._write_json(self.version / "manifest.json", manifest)
        freeze = validation.freeze_readiness_gate("gold-v008-split-clean")
        self.assertEqual(freeze["status"], "BLOCKED")
        self.assertIn("STALE_DIAGNOSTICS", {item["code"] for item in freeze["blocking_issues"]})
        self.assertNotIn("DATASET_NOT_FROZEN", {item["code"] for item in freeze["blocking_issues"]})


if __name__ == "__main__":
    unittest.main()
