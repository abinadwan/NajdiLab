import json
import unittest
from pathlib import Path

from app.phase39_edits import EDIT_IDS, PHASE39, REVIEW, V009


class Phase39Tests(unittest.TestCase):
    def test_exactly_seven_edits_and_twenty_nine_approvals(self):
        state = json.loads(REVIEW.read_text(encoding="utf-8"))
        self.assertEqual({r["record_id"] for r in state["records"] if r["decision"] == "EDIT"}, EDIT_IDS)
        self.assertEqual(sum(r["decision"] == "APPROVE" for r in state["records"]), 29)

    def test_audit_and_verification_queue_are_focused_and_incomplete(self):
        audit = json.loads((PHASE39 / "edit-audit.json").read_text(encoding="utf-8"))
        queue = json.loads((PHASE39 / "post-edit-verification.json").read_text(encoding="utf-8"))
        self.assertTrue(audit["approved_records_unchanged"])
        self.assertEqual({r["record_id"] for r in audit["edits"]}, EDIT_IDS)
        self.assertEqual(len(queue["records"]), 7)
        self.assertEqual(queue["summary"]["verified"], sum(bool(r.get("decision")) for r in queue["records"]))

    def test_native_tool_evidence_and_registry_remain_protected(self):
        rows = {r["id"]: r for r in (json.loads(line) for line in (V009 / "native_tool_use.jsonl").read_text(encoding="utf-8").splitlines())}
        self.assertEqual(rows["p38-tool-01"]["messages"][2]["role"], "tool")
        self.assertTrue(rows["p38-tool-01"]["messages"][2]["authoritative"])
        self.assertEqual(rows["p38-tool-01"]["messages"][1]["tool_calls"][0]["function"]["name"], "fs.list")

    def test_freeze_readiness_stays_blocked(self):
        readiness = json.loads((PHASE39 / "phase39-freeze-readiness.json").read_text(encoding="utf-8"))
        self.assertEqual(readiness["status"], "BLOCKED_POST_EDIT_VERIFICATION")
        self.assertFalse(readiness["freeze_allowed"])


if __name__ == "__main__":
    unittest.main()
