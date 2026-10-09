from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import complete_review_queue as batch


class CompleteReviewQueueTests(unittest.TestCase):
    def test_decision_manifest_is_complete_and_valid(self):
        self.assertEqual(batch.APPROVED | batch.DIALECT | batch.CONTENT | batch.FULL, batch.ALL_IDS)
        self.assertFalse(batch.APPROVED & batch.DIALECT)
        self.assertFalse(batch.APPROVED & batch.CONTENT)
        self.assertFalse(batch.DIALECT & batch.CONTENT)
        for review_id in batch.ALL_IDS:
            status = batch.decision_for(review_id)
            self.assertIn(status, batch.FINAL_STATUSES)
            corrected = batch.correction_for(review_id, "original")
            self.assertEqual(corrected is None, status == "APPROVED")
            self.assertTrue(set(batch.tags_for(review_id, status, "original")) <= batch.ERROR_TAGS)

    def test_atomic_guard_skips_finalized_or_concurrently_changed_rows(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE reviews(id INTEGER PRIMARY KEY, review_status TEXT, updated_at TEXT)")
        conn.executemany(
            "INSERT INTO reviews VALUES (?,?,?)",
            [(1, "PENDING", "old"), (2, "APPROVED", "new"), (3, "PENDING", "new")],
        )
        changed = conn.execute(
            "UPDATE reviews SET review_status='APPROVED' WHERE id=? AND review_status='PENDING' AND updated_at=?",
            (1, "old"),
        )
        finalized = conn.execute(
            "UPDATE reviews SET review_status='FULL_CORRECTION' WHERE id=? AND review_status='PENDING' AND updated_at=?",
            (2, "new"),
        )
        stale = conn.execute(
            "UPDATE reviews SET review_status='FULL_CORRECTION' WHERE id=? AND review_status='PENDING' AND updated_at=?",
            (3, "old"),
        )
        self.assertEqual(changed.rowcount, 1)
        self.assertEqual(finalized.rowcount, 0)
        self.assertEqual(stale.rowcount, 0)

    def test_empty_pending_snapshot_is_a_safe_rerun(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE reviews(id INTEGER PRIMARY KEY, original_response TEXT, review_status TEXT, updated_at TEXT)")
        conn.execute("INSERT INTO reviews VALUES (264, 'original', 'APPROVED', 'now')")
        with patch.object(batch, "connect", return_value=conn):
            self.assertEqual(batch.load_pending(conn), [])


if __name__ == "__main__":
    unittest.main()
