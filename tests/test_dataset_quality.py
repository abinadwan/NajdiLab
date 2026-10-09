import json

import pytest

from app.dataset_quality import analyze_directory, validate_candidate_release
from app.evaluation_guard import EvaluationGuardError, verify_adapter_evaluation


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")


def row(identifier, prompt, target, conversation, **extra):
    return {"id": identifier, "conversation_id": conversation, "source": "fixture",
            "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": target}],
            "target_message_index": 1, "message_loss_mask": [0, 1], **extra}


def test_quality_is_deterministic_and_finds_conflicts_leakage_and_structure(tmp_path):
    write_jsonl(tmp_path / "sft.jsonl", [row("a", "كيف الحال اليوم يا صاحبي", "تمام", "shared"), row("b", "كيف الحال اليوم يا صاحبي", "سيئ", "train-b")])
    write_jsonl(tmp_path / "multi_turn.jsonl", [{"id": "broken", "source": "fixture", "messages": []}])
    write_jsonl(tmp_path / "text_sft_eval.jsonl", [row("e", "سؤال تقييم مختلف كليا", "تمام", "shared")])
    first = analyze_directory(tmp_path)
    second = analyze_directory(tmp_path)
    assert first == second
    codes = {x["code"] for x in first["findings"]}
    assert {"CONTRADICTORY_TARGETS", "TRAIN_EVAL_CONVERSATION_LEAKAGE", "TRAIN_EVAL_TARGET_LEAKAGE", "MESSAGES_MISSING"} <= codes
    assert first["status"] == "BLOCKED"
    assert all(x["finding_id"].startswith("qf-") for x in first["findings"])


def test_candidate_release_fingerprint_is_reproducible_and_loss_mask_fails_closed(tmp_path):
    write_jsonl(tmp_path / "sft.jsonl", [row("a", "طلب صالح طويل بما يكفي", "جواب", "one")])
    write_jsonl(tmp_path / "multi_turn.jsonl", [row("b", "طلب ثان صالح طويل أيضا", "جواب آخر", "two")])
    a = validate_candidate_release(tmp_path, source_version="source", config={"seed": 42})
    b = validate_candidate_release(tmp_path, source_version="source", config={"seed": 42})
    assert a["release_fingerprint"] == b["release_fingerprint"]
    assert a["status"] == "VALID"
    rows = [row("a", "طلب صالح طويل بما يكفي", "جواب", "one")]
    rows[0]["message_loss_mask"] = [1, 1]
    write_jsonl(tmp_path / "sft.jsonl", rows)
    assert validate_candidate_release(tmp_path)["checks"]["response_only_loss_masks"] is False


def test_adapter_guard_rejects_silent_fallback_and_binds_configuration(tmp_path):
    adapter = tmp_path / "adapter"; adapter.mkdir()
    config = {"base_model_id": "base", "adapter_path": str(adapter), "adapter_revision": "r1", "dataset_version": "v1", "run_id": "run-1", "inference": {"temperature": 0}}
    with pytest.raises(EvaluationGuardError) as caught:
        verify_adapter_evaluation(config, {"adapter_active": False, "loaded_adapter_path": str(adapter)})
    assert caught.value.code == "ADAPTER_FALLBACK_DETECTED"
    verified = verify_adapter_evaluation(config, {"adapter_active": True, "loaded_adapter_path": str(adapter), "adapter_revision": "r1", "base_output_fingerprint": "a", "adapter_output_fingerprint": "b"})
    assert verified["status"] == "VERIFIED" and not verified["adapter_fallback"]
