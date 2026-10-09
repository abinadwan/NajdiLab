from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from app import dataset_platform as platform
from app.dataset_balancer import analyze_dataset_balance
from app import server as server_module


def conversation(record_id: str, turns: int = 1, **metadata) -> dict:
    messages = []
    for index in range(turns):
        messages += [{"role": "user", "content": f"سؤال عربي {index}"}, {"role": "assistant", "content": f"إجابة عربية مفيدة رقم {index}"}]
    return {"id": record_id, "conversation_id": metadata.pop("conversation_id", record_id), "messages": messages, "target_message_index": len(messages) - 1, "message_loss_mask": [0] * (len(messages) - 1) + [1], **metadata}


class DatasetBalancerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.exports = Path(self.temp.name)
        self.version = self.exports / "gold-v007-balanced"
        self.version.mkdir()
        self.write_manifest()
        self.write_rows("sft.jsonl", [conversation("s1", review_status="APPROVED", channel="whatsapp", tags=["dialect_issue"]), conversation("s2", review_status="FULL_CORRECTION", channel="telegram")])
        self.write_rows("multi_turn.jsonl", [conversation("m1", 2, origin="manual", source="Manual")])
        self.write_rows("preference_pairs.jsonl", [{"id": "p1", "prompt_context": [{"role": "user", "content": "اختر"}], "preferred_response": "هذا أفضل", "rejected_response": "ذاك أقل", "origin": "manual"}])
        self.write_rows("text_sft_eval.jsonl", [conversation("e1", dataset_split="evaluation", channel="whatsapp")])
        self.patch = patch.object(platform, "EXPORTS_DIR", self.exports)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def write_manifest(self, value=None):
        value = value if value is not None else {"version": "gold-v007-balanced", "created_at": "2026-10-05T00:00:00Z", "files": {}}
        (self.version / "manifest.json").write_text(json.dumps(value), encoding="utf-8")

    def write_rows(self, name, rows):
        (self.version / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def test_valid_dataset_counts_turns_lengths_metadata_and_language(self):
        report = analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(report["summary"]["total_records"], 5)
        self.assertEqual(report["record_types"]["counts"]["sft"], 2)
        self.assertEqual(report["record_types"]["counts"]["multi_turn"], 1)
        self.assertEqual(report["record_types"]["counts"]["preference"], 1)
        self.assertEqual(report["record_types"]["counts"]["evaluation"], 1)
        self.assertEqual(report["conversation_structure"]["multi_turn"], 1)
        self.assertEqual(report["conversation_structure"]["max_turns"], 2)
        self.assertGreater(report["length_distribution"]["assistant"]["p95"], 0)
        self.assertIn("whatsapp", {item["name"] for item in report["sources"]["items"]})
        self.assertIn("dialect_issue", {item["name"] for item in report["error_tags"]["items"]})
        self.assertEqual(report["language_signals"]["items"][0]["name"], "arabic_dominant")
        self.assertTrue(report["read_only"])

    def test_missing_optional_metadata_is_supported(self):
        self.write_rows("sft.jsonl", [conversation("minimal")])
        report = analyze_dataset_balance("gold-v007-balanced")
        self.assertIn("Unknown", {item["name"] for item in report["sources"]["items"]})

    def test_malformed_and_unsupported_records_are_isolated_as_warning(self):
        self.write_rows("sft.jsonl", [{"id": "bad", "messages": "wrong"}])
        self.write_rows("custom.jsonl", [{"id": "custom"}])
        report = analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(report["record_types"]["counts"]["unknown"], 2)
        self.assertIn("UNSUPPORTED_RECORDS", {item["code"] for item in report["warnings"]})
        self.assertEqual(report["balance_status"], "IMBALANCED")

    def test_empty_dataset_is_unavailable(self):
        for path in self.version.glob("*.jsonl"):
            path.unlink()
        report = analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(report["balance_status"], "UNAVAILABLE")
        self.assertEqual(report["length_distribution"]["user"]["mean"], 0)

    def test_invalid_manifest_and_invalid_jsonl_are_structured(self):
        (self.version / "manifest.json").write_text("{bad", encoding="utf-8")
        with self.assertRaises(platform.DatasetPlatformError) as invalid_manifest:
            analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(invalid_manifest.exception.code, "INVALID_MANIFEST")
        self.write_manifest()
        (self.version / "sft.jsonl").write_text("{bad\n", encoding="utf-8")
        with self.assertRaises(platform.DatasetPlatformError) as invalid_data:
            analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(invalid_data.exception.code, "INVALID_DATASET")

    def test_missing_dataset_is_structured(self):
        with self.assertRaises(platform.DatasetPlatformError) as missing:
            analyze_dataset_balance("gold-v999")
        self.assertEqual(missing.exception.code, "DATASET_NOT_FOUND")

    def test_cwd_independence_and_source_files_unchanged(self):
        before = {path.name: path.read_bytes() for path in self.version.iterdir() if path.is_file()}
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as elsewhere:
            os.chdir(elsewhere)
            try:
                report = analyze_dataset_balance("gold-v007-balanced")
            finally:
                os.chdir(original)
        self.assertEqual(report["version"], "gold-v007-balanced")
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.version.iterdir() if path.is_file()})

    def test_warning_and_recommendation_rules_are_explainable(self):
        self.write_rows("sft.jsonl", [conversation(f"s{i}", channel="whatsapp") for i in range(6)])
        self.write_rows("multi_turn.jsonl", [conversation("m1", 2, channel="manual")])
        report = analyze_dataset_balance("gold-v007-balanced")
        warning = next(item for item in report["warnings"] if item["code"] == "MULTITURN_UNDERREPRESENTED")
        self.assertEqual(warning["dimension"], "record_type")
        self.assertIn("recommended_min", warning)
        self.assertTrue(any(item["category"] == "record_mix" for item in report["recommendations"]))

    def test_unreadable_dataset_is_structured(self):
        with patch("pathlib.Path.open", side_effect=PermissionError("denied")):
            with self.assertRaises(platform.DatasetPlatformError) as denied:
                analyze_dataset_balance("gold-v007-balanced")
        self.assertEqual(denied.exception.code, "ACCESS_DENIED")


class DatasetBalancerHttpTests(unittest.TestCase):
    def test_balance_endpoint_200_and_structured_404(self):
        server = server_module.NajdiLabHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/api/v1/dataset-versions/gold-v007-balanced/balance", timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertIn("balance_status", payload)
            self.assertIn("recommendations", payload)
            with self.assertRaises(HTTPError) as missing:
                urlopen(base + "/api/v1/dataset-versions/gold-v999/balance", timeout=10)
            error = json.loads(missing.exception.read().decode("utf-8"))
            self.assertEqual(error["code"], "DATASET_NOT_FOUND")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
