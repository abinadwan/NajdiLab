"""End-to-end acceptance check for the passive Hermes -> NajdiLab v1.1 hook.

The conversations are synthetic and marked as demo data.  No external channel is used.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = PROJECT_ROOT.parent / "hermes-agent"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(HERMES_ROOT))

from agent import outbound_webhooks as webhooks  # noqa: E402
from app.db import DB_PATH, connect  # noqa: E402
from app.service import create_export, save_review  # noqa: E402


COLLECTOR_URL = "http://127.0.0.1:8770/api/v1/hermes-hook"
FIELDS = {
    "turn_id",
    "user_message",
    "assistant_response",
    "model",
    "provider",
    "platform",
    "conversation_key_hash",
    "system_prompt_version",
    "generation_settings",
    "acceptance_test",
}
SECRET_SENTINEL = "NAJDILAB_TEST_SECRET_DO_NOT_STORE"
RAW_PHONE_SENTINEL = "+966500000000"
RAW_TELEGRAM_SENTINEL = "telegram-id-998877"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event(conversation: int, turn: int, platform: str, user: str, assistant: str) -> dict:
    return {
        "session_id": f"acceptance-session-{conversation}",
        "turn_id": f"najdilab-v11-acceptance-c{conversation}-t{turn}",
        "user_message": user,
        "assistant_response": assistant,
        "model": "gemma4-hermes:latest",
        "provider": "ollama",
        "platform": platform,
        "conversation_key_hash": _hash(f"najdilab-v11-acceptance-conversation-{conversation}"),
        "system_prompt_version": f"sha256:{_hash('najdilab-v11-safe-system-prompt-version')}",
        "generation_settings": {"temperature": 0.4, "top_p": 0.9, "context_length": 8192},
        "acceptance_test": True,
        # These intentionally unsafe, non-allowlisted fields prove filtering at the Hermes boundary.
        "api_key": SECRET_SENTINEL,
        "raw_phone": RAW_PHONE_SENTINEL,
        "telegram_chat_id": RAW_TELEGRAM_SENTINEL,
        "conversation_history": [{"role": "tool", "content": SECRET_SENTINEL}],
    }


EVENTS = [
    _event(1, 1, "whatsapp", "السلام عليكم", "وعليكم السلام ورحمة الله وبركاته."),
    _event(2, 1, "telegram", "جاوب بكلمة واحدة فقط: نعم", "نعم"),
    _event(
        3,
        1,
        "api_server",
        "اختصر الجملة هذه بثلاث نقاط: التخطيط الجيد يوضح الأولويات ويوفر الوقت ويقلل النسيان.",
        "- يوضح الأولويات.\n- يوفر الوقت.\n- يقلل النسيان.",
    ),
    _event(4, 1, "whatsapp", "عندي موعد ثابت الساعة 7، لا تغيره.", "تم، موعد الساعة 7 ثابت."),
    _event(
        4,
        2,
        "whatsapp",
        "عندي مشوار للبنك والبقالة، رتبهم لي.",
        "رح للبنك أولًا، ثم البقالة، وخل موعد الساعة 7 كما هو.",
    ),
    _event(
        5,
        1,
        "desktop",
        "وش الفرق بين RAM وVRAM باختصار؟",
        "RAM ذاكرة عامة للنظام والبرامج، وVRAM ذاكرة مخصصة لمعالجة الرسوم على كرت الشاشة.",
    ),
]


def _rows() -> tuple[list[dict], list[dict]]:
    prefixes = tuple(
        f"hermes:default:{_hash(f'najdilab-v11-acceptance-conversation-{number}')}" for number in range(1, 6)
    )
    placeholders = ",".join("?" for _ in prefixes)
    conn = connect()
    try:
        conversations = [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM conversations WHERE external_conversation_id IN ({placeholders}) ORDER BY external_conversation_id",
                prefixes,
            )
        ]
        messages = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT m.*, c.external_conversation_id, c.channel, c.source, c.demo,
                       r.id AS review_id, r.review_status, r.training_eligible,
                       r.original_response, r.corrected_response
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN reviews r ON r.message_id = m.id
                WHERE c.external_conversation_id IN ({placeholders})
                ORDER BY c.external_conversation_id, m.turn_index
                """,
                prefixes,
            )
        ]
        return conversations, messages
    finally:
        conn.close()


def _assert_capture(conversations: list[dict], messages: list[dict]) -> None:
    assert len(conversations) == 5, f"expected 5 conversations, found {len(conversations)}"
    assert len(messages) == 12, f"expected 12 messages from 6 turns, found {len(messages)}"
    assistants = [row for row in messages if row["role"] == "assistant"]
    assert len(assistants) == 6
    assert all(row["source"] == "hermes" and row["demo"] == 1 for row in messages)
    assert all(row["review_status"] == "PENDING" and row["training_eligible"] == 0 for row in assistants)
    assert all(row["provider"] == "ollama" and row["model_name"] == "gemma4-hermes:latest" for row in messages)
    expected_channels = {"whatsapp", "telegram", "web", "private"}
    assert expected_channels.issubset({row["channel"] for row in conversations})
    multi_hash = _hash("najdilab-v11-acceptance-conversation-4")
    multi = [row for row in messages if row["external_conversation_id"].endswith(multi_hash)]
    assert len(multi) == 4 and [row["turn_index"] for row in multi] == [0, 1, 2, 3]
    database_bytes = Path(DB_PATH).read_bytes()
    for forbidden in (SECRET_SENTINEL, RAW_PHONE_SENTINEL, RAW_TELEGRAM_SENTINEL):
        assert forbidden.encode("utf-8") not in database_bytes


def main() -> None:
    target = webhooks.WebhookTarget(
        url=COLLECTOR_URL,
        events=["post_llm_call"],
        name="najdilab-v11-acceptance",
        timeout=1,
        fields=FIELDS,
    )
    callback = webhooks._make_callback("post_llm_call", target)

    # Measure synchronous hook overhead only.  Delivery remains a background worker operation.
    sample = EVENTS[0]
    original_enqueue = webhooks._enqueue
    webhooks._enqueue = lambda _delivery: None
    try:
        callback(**sample)  # warm imports and caches
        baseline_samples = []
        integrated_samples = []
        for _ in range(500):
            start = time.perf_counter_ns()
            (lambda **_kwargs: None)(**sample)
            baseline_samples.append((time.perf_counter_ns() - start) / 1_000_000)
            start = time.perf_counter_ns()
            callback(**sample)
            integrated_samples.append((time.perf_counter_ns() - start) / 1_000_000)
    finally:
        webhooks._enqueue = original_enqueue

    delivery_call_ms = []
    for event in EVENTS:
        start = time.perf_counter_ns()
        callback(**event)
        delivery_call_ms.append((time.perf_counter_ns() - start) / 1_000_000)
    assert webhooks.flush(10), "collector queue did not drain"

    conversations, messages = _rows()
    _assert_capture(conversations, messages)
    counts_before = (len(conversations), len(messages))
    callback(**EVENTS[0])
    assert webhooks.flush(10)
    duplicate_conversations, duplicate_messages = _rows()
    assert (len(duplicate_conversations), len(duplicate_messages)) == counts_before

    pending_assistants = [row for row in messages if row["role"] == "assistant"]
    by_turn = {row["source_message_id"]: row for row in pending_assistants}
    review_cases = {
        "najdilab-v11-acceptance-c1-t1": {
            "review_status": "APPROVED",
            "training_eligible": False,
            "review_notes": "NajdiLab v1.1 acceptance",
        },
        "najdilab-v11-acceptance-c2-t1": {
            "review_status": "DIALECT_CORRECTION",
            "corrected_response": "إيه",
            "tags": ["dialect_issue"],
            "training_eligible": False,
            "review_notes": "NajdiLab v1.1 acceptance",
        },
        "najdilab-v11-acceptance-c3-t1": {
            "review_status": "CONTENT_CORRECTION",
            "corrected_response": "- يحدد الأولويات.\n- يوفر الوقت.\n- يقلل النسيان.",
            "tags": ["factual_error"],
            "training_eligible": False,
            "review_notes": "NajdiLab v1.1 acceptance",
        },
        "najdilab-v11-acceptance-c4-t2": {
            "review_status": "FULL_CORRECTION",
            "corrected_response": "ابدأ بالبنك، وبعده البقالة، ثم توجّه لموعدك الثابت الساعة 7 بدون تغيير.",
            "tags": ["wrong_context"],
            "training_eligible": False,
            "review_notes": "NajdiLab v1.1 acceptance",
        },
    }
    original_responses = {turn_id: by_turn[turn_id]["original_response"] for turn_id in review_cases}
    reviewed = {}
    for turn_id, review_data in review_cases.items():
        reviewed[turn_id] = save_review(by_turn[turn_id]["review_id"], review_data)
    assert all(reviewed[key]["original_response"] == original_responses[key] for key in reviewed)
    assert reviewed["najdilab-v11-acceptance-c4-t2"]["context"][-2]["content"] == EVENTS[4]["user_message"]
    assert len(reviewed["najdilab-v11-acceptance-c4-t2"]["context"]) == 4

    selected_turn = "najdilab-v11-acceptance-c2-t1"
    selected_review_id = by_turn[selected_turn]["review_id"]
    selected = save_review(
        selected_review_id,
        {
            **review_cases[selected_turn],
            "training_eligible": True,
        },
    )
    export = create_export(
        include_demo=True,
        filters={
            "purpose": "NajdiLab v1.1 acceptance test only",
            "training_use": "prohibited",
            "selected_review_id": selected_review_id,
        },
    )
    export_path = Path(export["path"])
    manifest = json.loads((export_path / "manifest.json").read_text(encoding="utf-8"))
    for name, expected_sha in manifest["sha256"].items():
        assert hashlib.sha256((export_path / name).read_bytes()).hexdigest() == expected_sha
    assert not (export_path / "evaluation_holdout.jsonl").read_text(encoding="utf-8").strip()
    exported_records = []
    for filename in ("sft.jsonl", "multi_turn.jsonl"):
        exported_records.extend(
            json.loads(line)
            for line in (export_path / filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    exported_selected = next(item for item in exported_records if item["id"] == f"review:{selected_review_id}")
    assert exported_selected["messages"][-1]["content"] == selected["corrected_response"] == "إيه"
    assert len(exported_selected["messages"]) == 2
    # The exported artifact is retained as a test record; live eligibility is reset immediately.
    save_review(selected_review_id, {**review_cases[selected_turn], "training_eligible": False})

    failure_target = webhooks.WebhookTarget(
        url="http://127.0.0.1:1/api/v1/hermes-hook",
        events=["post_llm_call"],
        name="najdilab-v11-failure-test",
        timeout=1,
        fields=FIELDS,
    )
    failure_callback = webhooks._make_callback("post_llm_call", failure_target)
    start = time.perf_counter_ns()
    failure_callback(**_event(99, 1, "desktop", "اختبار فشل آمن", "استمر Hermes طبيعيًا."))
    failure_return_ms = (time.perf_counter_ns() - start) / 1_000_000
    hermes_continued = True  # reached immediately after the hook returned; delivery is still background work
    assert webhooks.flush(5), "failure-test queue did not settle"

    report = {
        "status": "PASS",
        "collector_url": COLLECTOR_URL,
        "conversations": 5,
        "turn_events": 6,
        "messages": 12,
        "pending_before_review": 6,
        "multi_turn_messages": 4,
        "duplicate_protection": "PASS",
        "privacy_secret_redaction": "PASS",
        "review_workflow": "PASS",
        "training_eligible_default_false": "PASS",
        "latency_ms": {
            "baseline_median": round(statistics.median(baseline_samples), 6),
            "integrated_hook_median": round(statistics.median(integrated_samples), 6),
            "acceptance_enqueue_median": round(statistics.median(delivery_call_ms), 6),
            "acceptance_enqueue_max": round(max(delivery_call_ms), 6),
        },
        "failure_test": {
            "callback_return_ms": round(failure_return_ms, 6),
            "hermes_continued": hermes_continued,
        },
        "gold_export": {
            "status": "PASS",
            "version": export["version"],
            "path": str(export_path),
            "record_count": manifest["record_count"],
            "selected_review_id": selected_review_id,
            "sha_verified": True,
            "evaluation_holdout_empty": True,
            "training_use": "prohibited",
        },
    }
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / "v1.1-acceptance.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
