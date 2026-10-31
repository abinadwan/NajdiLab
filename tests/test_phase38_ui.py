from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import phase38_dataset as p38


ROOT = Path(__file__).resolve().parents[1]


from tests.private_artifacts import requires_private_artifacts

class Phase38UiTests(unittest.TestCase):
    @requires_private_artifacts('reports/phase38/v009-human-review.json')
    def test_review_queue_contains_only_expected_new_records(self):
        state = p38.get_review()
        self.assertEqual(len(state["records"]), 36)
        counts = {kind: sum(r["record_type"] == kind for r in state["records"]) for kind in ("sft", "multi_turn", "native_tool_use")}
        self.assertEqual(counts, {"sft": 12, "multi_turn": 16, "native_tool_use": 8})
        self.assertTrue(all(r["record"]["provenance"]["kind"] == "new_remediation" for r in state["records"]))
        self.assertFalse(any("holdout" in r["record_id"].lower() or "eval" in r["record_id"].lower() for r in state["records"]))

    def test_ltr_shell_drawer_and_phase38_route_are_present(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "rtl-overhaul.css").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('<html lang="en" dir="ltr">', html)
        self.assertNotIn('data-view="phase38-review"', html)  # retained deep link, retired navigation
        self.assertIn('id="phase38-status"', html)
        self.assertIn("inset-inline-start:0", css)
        self.assertIn("transform:translateX(-105%)", css)
        self.assertIn("'/evaluation/remediation-review'", js)

    def test_loading_error_retry_unsaved_and_safe_edit_ui_are_present(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        for marker in ("showPhase38Error", "phase38-retry", "phase38Dirty", "beforeunload", "proposed_assistant_edits", "results are read-only"):
            self.assertIn(marker, js)
        self.assertIn("data.records.length!==36", js)
        self.assertIn("counts.sft!==12", js)
        self.assertIn("counts.multi_turn!==16", js)
        self.assertIn("counts.native_tool_use!==8", js)

    @requires_private_artifacts('reports/phase38/v009-human-review.json')
    def test_approve_edit_reject_persistence_without_touching_real_queue(self):
        template = p38.get_review()["records"][0]
        records = []
        for index in range(36):
            record = json.loads(json.dumps(template, ensure_ascii=False))
            record["record_id"] = f"temporary-{index:02d}"
            record["decision"] = None
            records.append(record)
        state = {
            "summary": {"total": 36, "reviewed": 0, "approved": 0, "edited": 0, "rejected": 0, "remaining": 36},
            "freeze_gate": {"allowed": False},
            "records": records,
        }
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            p38.write_json(reports / "v009-human-review.json", state)
            with patch.object(p38, "REPORTS", reports):
                approved = p38.save_review("temporary-00", {"decision": "APPROVE", "review": {"notes": "سليم"}})
                self.assertEqual(approved["summary"]["approved"], 1)
                edited = p38.save_review("temporary-01", {"decision": "EDIT", "review": {"proposed_assistant_edits": {"1": "صياغة مقترحة"}}})
                self.assertEqual(edited["records"][1]["review"]["proposed_assistant_edits"]["1"], "صياغة مقترحة")
                rejected = p38.save_review("temporary-02", {"decision": "REJECT", "review": {"contamination_concern": "FAIL"}})
                self.assertEqual(rejected["summary"]["rejected"], 1)
                self.assertEqual(rejected["summary"]["reviewed"], 3)
                self.assertFalse(rejected["freeze_gate"]["allowed"])


if __name__ == "__main__":
    unittest.main()
