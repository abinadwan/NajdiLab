from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from scripts.train_najdi_sft import IGNORE_INDEX, encode_masked_sft_record
except ModuleNotFoundError:
    from train_najdi_sft import IGNORE_INDEX, encode_masked_sft_record


def _rows(export_dir: Path) -> list[tuple[str, int, dict[str, Any]]]:
    rows = []
    for filename in ("sft.jsonl", "multi_turn.jsonl"):
        with (export_dir / filename).open(encoding="utf-8") as handle:
            rows.extend(
                (filename, line_number, json.loads(line))
                for line_number, line in enumerate(handle, start=1)
                if line.strip()
            )
    return rows


def _piece(tokenizer: Any, index: int, token_id: int) -> dict[str, Any]:
    return {
        "index": index,
        "token_id": token_id,
        "token_piece": tokenizer.convert_ids_to_tokens(token_id),
        "decoded_piece": tokenizer.decode(
            [token_id], skip_special_tokens=False, clean_up_tokenization_spaces=False
        ),
    }


def validate(export_dir: Path, tokenizer: Any, review_id: str) -> dict[str, Any]:
    rows = _rows(export_dir)
    failures = []
    detail = None
    passed = 0
    for filename, line_number, row in rows:
        try:
            encoded = encode_masked_sft_record(row, tokenizer)
            active = [
                index for index, label in enumerate(encoded["labels"])
                if label != IGNORE_INDEX
            ]
            expected = row["messages"][row["target_message_index"]]["content"]
            actual = tokenizer.decode(
                [encoded["input_ids"][index] for index in active],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            expected_positions = list(range(encoded["target_token_start"], encoded["target_token_end"]))
            if active != expected_positions:
                raise AssertionError("trainable target tokens are not one exact contiguous span")
            if any(
                label != IGNORE_INDEX
                for index, label in enumerate(encoded["labels"])
                if index not in active
            ):
                raise AssertionError("context or previous assistant token is trainable")
            if actual != expected:
                raise AssertionError(f"decoded target mismatch: {actual!r} != {expected!r}")

            if row.get("id") == review_id:
                messages = row["messages"]
                legacy = tokenizer.apply_chat_template(
                    messages[:-1] + [{"role": "assistant", "content": ""}],
                    tokenize=True,
                    add_generation_prompt=False,
                    return_tensors=None,
                )
                legacy_ids = legacy["input_ids"] if isinstance(legacy, Mapping) else legacy
                correct_start = encoded["target_token_start"]
                detail = {
                    "record_id": review_id,
                    "current_legacy_start_index": len(legacy_ids),
                    "correct_start_index": correct_start,
                    "last_10_tokens_before_target": [
                        _piece(tokenizer, index, encoded["input_ids"][index])
                        for index in range(max(0, correct_start - 10), correct_start)
                    ],
                    "first_10_tokens_of_target": [
                        _piece(tokenizer, index, encoded["input_ids"][index])
                        for index in range(correct_start, min(correct_start + 10, len(encoded["input_ids"])))
                    ],
                    "trainable_text": actual,
                    "mask_strategy": encoded["mask_strategy"],
                }
            passed += 1
        except Exception as exc:
            failures.append({
                "file": filename,
                "line": line_number,
                "id": row.get("id"),
                "error": f"{type(exc).__name__}: {exc}",
            })

    if detail is None:
        failures.append({"id": review_id, "error": "diagnostic record not found"})
    return {
        "passed": passed,
        "total": len(rows),
        "failures": failures,
        "diagnostic": detail,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate exact final-assistant loss masks")
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--review-id", default="review:76")
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    result = validate(args.export_dir, tokenizer, args.review_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
