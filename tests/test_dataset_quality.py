import json

from app.dataset_quality import analyze_directory, validate_candidate_release


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
