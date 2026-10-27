from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import patch

from app import dataset_platform as platform
from app import server as server_module


def row(record_id: str, conversation: str, target: str, turns: int = 1) -> dict:
    messages = []
    for index in range(turns):
        messages.extend([{"role": "user", "content": f"سؤال {index}"}, {"role": "assistant", "content": target if index == turns - 1 else f"رد {index}"}])
    target_index = len(messages) - 1
    return {"id": record_id, "conversation_id": conversation, "messages": messages, "target_message_index": target_index, "message_loss_mask": [0] * target_index + [1]}


from tests.private_artifacts import requires_private_artifacts

class DatasetPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.exports = Path(self.temp.name)
        self.version = self.exports / "gold-v007-balanced"
        self.version.mkdir()
        train = [row("s1", "c1", "هدف أول")]
        multi = [row(f"m{i}", "c2", f"هدف {i}", i + 1) for i in range(6)]
        evaluation = [row("e1", "eval-c1", "هدف تقييم")]
        for name, rows in (("sft.jsonl", train), ("multi_turn.jsonl", multi), ("text_sft_eval.jsonl", evaluation)):
            (self.version / name).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
        manifest = {"version": "gold-v007-balanced", "created_at": "2026-10-04T20:43:28Z", "source_version": "gold-v006-clean", "files": {"sft.jsonl": 1, "multi_turn.jsonl": 6, "text_sft_eval.jsonl": 1}, "loss_mask_validation": {"passed": 7, "total": 7, "failures": []}}
        (self.version / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.version / "balancing_report.json").write_text(json.dumps({"conversation_balance": {"conversation_count": 2, "highest_record_share": ["c2", {"record_share": .85}], "highest_context_word_share": ["c2", {"context_word_share": .8}], "highest_target_word_share": ["c2", {"target_word_share": .75}]}}), encoding="utf-8")
        self.patch = patch.object(platform, "EXPORTS_DIR", self.exports)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_health_reports_real_counts_and_warnings(self):
        health = platform.dataset_health("gold-v007-balanced")
        self.assertEqual(health["training_count"], 7)
        self.assertEqual(health["counts"]["multi_turn.jsonl"], 6)
        self.assertEqual(health["status"], "ready")
        self.assertEqual(health["training_readiness"]["status"], "READY")
        self.assertEqual(health["evaluation_integrity"]["status"], "CLEAN")
        self.assertIn("conversation_concentration", {x["code"] for x in health["warnings"]})

    def test_balancer_is_candidate_only_and_does_not_change_gold(self):
        before = (self.version / "multi_turn.jsonl").read_bytes()
        candidate = platform.balance_candidate("gold-v007-balanced")
        self.assertTrue(candidate["candidate_only"])
        self.assertTrue(candidate["source_unchanged"])
        self.assertLess(candidate["after"], candidate["before"])
        self.assertTrue(candidate["keep"])
        self.assertTrue(candidate["drop"])
        self.assertEqual(before, (self.version / "multi_turn.jsonl").read_bytes())

    def test_version_detail_has_manifest_hashes_provenance_and_frozen_state(self):
        detail = platform.dataset_version_detail("gold-v007-balanced")
        self.assertEqual(detail["state"], "Frozen")
        self.assertEqual(detail["provenance"], "gold-v006-clean")
        self.assertEqual(detail["manifest"]["files"]["sft.jsonl"], 1)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in detail["files"]))

    def test_eval_sets_are_locked_and_detect_leakage(self):
        clean = platform.eval_leakage("gold-v007-balanced")
        self.assertTrue(clean["locked"])
        self.assertTrue(clean["leakage_free"])
        leaked = row("e2", "c1", "هدف أول")
        with (self.version / "text_sft_eval.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(leaked, ensure_ascii=False) + "\n")
        result = platform.eval_leakage("gold-v007-balanced")
        self.assertFalse(result["leakage_free"])
        self.assertEqual(result["conversation_overlap_count"], 1)
        self.assertEqual(result["exact_target_overlap_count"], 1)
        health = platform.dataset_health("gold-v007-balanced")
        self.assertEqual(health["training_readiness"]["status"], "READY")
        self.assertEqual(health["evaluation_integrity"]["status"], "FAILED")
        self.assertEqual(health["evaluation_integrity"]["conversation_overlap_count"], 1)

    def test_v007_is_discoverable_in_version_list(self):
        versions = platform.list_dataset_versions()
        self.assertEqual(versions[0]["version"], "gold-v007-balanced")
        self.assertEqual(versions[0]["state"], "Frozen")

    def test_health_contract_has_timestamp_counts_and_separate_statuses(self):
        health = platform.dataset_health("gold-v007-balanced")
        self.assertIn("checked_at", health)
        self.assertEqual(health["counts"]["sft.jsonl"], 1)
        self.assertIn("training_readiness", health)
        self.assertIn("evaluation_integrity", health)

    def test_invalid_version_cannot_escape_exports(self):
        with self.assertRaises(platform.DatasetPlatformError):
            platform.dataset_health("../data")

    def test_missing_dataset_returns_controlled_error(self):
        with self.assertRaisesRegex(platform.DatasetPlatformError, "not found"):
            platform.dataset_health("gold-v999")

    def test_inventory_keeps_good_version_when_one_manifest_is_unreadable(self):
        broken = self.exports / "gold-v006-clean"
        broken.mkdir()
        (broken / "manifest.json").write_text("{not-json", encoding="utf-8")
        versions = platform.list_dataset_versions()
        by_name = {item["version"]: item for item in versions}
        self.assertTrue(by_name["gold-v007-balanced"]["readable"])
        self.assertFalse(by_name["gold-v006-clean"]["readable"])
        self.assertEqual(by_name["gold-v006-clean"]["error"]["code"], "INVALID_MANIFEST")

    def test_derived_clone_is_draft_independent_and_validated(self):
        before = {p.name: platform._sha256(p) for p in self.version.iterdir() if p.is_file()}
        detail = platform.create_derived_version("gold-v007-balanced", "gold-v008-split-clean")
        self.assertEqual(detail["state"], "Draft")
        self.assertEqual(detail["manifest"]["source_version"], "gold-v007-balanced")
        self.assertEqual(detail["manifest"]["provenance"]["kind"], "derived")
        self.assertEqual(before, {p.name: platform._sha256(p) for p in self.version.iterdir() if p.is_file()})
        with self.assertRaises(platform.DatasetPlatformError) as duplicate:
            platform.create_derived_version("gold-v007-balanced", "gold-v008-split-clean")
        self.assertEqual(duplicate.exception.code, "VERSION_ALREADY_EXISTS")
        with self.assertRaises(platform.DatasetPlatformError) as invalid:
            platform.create_derived_version("gold-v007-balanced", "../escape")
        self.assertEqual(invalid.exception.code, "INVALID_VERSION_NAME")
        with self.assertRaises(platform.DatasetPlatformError) as missing:
            platform.create_derived_version("gold-v999", "gold-v009")
        self.assertEqual(missing.exception.code, "DATASET_NOT_FOUND")

    def test_overlap_dry_run_apply_manifest_and_stale_guard(self):
        overlap = row("e2", "c2", "هدف تقييم مستقل", 2)
        eval_path = self.version / "text_sft_eval.jsonl"
        eval_path.write_text(eval_path.read_text(encoding="utf-8") + json.dumps(overlap, ensure_ascii=False) + "\n", encoding="utf-8")
        source_before = {p.name: platform._sha256(p) for p in self.version.iterdir() if p.is_file()}
        platform.create_derived_version("gold-v007-balanced", "gold-v008-split-clean")
        derived = self.exports / "gold-v008-split-clean"
        plan = platform.create_overlap_plan("gold-v008-split-clean")
        dry_before = {p.name: platform._sha256(p) for p in derived.iterdir() if p.is_file()}
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["summary"]["overlap_conversations"], 1)
        self.assertEqual(plan["items"][0]["proposed_destination"], "Training")
        self.assertEqual(dry_before, {p.name: platform._sha256(p) for p in derived.iterdir() if p.is_file()})
        with self.assertRaises(platform.DatasetPlatformError) as stale:
            platform.apply_overlap_plan("gold-v008-split-clean", "wrong", plan["dataset_fingerprint"])
        self.assertEqual(stale.exception.code, "OVERLAP_PLAN_STALE")
        result = platform.apply_overlap_plan("gold-v008-split-clean", plan["plan_token"], plan["dataset_fingerprint"])
        self.assertTrue(result["applied"])
        health = platform.dataset_health("gold-v008-split-clean")
        self.assertEqual(health["evaluation_integrity"]["conversation_overlap_count"], 0)
        self.assertEqual(health["evaluation_integrity"]["exact_target_overlap_count"], 0)
        self.assertEqual(health["exact_duplicate_extra"], 0)
        self.assertEqual(health["loss_mask_validation"]["total"], health["training_count"])
        self.assertEqual(health["loss_mask_validation"]["passed"], health["training_count"])
        self.assertTrue(health["diagnostics"]["valid"])
        manifest = json.loads((derived / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["state"], "Draft")
        self.assertEqual(manifest["files"]["multi_turn.jsonl"], 7)
        self.assertEqual(manifest["files"]["text_sft_eval.jsonl"], 1)
        for name, digest in manifest["sha256"].items():
            self.assertEqual(digest, platform._sha256(derived / name))
        self.assertEqual(source_before, {p.name: platform._sha256(p) for p in self.version.iterdir() if p.is_file()})

    def test_frozen_version_rejects_apply(self):
        plan = platform.create_overlap_plan("gold-v007-balanced")
        with self.assertRaises(platform.DatasetPlatformError) as frozen:
            platform.apply_overlap_plan("gold-v007-balanced", plan["plan_token"], plan["dataset_fingerprint"])
        self.assertEqual(frozen.exception.code, "TARGET_NOT_DRAFT")

    def test_plan_prefers_evaluation_when_training_would_create_duplicate(self):
        duplicate_target = row("e2", "c2", "هدف 0", 2)
        with (self.version / "text_sft_eval.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(duplicate_target, ensure_ascii=False) + "\n")
        platform.create_derived_version("gold-v007-balanced", "gold-v008-split-clean")
        plan = platform.create_overlap_plan("gold-v008-split-clean")
        self.assertEqual(plan["items"][0]["proposed_destination"], "Evaluation")
        self.assertIn("exact duplicate", plan["items"][0]["reason"])

    def test_health_rejects_inherited_diagnostics_after_membership_change(self):
        platform.create_derived_version("gold-v007-balanced", "gold-v008-split-clean")
        derived = self.exports / "gold-v008-split-clean"
        rows = platform._jsonl(derived / "multi_turn.jsonl")
        platform._write_jsonl(derived / "multi_turn.jsonl", rows[:-1])
        health = platform.dataset_health("gold-v008-split-clean")
        self.assertFalse(health["diagnostics"]["valid"])
        self.assertEqual(health["training_readiness"]["status"], "NOT_READY")
        self.assertIn("stale_diagnostics", {item["code"] for item in health["warnings"]})
        with self.assertRaises(platform.DatasetPlatformError) as stale:
            platform.freeze_dataset_version("gold-v008-split-clean")
        self.assertEqual(stale.exception.code, "INVALID_MANIFEST")


class DatasetPlatformHttpIntegrationTests(unittest.TestCase):
    @requires_private_artifacts('datasets/gold-v009-remediation-draft/manifest.json')
    def test_v009_managed_draft_is_registered_and_readable(self):
        versions = {item["version"]: item for item in platform.list_dataset_versions()}
        item = versions["gold-v009-remediation-draft"]
        self.assertTrue(item["readable"]); self.assertEqual(item["manifest_status"], "valid"); self.assertEqual(item["state"], "Frozen")
        detail = platform.dataset_version_detail("gold-v009-remediation-draft")
        self.assertEqual(detail["state"], "Frozen"); self.assertEqual(detail["health"]["training_readiness"]["status"], "READY")

    def test_duplicate_version_across_registry_roots_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); exports=root/"exports"; datasets=root/"datasets"; exports.mkdir(); datasets.mkdir()
            for base in (exports,datasets):
                path=base/"gold-duplicate"; path.mkdir(); (path/"manifest.json").write_text('{"version":"gold-duplicate","state":"DRAFT"}',encoding="utf-8")
            with patch.object(platform,"EXPORTS_ROOT",exports), patch.object(platform,"EXPORTS_DIR",exports), patch.object(platform,"DATASETS_ROOT",datasets):
                with self.assertRaises(platform.DatasetPlatformError) as raised: platform.dataset_version_detail("gold-duplicate")
                self.assertEqual(raised.exception.code,"DUPLICATE_DATASET_VERSION")

    def test_missing_registered_path_reports_structured_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(platform, "EXPORTS_ROOT", root), patch.object(platform, "EXPORTS_DIR", root), patch.object(platform, "DATASETS_ROOT", root):
                with self.assertRaises(platform.DatasetPlatformError) as raised:
                    platform.dataset_version_detail("gold-does-not-exist")
                self.assertEqual(raised.exception.code, "DATASET_NOT_FOUND")

    @requires_private_artifacts('exports/gold-v007-balanced/manifest.json')
    def test_real_endpoint_finds_v007_from_different_working_directory(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as other_cwd:
            os.chdir(other_cwd)
            server = server_module.NajdiLabHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/v1/dataset-versions", timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                by_name = {item["version"]: item for item in payload["items"]}
                self.assertEqual(response.status, 200)
                self.assertTrue(by_name["gold-v007-balanced"]["readable"])
                self.assertTrue(by_name["gold-v007-balanced"]["health_available"])
                self.assertEqual(platform.PROJECT_ROOT, Path(__file__).resolve().parents[1])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
