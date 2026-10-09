from __future__ import annotations

import copy

from scripts.select_v007_windows import build_report, strip_internal, validate_records


def row(record_id: str, conversation_id: str | None, prior_count: int, target: str) -> dict:
    messages = []
    for index in range(prior_count):
        messages.extend(
            [
                {"role": "user", "content": f"context-{record_id}-{index}"},
                {"role": "assistant", "content": f"reply-{record_id}-{index}"},
            ]
        )
    messages.extend([{"role": "user", "content": f"final-{record_id}"}, {"role": "assistant", "content": target}])
    return {
        "id": record_id,
        "conversation_id": conversation_id,
        "messages": messages,
        "target_message_index": len(messages) - 1,
        "message_loss_mask": [0] * (len(messages) - 1) + [1],
    }


def nested_row(record_id: str, prior_count: int, target: str) -> dict:
    messages = []
    for index in range(prior_count):
        messages.extend(
            [
                {"role": "user", "content": f"shared-{index}"},
                {"role": "assistant", "content": f"reply-{index}"},
            ]
        )
    messages.extend([{"role": "user", "content": "final"}, {"role": "assistant", "content": target}])
    return {
        "id": record_id,
        "conversation_id": "nested-conversation",
        "messages": messages,
        "target_message_index": len(messages) - 1,
        "message_loss_mask": [0] * (len(messages) - 1) + [1],
    }


def test_manual_none_conversation_is_scoped_as_manual_key() -> None:
    selected, report = build_report([row("manual_sft_items:3", None, 1, "manual-target")])
    assert report["conversations"][0]["conversation_id"] == "manual:manual_sft_items:3"
    assert selected[0]["conversation_id"] is None


def test_nested_conversation_is_capped_at_three_and_keeps_shortest_longest() -> None:
    rows = [nested_row(f"review:{index}", index, f"target-{index}") for index in range(1, 6)]
    selected, report = build_report(rows)
    assert len(selected) == 3
    assert len(selected[0]["messages"]) == 4
    assert len(selected[-1]["messages"]) == 12
    assert "review:1" in {item["id"] for item in selected}
    assert "review:5" in {item["id"] for item in selected}
    assert report["conversations"][0]["selection_rule"] == "nested_cap_3"


def test_non_nested_large_conversation_is_capped_at_four() -> None:
    rows = [row(f"review:{index}", "non-nested", 1, f"target-{index}") for index in range(1, 6)]
    selected, report = build_report(rows)
    assert len(selected) == 4
    assert report["conversations"][0]["selection_rule"] == "non_nested_cap_4"


def test_selection_is_deterministic_and_deduplicates_targets() -> None:
    rows = [
        row("review:b", "small", 1, "same-target"),
        row("review:a", "small", 2, "same-target"),
        row("review:c", "small", 3, "different-target"),
    ]
    first, first_report = build_report(copy.deepcopy(rows))
    second, second_report = build_report(copy.deepcopy(rows))
    assert first == second
    assert first_report == second_report
    assert [item["id"] for item in first] == ["review:b", "review:c"]
    assert first_report["summary"]["exact_duplicates_after"] == 0


def test_source_records_and_masks_are_not_changed() -> None:
    rows = [row("review:1", "conversation", 2, "target")]
    original = copy.deepcopy(rows)
    validate_records([row(f"review:{index}", "conversation", 2, f"target-{index}") for index in range(43)])
    selected, _ = build_report(rows)
    assert strip_internal(rows[0]) == selected[0]
    assert selected[0]["target_message_index"] == original[0]["target_message_index"]
    assert selected[0]["message_loss_mask"] == original[0]["message_loss_mask"]


def test_validation_rejects_multiple_trainable_messages() -> None:
    invalid = row("review:bad", "conversation", 1, "target")
    invalid["message_loss_mask"][0] = 1
    try:
        validate_records([invalid] + [row(f"review:{index}", "conversation", 1, f"target-{index}") for index in range(42)])
    except ValueError as exc:
        assert "exactly one 1" in str(exc)
    else:
        raise AssertionError("invalid mask was accepted")
