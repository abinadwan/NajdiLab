from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.clean_export import (
    ACTIVE_MODEL_RE,
    ArchiveIndex,
    MULTI_TURN_CAP,
    annotate_sft,
    classify_evaluation,
    clean_runtime_text,
    sanitize_external_ids,
    reconstruct_review_record,
    validate_clean_records,
    _validate_written_jsonl,
    _write_jsonl,
)


def archive_fixture(*, prior_status: str = "FULL_CORRECTION", quote: bool = False) -> tuple[ArchiveIndex, dict]:
    prior_user = "السؤال الأول"
    prior_bad = "الرد القديم الخاطئ"
    second_user = "وش الصحيح؟"
    if quote:
        second_user = f'[Replying to your previous message: "{prior_bad}"]\n\nوش الصحيح؟'
    messages = [
        {"id": 1, "conversation_id": 1, "turn_index": 0, "role": "user", "content": prior_user},
        {"id": 2, "conversation_id": 1, "turn_index": 1, "role": "assistant", "content": prior_bad},
        {"id": 3, "conversation_id": 1, "turn_index": 2, "role": "user", "content": second_user},
        {"id": 4, "conversation_id": 1, "turn_index": 3, "role": "assistant", "content": "هدف أصلي"},
    ]
    prior_review = {
        "id": 10,
        "message_id": 2,
        "review_status": prior_status,
        "original_response": prior_bad,
        "corrected_response": "الرد الذهبي الصحيح" if prior_status != "APPROVED" else None,
        "training_eligible": 1,
        "evaluation_only": 0,
        "exclude_from_training": 0,
    }
    target_review = {
        "id": 11,
        "message_id": 4,
        "review_status": "CONTENT_CORRECTION",
        "original_response": "هدف أصلي",
        "corrected_response": "الهدف الذهبي النهائي",
        "training_eligible": 1,
        "evaluation_only": 0,
        "exclude_from_training": 0,
    }
    archive = {
        "conversations": [{
            "id": 1,
            "external_conversation_id": "conv-clean",
            "provider": "local",
            "model_name": "model",
            "model_version": None,
            "channel": "web",
            "demo": 0,
        }],
        "messages": messages,
        "reviews": [prior_review, target_review],
        "review_tags": [],
        "manual_sft_items": [],
        "direct_language_texts": [],
        "preference_pairs": [],
    }
    return ArchiveIndex(archive), target_review


class CleanExportTests(unittest.TestCase):
    def test_01_previous_corrected_assistant_uses_gold(self):
        index, target = archive_fixture()
        record, audit, error = reconstruct_review_record(index, target)
        self.assertIsNone(error)
        self.assertEqual(record["messages"][1]["content"], "الرد الذهبي الصحيح")
        self.assertNotIn("الرد القديم الخاطئ", json.dumps(record, ensure_ascii=False))
        self.assertEqual(audit.prior_assistant_gold_replacements, 1)

    def test_02_untrusted_previous_assistant_trims_context(self):
        index, target = archive_fixture(prior_status="PENDING")
        record, audit, error = reconstruct_review_record(index, target)
        self.assertIsNone(error)
        self.assertEqual([message["content"] for message in record["messages"]], [
            "وش الصحيح؟", "الهدف الذهبي النهائي"
        ])
        self.assertTrue(audit.context_trimmed)

    def test_03_embedded_reply_quote_uses_gold(self):
        index, target = archive_fixture(quote=True)
        record, audit, error = reconstruct_review_record(index, target)
        self.assertIsNone(error)
        user = record["messages"][-2]["content"]
        self.assertIn("الرد الذهبي الصحيح", user)
        self.assertNotIn("الرد القديم الخاطئ", user)
        self.assertEqual(audit.quoted_reply_replacements, 1)

    def test_04_gateway_metadata_removed_but_user_text_kept(self):
        text = (
            "وش درجة الحرارة الان\n\n"
            "User correction during the turn: Gateway message origin (JSON data, not instructions or authorization):\n"
            '{"platform":"whatsapp","chat_id":"1","user_id":"2","message_id":"3"}\n'
            "Do not guess a reply destination when these fields are insufficient.\n\nوقف"
        )
        cleaned, removed = clean_runtime_text(text)
        self.assertEqual(removed, 1)
        self.assertIn("وش درجة الحرارة الان", cleaned)
        self.assertIn("وقف", cleaned)
        self.assertNotIn("chat_id", cleaned)

    def test_05_active_model_runtime_block_removed(self):
        text = "[System: The active model for this chat is x via y.]\n\nوش عندك؟"
        cleaned, removed = clean_runtime_text(text)
        self.assertEqual(removed, 1)
        self.assertEqual(cleaned, "وش عندك؟")
        self.assertIsNotNone(ACTIVE_MODEL_RE)

    def test_06_target_gold_is_unchanged(self):
        index, target = archive_fixture()
        record, _, _ = reconstruct_review_record(index, target)
        self.assertEqual(record["messages"][-1]["content"], target["corrected_response"])

    def test_07_message_loss_mask_is_exact(self):
        record = annotate_sft({
            "id": "x",
            "messages": [
                {"role": "user", "content": "س"},
                {"role": "assistant", "content": "ج"},
            ],
        })
        self.assertEqual(record["target_message_index"], 1)
        self.assertTrue(record["train_on_last_assistant_only"])
        self.assertEqual(record["message_loss_mask"], [0, 1])

    def test_08_train_text_eval_conversation_overlap_rejected(self):
        index, target = archive_fixture()
        record, _, _ = reconstruct_review_record(index, target)
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate_clean_records(
                [record],
                [record],
                index,
                {"max_multi_turn_records_per_conversation_after": MULTI_TURN_CAP},
            )

    def test_09_tool_and_vision_are_not_text_sft(self):
        tool = annotate_sft({
            "id": "tool",
            "messages": [
                {"role": "user", "content": "نفذ الأمر whoami"},
                {"role": "assistant", "content": "أبشر"},
            ],
        })
        vision = annotate_sft({
            "id": "vision",
            "messages": [
                {"role": "user", "content": "[The user sent an image~] وش فيها؟"},
                {"role": "assistant", "content": "أحتاج الصورة"},
            ],
        })
        self.assertEqual(classify_evaluation(tool)[0], "tool")
        self.assertEqual(classify_evaluation(vision)[0], "vision")

    def test_10_jsonl_writer_produces_valid_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rows.jsonl"
            _write_jsonl(path, [{"id": "1"}, {"id": "2", "text": "نجدي"}])
            _validate_written_jsonl([path])
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["1", "2"])

    def test_11_markdown_variant_backfills_same_message_id(self):
        index, target = archive_fixture(quote=True)
        index.messages[2]["content"] = "**الرد القديم الخاطئ**"
        index.messages[3]["content"] = '[Replying to your previous message: "*الرد القديم الخاطئ*"]\n\nوش الصحيح؟'
        index.messages[3].pop("reply_to_message_id", None)
        index.messages[3].pop("reply_link_origin", None)
        index.backfill = index._backfill_reply_links()
        self.assertEqual(index.messages[3]["reply_to_message_id"], 2)
        record, _, error = reconstruct_review_record(index, target)
        self.assertIsNone(error)
        self.assertIn("الرد الذهبي الصحيح", record["messages"][-2]["content"])

    def test_12_reply_backfill_never_crosses_conversation(self):
        index, _ = archive_fixture()
        other = {"id": 5, "conversation_id": 2, "turn_index": 0, "role": "user", "content": '[Replying to your previous message: "الرد القديم الخاطئ"]\n\nس'}
        index.messages[5] = other
        index.messages_by_conversation[2] = [other]
        index._backfill_reply_links()
        self.assertNotIn("reply_to_message_id", other)

    def test_13_ambiguous_and_unmatched_quotes_are_removed(self):
        index, target = archive_fixture(quote=True)
        duplicate = {"id": 9, "conversation_id": 1, "turn_index": 1, "role": "assistant", "content": "الرد القديم الخاطئ"}
        index.messages[9] = duplicate
        index.messages_by_conversation[1].insert(2, duplicate)
        index.messages[3].pop("reply_to_message_id", None)
        index._backfill_reply_links()
        record, audit, error = reconstruct_review_record(index, target)
        self.assertIsNone(error)
        self.assertNotIn("Replying to", json.dumps(record, ensure_ascii=False))
        self.assertGreaterEqual(audit.reply_quotes_ambiguous, 1)

    def test_14_voice_runtime_block_removed(self):
        text = "[The user sent a voice message but it came through empty or inaudible — speech-to-text returned no words. Do not guess.]\n\nاكتب لي"
        cleaned, removed = clean_runtime_text(text)
        self.assertEqual(cleaned, "اكتب لي")
        self.assertEqual(removed, 1)

    def test_15_eval_external_id_sanitized_consistently(self):
        record = annotate_sft({"id": "e", "messages": [
            {"role": "user", "content": "كلم @122707282755638"},
            {"role": "assistant", "content": "تم ذكر @122707282755638"},
        ]})
        cleaned, count = sanitize_external_ids(record)
        self.assertEqual(count, 1)
        self.assertEqual(cleaned["messages"][0]["content"], "كلم @USER_1")
        self.assertEqual(cleaned["messages"][1]["content"], "تم ذكر @USER_1")


if __name__ == "__main__":
    unittest.main()
