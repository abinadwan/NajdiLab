from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from urllib.request import Request
from tests.http_client import urlopen
from unittest.mock import patch

import app.server as server_module
from app.db import apply_migrations, connect
from app.review_integrity import ExportReadinessError
from app.service import (
    add_direct_text,
    add_manual_sft,
    add_preference_pair,
    analytics,
    approve_review,
    bulk_update_manual_data,
    clone_manual_data,
    correct_review,
    create_conversation,
    create_export,
    delete_manual_data,
    delete_review,
    dedup_report,
    get_manual_data,
    get_conversation,
    ingest_turn,
    ingest_hermes_hook,
    ignore_manual_data,
    ignore_review,
    list_conversations,
    list_manual_data,
    list_manual_versions,
    list_review_queue,
    list_reviewed,
    save_review,
    sync_manual_export_history,
    training_dataset,
    update_manual_data,
    ValidationError,
)
from scripts.backup import create_backup
from app.dataset_masks import IGNORE_INDEX, encode_masked_sft_record


class NajdiLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "data" / "test.db"
        self.exports = self.root / "exports"
        apply_migrations(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ingest(self, conversation_id="conv-1", user="هلا", assistant="مرحبًا", **extra):
        return ingest_turn(
            {
                "conversation_id": conversation_id,
                "title": "اختبار",
                "source": "api",
                "channel": "web",
                "provider": "local",
                "model_name": "test-model",
                "user_message": user,
                "assistant_response": assistant,
                **extra,
            },
            self.db,
        )

    def test_01_create_conversation_and_resume(self):
        created = create_conversation({"conversation_id": "standalone", "title": "مستقلة"}, self.db)
        self.assertEqual(created["external_conversation_id"], "standalone")
        reopened = connect(self.db)
        try:
            self.assertEqual(reopened.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 1)
            self.assertEqual(reopened.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(reopened.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        finally:
            reopened.close()

    def test_02_ingest_turn_creates_pending_review(self):
        result = self.ingest()
        self.assertEqual(result["review_status"], "PENDING")
        queue = list_review_queue(self.db)
        self.assertEqual(len(queue), 1)
        self.assertEqual([m["role"] for m in queue[0]["context"]], ["user", "assistant"])

    def test_03_all_review_outcomes_and_original_immutability(self):
        cases = [
            ("FULL_CORRECTION", "تصحيح كامل"),
            ("DIALECT_CORRECTION", "تصحيح لهجة"),
            ("CONTENT_CORRECTION", "تصحيح محتوى"),
            ("APPROVED", None),
        ]
        for index, (status, corrected) in enumerate(cases):
            result = self.ingest(f"r-{index}", assistant=f"الأصل {index}")
            review = save_review(
                result["review_id"],
                {
                    "review_status": status,
                    "corrected_response": corrected,
                    "training_eligible": True,
                    "tags": [] if status == "APPROVED" else ["other"],
                },
                self.db,
            )
            self.assertEqual(review["review_status"], status)
            self.assertEqual(review["original_response"], f"الأصل {index}")
            self.assertEqual(review["corrected_response"], corrected)
        self.assertEqual(len(list_review_queue(self.db)), 0)

    def test_04_training_eligibility_and_evaluation_protection(self):
        train = self.ingest("train")
        # Its own answer: an evaluation turn identical to a training turn is train/eval leakage and is refused.
        holdout = self.ingest("eval", assistant="أهلًا وسهلًا")
        save_review(train["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        reviewed = save_review(
            holdout["review_id"],
            {"review_status": "APPROVED", "training_eligible": True, "evaluation_only": True},
            self.db,
        )
        self.assertEqual(reviewed["training_eligible"], 0)
        dataset = training_dataset(self.db)
        self.assertEqual(len(dataset["reviews"]), 1)
        export = create_export(self.db, self.exports)
        sft = (Path(export["path"]) / "sft.jsonl").read_text(encoding="utf-8")
        holdout_text = (Path(export["path"]) / "evaluation_holdout.jsonl").read_text(encoding="utf-8")
        self.assertIn("train", sft)
        self.assertNotIn("eval", sft)
        self.assertIn("eval", holdout_text)

    def test_05_full_multiturn_context_reconstruction(self):
        first = self.ingest("multi", "سجّل أن اللون أزرق", "تم")
        save_review(first["review_id"], {"review_status": "APPROVED", "training_eligible": False}, self.db)
        second = self.ingest("multi", "وش اللون؟", "أحمر")
        save_review(
            second["review_id"],
            {"review_status": "CONTENT_CORRECTION", "corrected_response": "أزرق", "training_eligible": True},
            self.db,
        )
        record = training_dataset(self.db)["reviews"][0]
        self.assertEqual([m["role"] for m in record["messages"]], ["user", "assistant", "user", "assistant"])
        self.assertEqual(record["messages"][-1]["content"], "أزرق")
        original = get_conversation(second["conversation_id"], self.db)["messages"][-1]["content"]
        self.assertEqual(original, "أحمر")

    def test_06_manual_direct_and_preference_exports(self):
        add_manual_sft(
            {"messages": [{"role": "user", "content": "س"}, {"role": "assistant", "content": "ج"}], "language_layer": "msa", "origin": "manual", "training_eligible": True},
            self.db,
        )
        add_direct_text(
            {"text": "نص مباشر", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True},
            self.db,
        )
        add_preference_pair(
            {"prompt_context": "سياق", "rejected_response": "سيئ", "preferred_response": "جيد", "origin": "manual", "training_eligible": True},
            self.db,
        )
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        self.assertIn("نص مباشر", (path / "direct_language.jsonl").read_text(encoding="utf-8"))
        self.assertIn("جيد", (path / "preference_pairs.jsonl").read_text(encoding="utf-8"))
        self.assertIn('"content":"ج"', (path / "sft.jsonl").read_text(encoding="utf-8"))

    def test_07_dataset_versioning_and_sha_manifest(self):
        result = self.ingest()
        save_review(result["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        one = create_export(self.db, self.exports)
        two = create_export(self.db, self.exports)
        self.assertEqual(one["version"], "gold-v001")
        self.assertEqual(two["version"], "gold-v002")
        manifest = json.loads((Path(one["path"]) / "manifest.json").read_text(encoding="utf-8"))
        for filename, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((Path(one["path"]) / filename).read_bytes()).hexdigest(), digest)

    def test_08_filters_and_full_text_search(self):
        result = self.ingest(user="عبارة فريدة للبحث")
        save_review(
            result["review_id"],
            {"review_status": "DIALECT_CORRECTION", "corrected_response": "ياهلا", "tags": ["dialect_issue"]},
            self.db,
        )
        self.assertEqual(len(list_conversations(self.db, search="فريدة")), 1)
        filtered = list_reviewed({"review_status": "DIALECT_CORRECTION", "tag": "dialect_issue"}, self.db)
        self.assertEqual(len(filtered), 1)

    def test_09_secret_redaction(self):
        self.ingest(metadata={"api_key": "must-not-store", "nested": {"token": "secret", "safe": "ok"}})
        conn = connect(self.db)
        try:
            metadata = conn.execute("SELECT metadata_json FROM conversations").fetchone()[0]
            self.assertNotIn("must-not-store", metadata)
            self.assertNotIn("secret", metadata)
            self.assertIn("[REDACTED]", metadata)
        finally:
            conn.close()

    def test_10_dedup_report_does_not_delete(self):
        for idx in range(2):
            add_direct_text(
                {"text": "نفس النص تمامًا", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True},
                self.db,
            )
        report = dedup_report(self.db)
        self.assertEqual(len(report["exact_duplicate_groups"]), 1)
        self.assertEqual(training_dataset(self.db)["stats"]["direct_language_texts"], 2)

    def test_11_analytics(self):
        result = self.ingest()
        save_review(result["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        data = analytics(self.db)
        self.assertEqual(data["summary"]["total_conversations"], 1)
        self.assertEqual(data["summary"]["approved_pct"], 100.0)
        self.assertEqual(data["by_model"][0]["name"], "test-model")

    def test_12_timestamped_backup(self):
        self.ingest()
        backup_root = self.root / "backup-project"
        (backup_root / "data").mkdir(parents=True)
        source = sqlite3.connect(self.db)
        dest = sqlite3.connect(backup_root / "data" / "najdilab.db")
        source.backup(dest); source.close(); dest.close()
        (backup_root / "exports" / "gold-v001").mkdir(parents=True)
        (backup_root / "exports" / "gold-v001" / "manifest.json").write_text("{}", encoding="utf-8")
        first = create_backup(backup_root)
        second = create_backup(backup_root)
        self.assertNotEqual(first, second)
        with zipfile.ZipFile(first) as archive:
            self.assertIn("data/najdilab.db", archive.namelist())
            self.assertIn("exports/gold-v001/manifest.json", archive.namelist())

    def test_13_stable_source_message_id_is_idempotent(self):
        first = self.ingest(source_message_id="stable-turn-1")
        second = self.ingest(source_message_id="stable-turn-1")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        conn = connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
        finally:
            conn.close()

    def test_14_hermes_hook_uses_pseudonymous_continuity_and_safe_defaults(self):
        base = {
            "hook_event_name": "post_llm_call",
            "profile": "default",
            "session_id": "session-safe-id",
            "delivery_id": "delivery-1",
            "timestamp": "2026-10-02T09:00:00Z",
            "extra": {
                "turn_id": "turn-1",
                "user_message": "السلام عليكم",
                "assistant_response": "وعليكم السلام",
                "model": "gemma4-hermes:latest",
                "provider": "ollama",
                "platform": "whatsapp",
                "conversation_key_hash": "a" * 64,
                "system_prompt_version": "sha256:" + "b" * 64,
                "generation_settings": {"temperature": 0.2},
            },
        }
        first = ingest_hermes_hook(base, self.db)
        duplicate = ingest_hermes_hook(base, self.db)
        second_payload = json.loads(json.dumps(base))
        second_payload["delivery_id"] = "delivery-2"
        second_payload["extra"]["turn_id"] = "turn-2"
        second_payload["extra"]["user_message"] = "كمل"
        second_payload["extra"]["assistant_response"] = "أبشر"
        second = ingest_hermes_hook(second_payload, self.db)

        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        conversation = get_conversation(first["conversation_id"], self.db)
        self.assertEqual(len(conversation["messages"]), 4)
        self.assertEqual(conversation["conversation"]["external_conversation_id"], "hermes:default:" + "a" * 64)
        reviews = list_review_queue(self.db)
        self.assertTrue(all(item["training_eligible"] == 0 for item in reviews))
        raw = json.dumps(conversation, ensure_ascii=False)
        self.assertNotIn("+966", raw)
        self.assertNotIn("api_key", raw)

    def test_15_manual_manager_lists_all_types_and_filters_search_sort(self):
        sft = add_manual_sft(
            {
                "messages": [{"role": "user", "content": "سؤال نجدي فريد"}, {"role": "assistant", "content": "جواب"}],
                "language_layer": "najdi_riyadh", "domain": "لهجة", "source": "مراجعة بشرية",
                "source_type": "human_corrected", "origin": "human_corrected", "training_eligible": True,
            }, self.db,
        )
        direct = add_direct_text(
            {"text": "نص تقني فريد", "language_layer": "technical_arabic", "domain": "تقنية", "source": "كاتب",
             "source_type": "human_written", "origin": "manual", "training_eligible": False}, self.db,
        )
        dpo = add_preference_pair(
            {"prompt_context": "سياق", "rejected_response": "رد مرفوض", "preferred_response": "رد مفضل",
             "language_layer": "formal_arabic", "domain": "أسلوب", "source": "تحكيم",
             "source_type": "synthetic_reviewed", "origin": "synthetic_reviewed", "training_eligible": True}, self.db,
        )
        listing = list_manual_data({}, self.db)
        self.assertEqual(listing["summary"]["total"], 3)
        self.assertEqual({item["item_type"] for item in listing["items"]}, {"sft", "direct", "dpo"})
        self.assertEqual(len(list_manual_data({"search": "تقني"}, self.db)["items"]), 1)
        self.assertEqual(len(list_manual_data({"type": "sft", "language_layer": "najdi_riyadh"}, self.db)["items"]), 1)
        self.assertEqual(list_manual_data({"sort": "oldest"}, self.db)["items"][0]["id"], sft["id"])
        self.assertEqual(direct["id"], 1)
        self.assertEqual(dpo["id"], 1)

    def test_16_edit_all_types_and_version_history(self):
        sft = add_manual_sft(
            {"messages": [{"role": "user", "content": "قبل"}, {"role": "assistant", "content": "قديم"}],
             "language_layer": "msa", "origin": "manual"}, self.db,
        )
        direct = add_direct_text(
            {"text": "قبل", "language_layer": "msa", "source": "أصل ثابت", "source_type": "human_written", "origin": "manual"}, self.db,
        )
        dpo = add_preference_pair(
            {"prompt_context": "س", "rejected_response": "أ", "preferred_response": "ب", "origin": "manual"}, self.db,
        )
        updated_sft = update_manual_data("sft", sft["id"], {
            "messages": [{"role": "system", "content": "تعليمات"}, {"role": "user", "content": "بعد"}, {"role": "assistant", "content": "جديد"}],
            "change_notes": "تعديل الحوار",
        }, self.db)
        updated_direct = update_manual_data("direct", direct["id"], {"text": "بعد", "notes": "ملاحظة", "change_notes": "تعديل النص"}, self.db)
        updated_dpo = update_manual_data("dpo", dpo["id"], {"preferred_response": "أفضل", "change_notes": "تعديل التفضيل"}, self.db)
        self.assertEqual(updated_sft["version_number"], 2)
        self.assertEqual(updated_direct["version_number"], 2)
        self.assertEqual(updated_dpo["version_number"], 2)
        versions = list_manual_versions("direct", direct["id"], self.db)
        self.assertEqual([item["version_number"] for item in versions], [2, 1])
        self.assertEqual(versions[0]["change_notes"], "تعديل النص")
        self.assertEqual(versions[1]["snapshot"]["text"], "قبل")
        with self.assertRaises(ValidationError):
            update_manual_data("direct", direct["id"], {"text": ""}, self.db)
        with self.assertRaises(ValidationError):
            update_manual_data("direct", direct["id"], {"source": ""}, self.db)
        with self.assertRaises(ValidationError):
            update_manual_data("dpo", dpo["id"], {"rejected_response": "أفضل", "preferred_response": "أفضل"}, self.db)

    def test_17_clone_archive_exclude_eligibility_and_bulk(self):
        direct = add_direct_text(
            {"text": "أصل", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        clone = clone_manual_data("direct", direct["id"], {"text": "نسخة"}, self.db)
        self.assertNotEqual(clone["id"], direct["id"])
        self.assertEqual(clone["parent_item_id"], direct["id"])
        archived = update_manual_data("direct", direct["id"], {"archived": True, "change_notes": "أرشفة"}, self.db)
        self.assertFalse(archived["training_eligible_effective"])
        self.assertEqual(len(list_manual_data({}, self.db)["items"]), 1)
        self.assertEqual(len(list_manual_data({"show_archived": "1"}, self.db)["items"]), 2)
        unarchived = update_manual_data("direct", direct["id"], {"archived": False}, self.db)
        self.assertTrue(unarchived["training_eligible_effective"])
        excluded = update_manual_data("direct", direct["id"], {"exclude_from_training": True}, self.db)
        self.assertFalse(excluded["training_eligible_effective"])
        reenabled = update_manual_data("direct", direct["id"], {"exclude_from_training": False, "training_eligible": False}, self.db)
        self.assertFalse(reenabled["training_eligible_effective"])
        result = bulk_update_manual_data({"action": "eligible", "items": [{"type": "direct", "id": direct["id"]}, {"type": "direct", "id": clone["id"]}]}, self.db)
        self.assertEqual(result["updated"], 2)
        self.assertTrue(get_manual_data("direct", direct["id"], self.db)["training_eligible_effective"])

    def test_18_export_safety_history_and_old_export_immutability(self):
        direct = add_direct_text(
            {"text": "يدخل النسخة القديمة", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        export = create_export(self.db, self.exports)
        old_file = Path(export["path"]) / "direct_language.jsonl"
        old_digest = hashlib.sha256(old_file.read_bytes()).hexdigest()
        item = get_manual_data("direct", direct["id"], self.db)
        self.assertEqual(item["exported_versions"], ["gold-v001"])
        update_manual_data("direct", direct["id"], {"text": "نص جديد", "archived": True}, self.db)
        self.assertEqual(training_dataset(self.db)["direct_language"], [])
        self.assertEqual(hashlib.sha256(old_file.read_bytes()).hexdigest(), old_digest)
        self.assertIn("يدخل النسخة القديمة", old_file.read_text(encoding="utf-8"))
        self.assertNotIn("نص جديد", old_file.read_text(encoding="utf-8"))
        update_manual_data("direct", direct["id"], {"archived": False, "exclude_from_training": True}, self.db)
        self.assertEqual(training_dataset(self.db)["direct_language"], [])

    def test_19_exported_delete_requires_confirmation_and_preserves_export(self):
        direct = add_direct_text(
            {"text": "سجل للحذف", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        export = create_export(self.db, self.exports)
        old_file = Path(export["path"]) / "direct_language.jsonl"
        old_content = old_file.read_text(encoding="utf-8")
        with self.assertRaises(ValidationError):
            delete_manual_data("direct", direct["id"], False, self.db)
        self.assertEqual(get_manual_data("direct", direct["id"], self.db)["id"], direct["id"])
        deleted = delete_manual_data("direct", direct["id"], True, self.db)
        self.assertTrue(deleted["deleted"])
        self.assertEqual(old_file.read_text(encoding="utf-8"), old_content)
        with self.assertRaises(ValidationError):
            get_manual_data("direct", direct["id"], self.db)

    def test_20_sync_existing_export_history_from_jsonl(self):
        direct = add_direct_text(
            {"text": "مزامنة", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        export = create_export(self.db, self.exports)
        conn = connect(self.db)
        try:
            conn.execute("DELETE FROM manual_data_export_history")
        finally:
            conn.close()
        shutil.rmtree(export["path"])
        self.assertGreater(sync_manual_export_history(self.db), 0)
        self.assertEqual(get_manual_data("direct", direct["id"], self.db)["exported_versions"], ["gold-v001"])

    def test_21_review_action_helpers_with_explicit_eligibility(self):
        approved_source = self.ingest("approve-action", assistant="رد يعتمد")
        corrected_source = self.ingest("correct-action", assistant="رد يحتاج تعديل")
        approved = approve_review(approved_source["review_id"], {"training_eligible": True}, self.db)
        corrected = correct_review(
            corrected_source["review_id"],
            {"review_status": "DIALECT_CORRECTION", "corrected_response": "رد مصحح", "training_eligible": True},
            self.db,
        )
        self.assertEqual(approved["review_status"], "APPROVED")
        self.assertEqual(approved["training_eligible"], 1)
        self.assertEqual(corrected["review_status"], "DIALECT_CORRECTION")
        self.assertEqual(corrected["corrected_response"], "رد مصحح")
        self.assertEqual(corrected["training_eligible"], 1)
        self.assertEqual(len(training_dataset(self.db)["reviews"]), 2)

    def test_22_ignore_review_is_auditable_and_never_trainable(self):
        result = self.ingest("ignore-review")
        ignored = ignore_review(result["review_id"], {"ignored_reason": "غير مناسب"}, self.db)
        self.assertEqual(ignored["review_status"], "IGNORED")
        self.assertEqual(ignored["training_eligible"], 0)
        self.assertIsNotNone(ignored["ignored_at"])
        self.assertEqual(ignored["ignored_reason"], "غير مناسب")
        self.assertIsNone(ignored["deleted_at"])
        self.assertEqual(list_review_queue(self.db), [])
        self.assertEqual(training_dataset(self.db)["reviews"], [])
        self.assertEqual(len(list_reviewed({"review_status": "IGNORED"}, self.db)), 1)
        self.assertEqual(analytics(self.db)["summary"]["ignored"], 1)

    def test_23_delete_review_is_soft_and_never_trainable(self):
        result = self.ingest("delete-review")
        deleted = delete_review(result["review_id"], {}, self.db)
        self.assertEqual(deleted["review_status"], "DELETED")
        self.assertEqual(deleted["training_eligible"], 0)
        self.assertIsNotNone(deleted["deleted_at"])
        self.assertIsNone(deleted["ignored_at"])
        self.assertEqual(list_review_queue(self.db), [])
        self.assertEqual(training_dataset(self.db)["reviews"], [])
        conn = connect(self.db)
        try:
            row = conn.execute("SELECT review_status, deleted_at FROM reviews WHERE id = ?", (result["review_id"],)).fetchone()
            self.assertEqual(row["review_status"], "DELETED")
            self.assertIsNotNone(row["deleted_at"])
        finally:
            conn.close()
        self.assertEqual(analytics(self.db)["summary"]["deleted"], 1)

    def test_24_all_manual_types_use_soft_delete_and_ignore_gates(self):
        sft = add_manual_sft(
            {"messages": [{"role": "user", "content": "س"}, {"role": "assistant", "content": "ج"}],
             "language_layer": "msa", "origin": "manual", "training_eligible": True}, self.db,
        )
        direct = add_direct_text(
            {"text": "نص", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        dpo = add_preference_pair(
            {"prompt_context": "سياق", "rejected_response": "مرفوض", "preferred_response": "مفضل",
             "origin": "manual", "training_eligible": True}, self.db,
        )
        for item_type, table, item_id in (
            ("sft", "manual_sft_items", sft["id"]),
            ("direct", "direct_language_texts", direct["id"]),
            ("dpo", "preference_pairs", dpo["id"]),
        ):
            result = delete_manual_data(item_type, item_id, False, self.db)
            self.assertTrue(result["deleted"])
            conn = connect(self.db)
            try:
                row = conn.execute(
                    f"SELECT deleted_at, ignored_at, training_eligible, exclude_from_training FROM {table} WHERE id = ?",
                    (item_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertIsNotNone(row["deleted_at"])
                self.assertIsNone(row["ignored_at"])
                self.assertEqual(row["training_eligible"], 0)
                self.assertEqual(row["exclude_from_training"], 1)
            finally:
                conn.close()
        self.assertEqual(training_dataset(self.db)["stats"]["total"], 0)
        with self.assertRaises(ExportReadinessError) as blocked:
            create_export(self.db, self.exports)
        self.assertIn("NO_EXPORTABLE_DATA", {item["code"] for item in blocked.exception.readiness["blocking_findings"]})
        self.assertFalse(self.exports.exists())

        ignored = add_direct_text(
            {"text": "متجاهل", "language_layer": "msa", "source_type": "human_written", "origin": "manual", "training_eligible": True}, self.db,
        )
        ignored_item = ignore_manual_data("direct", ignored["id"], {"ignored_reason": "مكرر"}, self.db)
        self.assertIsNotNone(ignored_item["ignored_at"])
        self.assertIsNone(ignored_item["deleted_at"])
        self.assertFalse(ignored_item["training_eligible_effective"])
        self.assertEqual(training_dataset(self.db)["direct_language"], [])

    def test_25_review_training_allowlist_wins_over_hostile_flags(self):
        ignored = self.ingest("hostile-ignore")
        deleted = self.ingest("hostile-delete")
        conn = connect(self.db)
        try:
            conn.execute("PRAGMA ignore_check_constraints = ON")
            conn.execute(
                "UPDATE reviews SET review_status = 'IGNORED', ignored_at = ?, training_eligible = 1, evaluation_only = 1, exclude_from_training = 0 WHERE id = ?",
                ("2026-10-03T00:00:00Z", ignored["review_id"]),
            )
            conn.execute(
                "UPDATE reviews SET review_status = 'DELETED', deleted_at = ?, training_eligible = 1, evaluation_only = 1, exclude_from_training = 0 WHERE id = ?",
                ("2026-10-03T00:00:00Z", deleted["review_id"]),
            )
            conn.execute("PRAGMA ignore_check_constraints = OFF")
        finally:
            conn.close()
        self.assertEqual(training_dataset(self.db)["reviews"], [])
        self.assertEqual(dedup_report(self.db)["record_count"], 0)
        with self.assertRaises(ExportReadinessError) as blocked:
            create_export(self.db, self.exports)
        codes = {item["code"] for item in blocked.exception.readiness["blocking_findings"]}
        self.assertIn("REVIEW_ELIGIBILITY_CONFLICT", codes)
        self.assertIn("REVIEW_SPLIT_CONFLICT", codes)
        self.assertFalse(self.exports.exists())

    def test_26_full_archive_keeps_ignored_and_deleted_reviews(self):
        ignored_source = self.ingest("archive-ignore", assistant="نص متجاهل")
        deleted_source = self.ingest("archive-delete", assistant="نص محذوف")
        approved_source = self.ingest("archive-approved", assistant="نص معتمد")
        ignore_review(ignored_source["review_id"], {"ignored_reason": "للأرشيف"}, self.db)
        delete_review(deleted_source["review_id"], {}, self.db)
        approve_review(approved_source["review_id"], {"training_eligible": True}, self.db)
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        archive = json.loads((path / "full_archive.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in archive["reviews"]}
        ignored = by_id[ignored_source["review_id"]]
        deleted = by_id[deleted_source["review_id"]]
        self.assertEqual(ignored["review_status"], "IGNORED")
        self.assertIsNotNone(ignored["ignored_at"])
        self.assertEqual(deleted["review_status"], "DELETED")
        self.assertIsNotNone(deleted["deleted_at"])
        training_text = "".join(
            (path / filename).read_text(encoding="utf-8")
            for filename in ("sft.jsonl", "multi_turn.jsonl", "evaluation_holdout.jsonl")
        )
        self.assertNotIn("نص متجاهل", training_text)
        self.assertNotIn("نص محذوف", training_text)
        self.assertEqual(export["manifest"]["ignored_count"], 1)
        self.assertEqual(export["manifest"]["deleted_count"], 1)

    def test_27_review_action_http_endpoints(self):
        records = [self.ingest(f"http-action-{index}") for index in range(4)]
        bindings = {
            "approve_review": lambda review_id, data: approve_review(review_id, data, self.db),
            "correct_review": lambda review_id, data: correct_review(review_id, data, self.db),
            "ignore_review": lambda review_id, data: ignore_review(review_id, data, self.db),
            "delete_review": lambda review_id, data: delete_review(review_id, data, self.db),
        }
        patches = [patch.object(server_module, name, value) for name, value in bindings.items()]
        for active_patch in patches:
            active_patch.start()
        server = server_module.ThreadingHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(path: str, payload: dict) -> dict:
                request = Request(
                    f"http://127.0.0.1:{server.server_address[1]}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    return json.loads(response.read().decode("utf-8"))

            approved = post(f"/api/v1/reviews/{records[0]['review_id']}/approve", {})
            corrected = post(
                f"/api/v1/reviews/{records[1]['review_id']}/correct",
                {"review_status": "CONTENT_CORRECTION", "corrected_response": "مصحح"},
            )
            ignored = post(f"/api/v1/reviews/{records[2]['review_id']}/ignore", {"ignored_reason": "اختبار"})
            deleted = post(f"/api/v1/reviews/{records[3]['review_id']}/delete", {})
            self.assertEqual(approved["review"]["review_status"], "APPROVED")
            self.assertEqual(corrected["review"]["review_status"], "CONTENT_CORRECTION")
            self.assertEqual(ignored["review"]["review_status"], "IGNORED")
            self.assertEqual(deleted["review"]["review_status"], "DELETED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            for active_patch in reversed(patches):
                active_patch.stop()

    def test_28_review_ui_uses_lifecycle_actions_without_legacy_wording(self):
        static_root = Path(__file__).resolve().parents[1] / "static"
        html = (static_root / "index.html").read_text(encoding="utf-8")
        javascript = (static_root / "app.js").read_text(encoding="utf-8")
        combined = html + javascript
        for button_id, label in (
            ("approve-review", "Approve"),
            ("edit-review", "Edit"),
            ("exclude-review", "Exclude"),
            ("delete-review", "Delete"),
        ):
            self.assertIn(f'id="{button_id}"', html)
            self.assertIn(label, html)
        for action in ("approve", "correct", "exclude", "delete"):
            self.assertIn(f"runReviewAction('{action}'", javascript)
        self.assertIn("IGNORED:'Ignored'", javascript)
        self.assertIn("DELETED:'Deleted'", javascript)
        # Phase 3 Human Review intentionally has a temporary-defer control; the
        # legacy review queue must still have no skip-review action.
        self.assertNotIn("skip-review", combined)
        self.assertNotIn("Permanently delete", combined)
        self.assertNotIn("prompt(", combined)

    def test_29_all_review_decisions_stay_out_of_queue_after_reload(self):
        records = [self.ingest(f"reload-{index}") for index in range(4)]
        approve_review(records[0]["review_id"], {"training_eligible": True}, self.db)
        correct_review(
            records[1]["review_id"],
            {"review_status": "FULL_CORRECTION", "corrected_response": "نسخة مصححة", "training_eligible": True},
            self.db,
        )
        ignore_review(records[2]["review_id"], {}, self.db)
        delete_review(records[3]["review_id"], {}, self.db)
        self.assertEqual(list_review_queue(self.db), [])
        self.assertEqual(list_review_queue(self.db), [])
        dataset = training_dataset(self.db)
        self.assertEqual({item["review_status"] for item in dataset["reviews"]}, {"APPROVED", "FULL_CORRECTION"})

    def test_30_multiturn_exports_only_final_gold_target(self):
        first = self.ingest("masked-multi", "السؤال الأول", "الرد القديم الخاطئ")
        save_review(first["review_id"], {"review_status": "APPROVED", "training_eligible": False}, self.db)
        second = self.ingest("masked-multi", "السؤال التالي", "إجابة خاطئة")
        save_review(
            second["review_id"],
            {
                "review_status": "CONTENT_CORRECTION",
                "corrected_response": "الإجابة الذهبية",
                "training_eligible": True,
            },
            self.db,
        )
        export = create_export(self.db, self.exports)
        rows = [
            json.loads(line)
            for line in (Path(export["path"]) / "multi_turn.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 1)
        record = rows[0]
        self.assertEqual(record["messages"][1]["content"], "الرد القديم الخاطئ")
        self.assertEqual(record["messages"][-1]["content"], "الإجابة الذهبية")
        self.assertEqual(record["target_message_index"], 3)
        self.assertEqual(record["message_loss_mask"], [0, 0, 0, 1])
        self.assertTrue(record["train_on_last_assistant_only"])

    def test_31_evaluation_conversation_is_fully_isolated(self):
        train = self.ingest("isolated-conversation", "تدريب", "رد تدريب")
        save_review(train["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        evaluation = self.ingest("isolated-conversation", "تقييم", "رد تقييم")
        save_review(
            evaluation["review_id"],
            {"review_status": "APPROVED", "training_eligible": True, "evaluation_only": True},
            self.db,
        )
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        training_rows = [
            json.loads(line)
            for filename in ("sft.jsonl", "multi_turn.jsonl")
            for line in (path / filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        evaluation_rows = [
            json.loads(line)
            for line in (path / "evaluation_holdout.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertFalse(any(item.get("conversation_id") == "isolated-conversation" for item in training_rows))
        self.assertEqual(
            sum(item.get("conversation_id") == "isolated-conversation" for item in evaluation_rows),
            2,
        )
        self.assertTrue(export["manifest"]["validation"]["no_train_eval_conversation_overlap"])

    def test_32_exact_duplicate_targets_are_removed_by_priority(self):
        lower = self.ingest("duplicate-content", assistant="قديم")
        save_review(
            lower["review_id"],
            {
                "review_status": "CONTENT_CORRECTION",
                "corrected_response": "هدف ذهبي مكرر",
                "training_eligible": True,
            },
            self.db,
        )
        higher = self.ingest("duplicate-approved", assistant="هدف ذهبي مكرر")
        save_review(higher["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        rows = [
            json.loads(line)
            for filename in ("sft.jsonl", "multi_turn.jsonl")
            for line in (path / filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        matching = [item for item in rows if item["messages"][-1]["content"] == "هدف ذهبي مكرر"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["review_status"], "APPROVED")
        self.assertEqual(export["manifest"]["exact_duplicates_removed"], 1)

    def test_33_near_duplicates_remain_in_training(self):
        for text in ("هذا نص نجدي طويل للاختبار فقط", "هذا نص نجدي طويل للاختبار فقط!"):
            add_direct_text(
                {
                    "text": text,
                    "language_layer": "najdi_riyadh",
                    "source_type": "human_written",
                    "origin": "manual",
                    "training_eligible": True,
                },
                self.db,
            )
        export = create_export(self.db, self.exports)
        rows = [
            json.loads(line)
            for line in (Path(export["path"]) / "direct_language.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 2)
        self.assertEqual(export["manifest"]["exact_duplicates_removed"], 0)
        self.assertGreaterEqual(export["manifest"]["near_duplicate_count"], 1)

    def test_34_demo_records_are_excluded_when_disabled(self):
        add_direct_text(
            {
                "text": "سجل تجريبي لا يدخل",
                "language_layer": "msa",
                "source_type": "human_written",
                "origin": "manual",
                "training_eligible": True,
                "demo": True,
            },
            self.db,
        )
        add_direct_text(
            {
                "text": "سجل حقيقي يدخل",
                "language_layer": "msa",
                "source_type": "human_written",
                "origin": "manual",
                "training_eligible": True,
            },
            self.db,
        )
        export = create_export(self.db, self.exports, include_demo=False)
        content = (Path(export["path"]) / "direct_language.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("سجل تجريبي لا يدخل", content)
        self.assertIn("سجل حقيقي يدخل", content)
        self.assertEqual(export["manifest"]["demo_records_included"], 0)

    def test_35_preference_records_never_enter_sft_files(self):
        sft = add_manual_sft(
            {
                "messages": [{"role": "user", "content": "سؤال"}, {"role": "assistant", "content": "جواب"}],
                "language_layer": "msa",
                "origin": "manual",
                "training_eligible": True,
            },
            self.db,
        )
        preference = add_preference_pair(
            {
                "prompt_context": "سياق مستقل",
                "rejected_response": "رد مرفوض لا يظهر في SFT",
                "preferred_response": "رد مفضل مستقل",
                "origin": "manual",
                "training_eligible": True,
            },
            self.db,
        )
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        sft_text = (path / "sft.jsonl").read_text(encoding="utf-8") + (path / "multi_turn.jsonl").read_text(encoding="utf-8")
        preference_text = (path / "preference_pairs.jsonl").read_text(encoding="utf-8")
        self.assertIn(f'manual_sft_items:{sft["id"]}', sft_text)
        self.assertNotIn("رد مرفوض لا يظهر في SFT", sft_text)
        self.assertNotIn(f'preference_pairs:{preference["id"]}', sft_text)
        self.assertIn(f'preference_pairs:{preference["id"]}', preference_text)

    def test_36_all_export_jsonl_files_parse_line_by_line(self):
        source = self.ingest("jsonl-valid", user="اختبار", assistant="سليم")
        save_review(source["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        for filename in (
            "sft.jsonl",
            "multi_turn.jsonl",
            "direct_language.jsonl",
            "preference_pairs.jsonl",
            "evaluation_holdout.jsonl",
        ):
            for line in (path / filename).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.assertIsInstance(json.loads(line), dict)
        self.assertTrue(export["manifest"]["validation"]["jsonl_parse_valid"])

    def test_37_token_loss_mask_excludes_previous_assistant_responses(self):
        class FakeTokenizer:
            def __init__(self):
                self.chat_template = "no generation blocks"
                self.specials = {"<s>": 1, "</s>": 2, "[INST]": 3, "[/INST]": 4}
                self.reverse = {value: key for key, value in self.specials.items()}
                self.char_ids = {}

            def _render(self, messages):
                result = "<s>"
                for message in messages:
                    if message["role"] == "user":
                        result += f'[INST]{message["content"]}[/INST]'
                    else:
                        result += f'{message["content"]}</s>'
                return result

            def _encode(self, text):
                ids = []
                offsets = []
                index = 0
                while index < len(text):
                    special = next((value for value in self.specials if text.startswith(value, index)), None)
                    if special is not None:
                        ids.append(self.specials[special])
                        offsets.append((index, index + len(special)))
                        index += len(special)
                        continue
                    char = text[index]
                    token = self.char_ids.setdefault(char, 100 + len(self.char_ids))
                    self.reverse[token] = char
                    ids.append(token)
                    offsets.append((index, index + 1))
                    index += 1
                return ids, offsets

            def apply_chat_template(self, messages, tokenize, add_generation_prompt, return_tensors=None, **kwargs):
                rendered = self._render(messages)
                if not tokenize:
                    return rendered
                ids, _ = self._encode(rendered)
                return ids

            def __call__(self, text, **kwargs):
                ids, offsets = self._encode(text)
                result = {"input_ids": ids}
                if kwargs.get("return_offsets_mapping"):
                    result["offset_mapping"] = offsets
                return result

            def decode(self, ids, skip_special_tokens=False, clean_up_tokenization_spaces=False):
                return "".join(
                    self.reverse[token]
                    for token in ids
                    if not skip_special_tokens or token not in self.specials.values()
                )

        tokenizer = FakeTokenizer()
        record = {
            "id": "masked-token-test",
            "messages": [
                {"role": "user", "content": "السؤال الأول"},
                {"role": "assistant", "content": "رد سابق خاطئ"},
                {"role": "user", "content": "السؤال الأخير"},
                {"role": "assistant", "content": "الرد الذهبي"},
            ],
            "target_message_index": 3,
            "train_on_last_assistant_only": True,
            "message_loss_mask": [0, 0, 0, 1],
        }
        encoded = encode_masked_sft_record(record, tokenizer)
        trainable_ids = [
            token for token, label in zip(encoded["input_ids"], encoded["labels"])
            if label != IGNORE_INDEX
        ]
        self.assertEqual(tokenizer.decode(trainable_ids), "الرد الذهبي")
        self.assertTrue(all(label == IGNORE_INDEX for label in encoded["labels"][: encoded["target_token_start"]]))

    def test_37b_review_76_keeps_the_initial_alef(self):
        class Review76Tokenizer:
            chat_template = "no generation blocks"
            specials = {"<s>": 1, "</s>": 2, "[INST]": 3, "[/INST]": 4}

            def __init__(self):
                self.reverse = {value: key for key, value in self.specials.items()}
                self.char_ids = {}

            def _render(self, messages):
                rendered = "<s>"
                for message in messages:
                    if message["role"] == "user":
                        rendered += f'[INST]{message["content"]}[/INST]'
                    else:
                        rendered += f'{message["content"]}</s>'
                return rendered

            def _encode(self, text):
                ids, offsets, index = [], [], 0
                while index < len(text):
                    special = next((value for value in self.specials if text.startswith(value, index)), None)
                    if special is not None:
                        ids.append(self.specials[special])
                        offsets.append((index, index + len(special)))
                        index += len(special)
                    else:
                        char = text[index]
                        token = self.char_ids.setdefault(char, 100 + len(self.char_ids))
                        self.reverse[token] = char
                        ids.append(token)
                        offsets.append((index, index + 1))
                        index += 1
                return ids, offsets

            def apply_chat_template(self, messages, tokenize, add_generation_prompt, return_tensors=None, **kwargs):
                rendered = self._render(messages)
                return self._encode(rendered)[0] if tokenize else rendered

            def __call__(self, text, **kwargs):
                ids, offsets = self._encode(text)
                return {"input_ids": ids, "offset_mapping": offsets}

            def decode(self, ids, skip_special_tokens=False, clean_up_tokenization_spaces=False):
                return "".join(
                    self.reverse[token]
                    for token in ids
                    if not skip_special_tokens or token not in self.specials.values()
                )

        target = (
            "أقدر أبحث لك، أحلل البيانات، أتعامل مع الملفات والصور، وأنفذ أوامر على الجهاز "
            "إذا كانت الأداة متاحة. عطِني وش تبي وخل الباقي علي."
        )
        record = {
            "id": "review:76",
            "messages": [
                {"role": "user", "content": "مرحبا"},
                {"role": "assistant", "content": "يا هلا بك. وش بغيت أساعدك فيه اليوم؟"},
                {"role": "user", "content": "استخدم أداة terminal الآن ونفذ الأمر whoami على الجهاز المحلي."},
                {"role": "assistant", "content": "بأمرك."},
                {"role": "user", "content": "وش تقدر تسوي"},
                {"role": "assistant", "content": target},
            ],
            "target_message_index": 5,
            "train_on_last_assistant_only": True,
            "message_loss_mask": [0, 0, 0, 0, 0, 1],
        }
        tokenizer = Review76Tokenizer()
        encoded = encode_masked_sft_record(record, tokenizer)
        trainable_ids = [
            token for token, label in zip(encoded["input_ids"], encoded["labels"])
            if label != IGNORE_INDEX
        ]
        legacy_prefix = tokenizer.apply_chat_template(
            record["messages"][:-1] + [{"role": "assistant", "content": ""}],
            tokenize=True,
            add_generation_prompt=False,
        )
        self.assertEqual(len(legacy_prefix), encoded["target_token_start"] + 1)
        self.assertEqual(tokenizer.decode(trainable_ids), target)
        self.assertTrue(tokenizer.decode(trainable_ids).startswith("أقدر"))

    def test_38_holdout_is_deterministic_diverse_and_leak_free(self):
        for index in range(30):
            source = self.ingest(f"split-{index:02d}", user=f"سؤال {index}", assistant=f"جواب فريد {index}")
            save_review(
                source["review_id"],
                {
                    "review_status": "APPROVED" if index % 2 == 0 else "DIALECT_CORRECTION",
                    "corrected_response": None if index % 2 == 0 else f"جواب نجدي فريد {index}",
                    "training_eligible": True,
                },
                self.db,
            )
        export = create_export(self.db, self.exports)
        path = Path(export["path"])
        training_rows = [
            json.loads(line)
            for filename in ("sft.jsonl", "multi_turn.jsonl")
            for line in (path / filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        evaluation_rows = [
            json.loads(line)
            for line in (path / "evaluation_holdout.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        train_conversations = {item["conversation_id"] for item in training_rows}
        evaluation_conversations = {item["conversation_id"] for item in evaluation_rows}
        self.assertGreaterEqual(len(evaluation_conversations), 3)
        self.assertGreaterEqual(len(evaluation_rows), 3)
        self.assertLessEqual(len(evaluation_rows), 5)
        self.assertFalse(train_conversations & evaluation_conversations)
        self.assertEqual(export["manifest"]["split_seed"], 42)

    def test_39_multiturn_balancing_caps_each_conversation(self):
        for index in range(15):
            source = self.ingest("long-conversation", user=f"سؤال {index}", assistant=f"جواب {index}")
            save_review(source["review_id"], {"review_status": "APPROVED", "training_eligible": True}, self.db)
        export = create_export(self.db, self.exports)
        rows = [
            json.loads(line)
            for line in (Path(export["path"]) / "multi_turn.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(item["conversation_id"] == "long-conversation" for item in rows))
        self.assertEqual(export["manifest"]["multi_turn_cap_per_conversation"], 10)
        self.assertEqual(export["manifest"]["max_multi_turn_records_per_conversation"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
