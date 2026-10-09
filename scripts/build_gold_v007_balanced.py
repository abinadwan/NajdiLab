from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_SFT = 16
EXPECTED_MULTI = 17
PHRASES = ("أبشر", "يا هلا", "يا مرحبا", "الله يحييك", "وش عندك", "وش بغيت", "ولا تهون")
PROTECTED_EXPORTS = ("gold-v004", "gold-v005-clean", "gold-v006-clean")
SEPARATE_EVAL_FILES = ("tool_eval.jsonl", "vision_eval.jsonl", "runtime_agent_eval.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hash(path: Path) -> tuple[str, dict[str, str]]:
    files = {p.relative_to(path).as_posix(): sha256(p) for p in sorted(path.rglob("*")) if p.is_file()}
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest(), files


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text.strip()).casefold()


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text or "", flags=re.UNICODE)


def target_of(row: dict[str, Any]) -> str:
    messages = row.get("messages") or []
    index = row.get("target_message_index")
    if not isinstance(index, int) or not 0 <= index < len(messages):
        raise ValueError(f"{row.get('id')}: invalid target_message_index")
    if messages[index].get("role") != "assistant":
        raise ValueError(f"{row.get('id')}: target is not assistant")
    return str(messages[index].get("content") or "")


def validate_mask_metadata(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        messages = row.get("messages") or []
        index = row.get("target_message_index")
        if not isinstance(index, int) or not 0 <= index < len(messages):
            raise ValueError(f"{row.get('id')}: invalid target_message_index")
        if messages[index].get("role") != "assistant":
            raise ValueError(f"{row.get('id')}: target is not assistant")
        if row.get("train_on_last_assistant_only") is not True:
            raise ValueError(f"{row.get('id')}: train_on_last_assistant_only is not true")
        mask = row.get("message_loss_mask")
        if not isinstance(mask, list) or len(mask) != len(messages):
            raise ValueError(f"{row.get('id')}: invalid message_loss_mask length")
        if sum(int(value) for value in mask) != 1 or int(mask[index]) != 1:
            raise ValueError(f"{row.get('id')}: mask does not select exactly the target")
        if any(messages[i].get("role") == "assistant" and i > index for i in range(len(messages))):
            raise ValueError(f"{row.get('id')}: assistant message follows target")


def conversation_key(row: dict[str, Any]) -> str:
    cid = row.get("conversation_id")
    return str(cid) if cid is not None else f"manual:{row.get('id')}"


def context_set(row: dict[str, Any]) -> set[str]:
    index = row["target_message_index"]
    result = set()
    for message in row["messages"][:index]:
        role = str(message.get("role") or "")
        content = normalize_text(str(message.get("content") or ""))
        result.add(f"{role}\n{content}")
    return result


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def pairwise_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sets = [context_set(row) for row in rows]
    values = [jaccard(sets[i], sets[j]) for i in range(len(sets)) for j in range(i + 1, len(sets))]
    nested = sum(1 for i in range(len(sets)) for j in range(i + 1, len(sets)) if sets[i] <= sets[j] or sets[j] <= sets[i])
    pairs = len(values)
    return {
        "windows": len(rows),
        "mean_jaccard": sum(values) / pairs if pairs else 0.0,
        "max_jaccard": max(values) if values else 0.0,
        "nested_ratio": nested / pairs if pairs else 0.0,
        "nested_pairs": nested,
        "pair_count": pairs,
    }


def target_groups(rows: list[dict[str, Any]], normalizer) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[normalizer(target_of(row))].append(row)
    return [group for group in groups.values() if len(group) > 1]


def train_metrics(sft: list[dict[str, Any]], multi: list[dict[str, Any]]) -> dict[str, Any]:
    train = [(row, "single-turn") for row in sft] + [(row, "multi-turn") for row in multi]
    conv: dict[str, dict[str, Any]] = defaultdict(lambda: {"total_records": 0, "single_turn_count": 0, "multi_turn_count": 0, "target_words": 0, "context_words": 0, "ids": []})
    all_target_words = 0
    all_context_words = 0
    for row, kind in train:
        key = conversation_key(row)
        target = target_of(row)
        context = " ".join(str(m.get("content") or "") for m in row["messages"][: row["target_message_index"]])
        item = conv[key]
        item["total_records"] += 1
        item["single_turn_count"] += int(kind == "single-turn")
        item["multi_turn_count"] += int(kind == "multi-turn")
        item["target_words"] += len(words(target))
        item["context_words"] += len(words(context))
        item["ids"].append(row["id"])
        all_target_words += len(words(target))
        all_context_words += len(words(context))
    total = len(train)
    conversations = {}
    for key, item in sorted(conv.items()):
        conversations[key] = {
            **item,
            "record_share": item["total_records"] / total if total else 0.0,
            "target_word_share": item["target_words"] / all_target_words if all_target_words else 0.0,
            "context_word_share": item["context_words"] / all_context_words if all_context_words else 0.0,
        }
    over_15 = [
        {"conversation_key": key, **value}
        for key, value in conversations.items()
        if value["record_share"] > 0.15 or value["target_word_share"] > 0.15
    ]
    return {
        "total_records": total,
        "total_target_words": all_target_words,
        "total_context_words": all_context_words,
        "conversation_count": len(conversations),
        "conversations": conversations,
        "over_15_percent": over_15,
        "highest_record_share": max(conversations.items(), key=lambda x: x[1]["record_share"]) if conversations else None,
        "highest_target_word_share": max(conversations.items(), key=lambda x: x[1]["target_word_share"]) if conversations else None,
        "highest_context_word_share": max(conversations.items(), key=lambda x: x[1]["context_word_share"]) if conversations else None,
    }


def target_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = [target_of(row) for row in rows]
    exact = target_groups(rows, lambda x: x)
    normalized = target_groups(rows, normalize_text)
    near = []
    for i, left in enumerate(targets):
        for j in range(i + 1, len(targets)):
            right = targets[j]
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio >= 0.90:
                near.append({"left_id": rows[i]["id"], "right_id": rows[j]["id"], "ratio": ratio})
    counts = [len(words(target)) for target in targets]
    total_words = sum(counts)
    longest_indices = sorted(range(len(rows)), key=lambda i: (-counts[i], rows[i]["id"]))[:10]
    return {
        "record_count": len(rows),
        "unique_targets": len(set(targets)),
        "exact_duplicate_groups": len(exact),
        "exact_duplicate_records_extra": sum(len(group) - 1 for group in exact),
        "normalized_duplicate_groups": len(normalized),
        "normalized_duplicate_records_extra": sum(len(group) - 1 for group in normalized),
        "near_duplicate_pairs_gte_0_90": len(near),
        "near_duplicate_pairs": near,
        "phrase_counts": {phrase: sum(phrase in target for target in targets) for phrase in PHRASES},
        "longest_10_ids": [rows[i]["id"] for i in longest_indices],
        "longest_10_target_word_share": sum(counts[i] for i in longest_indices) / total_words if total_words else 0.0,
    }


def multi_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[conversation_key(row)].append(row)
    per_conv = {key: pairwise_metrics(value) for key, value in sorted(grouped.items())}
    def highest(field: str) -> dict[str, Any] | None:
        if not per_conv:
            return None
        key, metrics = max(per_conv.items(), key=lambda item: (item[1][field], item[1]["windows"], item[0]))
        return {"conversation_key": key, **metrics}
    return {"conversation_count": len(grouped), "per_conversation": per_conv, "highest_mean_jaccard": highest("mean_jaccard"), "highest_max_jaccard": highest("max_jaccard"), "highest_nested_ratio": highest("nested_ratio")}


def copy_required(src: Path, dst: Path, name: str) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    shutil.copyfile(src, dst)


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    src = root / "exports" / "gold-v006-clean"
    selected = root / "reports" / "v007-selected-multiturn.jsonl"
    separate = root / "reports" / "eval-v006-clean"
    destination = root / "exports" / "gold-v007-balanced"
    if destination.exists() and not args.replace_existing:
        raise FileExistsError(f"{destination} exists; pass --replace-existing to rebuild this generated package")
    sft = read_jsonl(src / "sft.jsonl")
    multi = read_jsonl(selected)
    evaluation = read_jsonl(src / "text_sft_eval.jsonl")
    if len(sft) != EXPECTED_SFT or len(multi) != EXPECTED_MULTI:
        raise ValueError(f"expected {EXPECTED_SFT} sft + {EXPECTED_MULTI} multi-turn, got {len(sft)} + {len(multi)}")
    validate_mask_metadata(sft + multi)
    if len({row["id"] for row in sft + multi}) != len(sft) + len(multi):
        raise ValueError("duplicate training record ids")
    train_targets = {target_of(row) for row in sft + multi}
    eval_targets = {target_of(row) for row in evaluation}
    train_conversations = {conversation_key(row) for row in sft + multi}
    eval_conversations = {conversation_key(row) for row in evaluation}
    overlap = train_conversations & eval_conversations
    target_overlap = train_targets & eval_targets

    protected_before = {name: tree_hash(root / "exports" / name) for name in PROTECTED_EXPORTS}
    db_path = root / "data" / "najdilab.db"
    db_before = sha256(db_path)
    staging = Path(tempfile.mkdtemp(prefix=".gold-v007-balanced-", dir=str(root / "exports")))
    try:
        write_jsonl(staging / "sft.jsonl", sft)
        write_jsonl(staging / "multi_turn.jsonl", multi)
        copy_required(src / "direct_language.jsonl", staging / "direct_language.jsonl", "direct_language.jsonl")
        copy_required(src / "preference_pairs.jsonl", staging / "preference_pairs.jsonl", "preference_pairs.jsonl")
        copy_required(src / "text_sft_eval.jsonl", staging / "text_sft_eval.jsonl", "text_sft_eval.jsonl")
        for name in SEPARATE_EVAL_FILES:
            copy_required(separate / name, staging / name, name)
        metrics = train_metrics(sft, multi)
        target_stats = target_metrics(sft + multi)
        multi_stats = multi_metrics(multi)
        balance_report = {
            "version": "gold-v007-balanced",
            "source": {"single_turn": str(src / "sft.jsonl"), "selected_multi_turn": str(selected)},
            "counts": {"sft": len(sft), "multi_turn": len(multi), "total_train": len(sft) + len(multi), "evaluation": len(evaluation)},
            "conversation_balance": metrics,
            "target_analysis": target_stats,
            "multi_turn_overlap": multi_stats,
            "train_eval_checks": {"conversation_overlap_count": len(overlap), "exact_target_overlap_count": len(target_overlap), "conversation_overlap": sorted(overlap), "exact_target_overlap": sorted(target_overlap)},
            "separate_evaluation_files": {name: len(read_jsonl(staging / name)) for name in SEPARATE_EVAL_FILES},
            "sft_exclusions": ["direct_language.jsonl", "preference_pairs.jsonl", "text_sft_eval.jsonl", *SEPARATE_EVAL_FILES],
        }
        write_json(staging / "balancing_report.json", balance_report)
        manifest = {
            "version": "gold-v007-balanced",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_version": "gold-v006-clean + reports/v007-selected-multiturn.jsonl",
            "database_modified": False,
            "reviewed_gold_responses_modified": False,
            "training_started": False,
            "merge_started": False,
            "gguf_started": False,
            "ollama_started": False,
            "files": {name: len(read_jsonl(staging / name)) for name in ("sft.jsonl", "multi_turn.jsonl", "direct_language.jsonl", "preference_pairs.jsonl", "text_sft_eval.jsonl", *SEPARATE_EVAL_FILES)},
            "training_files": ["sft.jsonl", "multi_turn.jsonl"],
            "non_training_files": ["direct_language.jsonl", "preference_pairs.jsonl", "text_sft_eval.jsonl", *SEPARATE_EVAL_FILES],
            "loss_mask": "tokenizer validation required for every sft and selected multi-turn record",
            "train_eval_conversation_overlap": len(overlap),
            "exact_target_overlap": len(target_overlap),
            "protected_hashes_before": {name: digest for name, (digest, _) in protected_before.items()},
        }
        write_json(staging / "manifest.json", manifest)
        if destination.exists():
            backup = root / "reports" / ("gold-v007-balanced-previous-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            shutil.move(str(destination), str(backup))
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # Run the canonical tokenizer-based validator over the newly built package.
    model = args.model
    validator = root / "scripts" / "validate_training_masks.py"
    validation = subprocess.run([sys.executable, str(validator), "--export-dir", str(destination), "--model", model], capture_output=True, text=True)
    if validation.stdout.strip():
        try:
            loss_validation = json.loads(validation.stdout)
        except json.JSONDecodeError:
            loss_validation = {"raw_stdout": validation.stdout, "returncode": validation.returncode}
    else:
        loss_validation = {"raw_stderr": validation.stderr, "returncode": validation.returncode}
    write_json(destination / "loss-mask-validation.json", loss_validation)
    if validation.returncode != 0 or loss_validation.get("passed") != len(sft) + len(multi):
        raise RuntimeError(f"tokenizer loss-mask validation failed: {loss_validation}")

    protected_after = {name: tree_hash(root / "exports" / name) for name in PROTECTED_EXPORTS}
    db_after = sha256(db_path)
    audit = {
        "database_sha256_before": db_before,
        "database_sha256_after": db_after,
        "database_unchanged": db_before == db_after,
        "protected_exports": {name: {"before": protected_before[name][0], "after": protected_after[name][0], "unchanged": protected_before[name][0] == protected_after[name][0]} for name in PROTECTED_EXPORTS},
        "loss_mask_validation": loss_validation,
    }
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    manifest["database_unchanged"] = audit["database_unchanged"]
    manifest["protected_exports_unchanged"] = all(item["unchanged"] for item in audit["protected_exports"].values())
    manifest["loss_mask_validation"] = {"passed": loss_validation.get("passed"), "total": loss_validation.get("total"), "failures": loss_validation.get("failures", [])}
    write_json(destination / "manifest.json", manifest)
    return {"balance_report": json.loads((destination / "balancing_report.json").read_text(encoding="utf-8")), "audit": audit}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--model", default="/home/najdi/najdi-training/models/Ministral-3-3B-Instruct-2512-unsloth-bnb-4bit")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    result = build(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
