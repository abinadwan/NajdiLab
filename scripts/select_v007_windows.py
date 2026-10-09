"""Deterministically select a low-overlap multi-turn subset for v007.

This script only reads the source JSONL and writes a report plus a selected
JSONL. It never changes source records, the database, or any Gold content.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Any


EXPECTED_RECORDS = 43
MAX_NESTED_SELECTION = 3
MAX_NON_NESTED_SELECTION = 4


def normalize_content(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            row["_source_line"] = line_number
            rows.append(row)
    return rows


def validate_records(rows: list[dict[str, Any]]) -> None:
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"expected {EXPECTED_RECORDS} records, found {len(rows)}")
    for row in rows:
        record_id = str(row.get("id"))
        messages = row.get("messages")
        target_index = row.get("target_message_index")
        mask = row.get("message_loss_mask")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"{record_id}: messages must be a non-empty list")
        if not isinstance(target_index, int) or not 0 <= target_index < len(messages):
            raise ValueError(f"{record_id}: target_message_index out of bounds")
        if not isinstance(messages[target_index], dict) or messages[target_index].get("role") != "assistant":
            raise ValueError(f"{record_id}: target is not an assistant")
        if not isinstance(mask, list) or len(mask) != len(messages):
            raise ValueError(f"{record_id}: invalid message_loss_mask length")
        if mask[target_index] != 1 or sum(value == 1 for value in mask) != 1:
            raise ValueError(f"{record_id}: target mask must contain exactly one 1")


def conversation_key(row: dict[str, Any]) -> str:
    value = row.get("conversation_id")
    return str(value) if value is not None else f"manual:{row['id']}"


def prior_identity_set(row: dict[str, Any]) -> set[str]:
    target_index = int(row["target_message_index"])
    return {
        f"{message.get('role')}\n{normalize_content(message.get('content'))}"
        for message in row["messages"][:target_index]
    }


def context_word_count(row: dict[str, Any]) -> int:
    target_index = int(row["target_message_index"])
    return sum(
        len(re.findall(r"\S+", str(message.get("content") or "")))
        for message in row["messages"][:target_index]
    )


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def pairwise_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    values = [item["context_set"] for item in items]
    pairs = [jaccard(left, right) for left, right in combinations(values, 2)]
    nested = [
        left < right or right < left
        for left, right in combinations(values, 2)
    ]
    return {
        "mean_jaccard": sum(pairs) / len(pairs) if pairs else 0.0,
        "median_jaccard": median(pairs) if pairs else 0.0,
        "max_jaccard": max(pairs, default=0.0),
        "nested_pair_ratio": sum(nested) / len(nested) if nested else 0.0,
        "pairwise_jaccard": [
            {
                "left_id": left["id"],
                "right_id": right["id"],
                "jaccard": jaccard(left["context_set"], right["context_set"]),
            }
            for left, right in combinations(items, 2)
        ],
    }


def distinct_target(item: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    return item["target"] not in {entry["target"] for entry in selected}


def choose_shortest(items: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in items if distinct_target(item, selected)]
    return min(candidates, key=lambda item: (len(item["context_set"]), item["id"])) if candidates else None


def choose_longest(items: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in items if distinct_target(item, selected)]
    return min(candidates, key=lambda item: (-len(item["context_set"]), item["id"])) if candidates else None


def choose_low_overlap(items: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in items if distinct_target(item, selected)]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            sum(jaccard(item["context_set"], other["context_set"]) for other in selected)
            / len(selected),
            item["id"],
        ),
    )


def select_group(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    ordered = sorted(items, key=lambda item: item["id"])
    unique_targets = len({item["target"] for item in ordered})
    if len(ordered) <= 4:
        selected: list[dict[str, Any]] = []
        for item in sorted(items, key=lambda entry: entry["_source_line"]):
            if distinct_target(item, selected):
                selected.append(item)
        return selected, "keep_all_up_to_four_deduplicate_targets"

    before = pairwise_metrics(ordered)
    selected = []
    shortest = choose_shortest(ordered, selected)
    if shortest:
        selected.append(shortest)
    longest = choose_longest(ordered, selected)
    if longest:
        selected.append(longest)

    if before["nested_pair_ratio"] >= 0.80:
        extra = choose_low_overlap(ordered, selected)
        if extra:
            selected.append(extra)
        rule = "nested_cap_3"
    else:
        third = choose_low_overlap(ordered, selected)
        if third:
            selected.append(third)
        fourth = choose_low_overlap(ordered, selected)
        if fourth:
            selected.append(fourth)
        rule = "non_nested_cap_4"

    if len({item["target"] for item in selected}) != len(selected):
        raise ValueError("selection produced duplicate final targets")
    if unique_targets and len(selected) > unique_targets:
        raise ValueError("selection exceeded unique target count")
    return sorted(selected, key=lambda item: item["_source_line"]), rule


def target_preview(text: str, limit: int = 240) -> str:
    text = str(text).replace("\r", "").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def strip_internal(row: dict[str, Any]) -> dict[str, Any]:
    internal_keys = {"conversation_key", "context_set", "target"}
    return {
        key: value
        for key, value in row.items()
        if not key.startswith("_") and key not in internal_keys
    }


def build_report(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_line, row in enumerate(rows, start=1):
        row.setdefault("_source_line", source_line)
        row["conversation_key"] = conversation_key(row)
        row["context_set"] = prior_identity_set(row)
        row["target"] = str(row["messages"][row["target_message_index"]]["content"])
        groups[row["conversation_key"]].append(row)

    selected_rows: list[dict[str, Any]] = []
    conversation_reports = []
    for key in sorted(groups):
        group = groups[key]
        selected, rule = select_group(group)
        selected_rows.extend(selected)
        before = pairwise_metrics(group)
        after = pairwise_metrics(selected)
        selected_ids = {item["id"] for item in selected}
        conversation_reports.append(
            {
                "conversation_id": key,
                "windows_before": len(group),
                "windows_after": len(selected),
                "selection_rule": rule,
                "nested_pair_ratio_before": before["nested_pair_ratio"],
                "nested_pair_ratio_after": after["nested_pair_ratio"],
                "mean_jaccard_before": before["mean_jaccard"],
                "mean_jaccard_after": after["mean_jaccard"],
                "median_jaccard_before": before["median_jaccard"],
                "median_jaccard_after": after["median_jaccard"],
                "max_jaccard_before": before["max_jaccard"],
                "max_jaccard_after": after["max_jaccard"],
                "selected_ids": [item["id"] for item in selected],
                "dropped_ids": [item["id"] for item in group if item["id"] not in selected_ids],
                "target_ids_text_previews": [
                    {"id": item["id"], "target_preview": target_preview(item["target"])}
                    for item in selected
                ],
                "context_message_count": {
                    item["id"]: int(item["target_message_index"]) for item in selected
                },
                "context_word_count": {
                    item["id"]: context_word_count(item) for item in selected
                },
                "pairwise_jaccard_selected": after["pairwise_jaccard"],
            }
        )

    selected_rows = sorted(selected_rows, key=lambda item: item["_source_line"])
    selected_targets = [item["target"] for item in selected_rows]
    after_metrics = [pairwise_metrics([item for item in groups[key] if item["id"] in {row["id"] for row in selected_rows}]) for key in groups]
    summary = {
        "multi_turn_before": len(rows),
        "multi_turn_after": len(selected_rows),
        "conversations": len(groups),
        "unique_targets_after": len(set(selected_targets)),
        "exact_duplicates_after": len(selected_targets) - len(set(selected_targets)),
        "highest_mean_jaccard_after": max((report["mean_jaccard_after"] for report in conversation_reports), default=0.0),
        "highest_max_jaccard_after": max((report["max_jaccard_after"] for report in conversation_reports), default=0.0),
        "highest_nested_ratio_after": max((report["nested_pair_ratio_after"] for report in conversation_reports), default=0.0),
    }
    report = {
        "version": "v007-window-selection",
        "deterministic": True,
        "normalization": "strip; CRLF/CR to LF; collapse whitespace",
        "source_record_count": len(rows),
        "summary": summary,
        "conversations": conversation_reports,
    }
    return [strip_internal(row) for row in selected_rows], report


def main() -> None:
    parser = argparse.ArgumentParser(description="Select deterministic low-overlap multi-turn windows")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "exports" / "gold-v006-clean" / "multi_turn.jsonl",
    )
    parser.add_argument(
        "--selected-output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports" / "v007-selected-multiturn.jsonl",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports" / "v007-selection-report.json",
    )
    args = parser.parse_args()
    rows = read_jsonl(args.source)
    validate_records(rows)
    selected, report = build_report(rows)
    args.selected_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    with args.selected_output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    args.report_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
