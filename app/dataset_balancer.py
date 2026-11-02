from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from .dataset_platform import DatasetPlatformError, EVAL_FILES, NATIVE_TRAIN_FILE, _json, _normalized, _state, _version_dir, dataset_health

# File names come from dataset_platform so Health, Balancer, Quality and Unsloth export
# agree on which files a version may contain.
DATASET_FILES: dict[str, str] = {
    "sft.jsonl": "sft", "multi_turn.jsonl": "multi_turn",
    "preference_pairs.jsonl": "preference", "direct_language.jsonl": "direct_language",
    NATIVE_TRAIN_FILE: "native_tool_use",
    **dict.fromkeys(EVAL_FILES, "evaluation"),
}
MESSAGE_KINDS = {"sft", "multi_turn", "native_tool_use", "evaluation"}
LENGTH_BUCKETS = (("very_short", 0, 39), ("short", 40, 119), ("medium", 120, 399), ("long", 400, 999), ("very_long", 1000, None))
BALANCE_RULES = {
    "multi_turn_share": {"recommended_min": 0.30, "recommended_max": 0.70},
    "source_dominance": {"recommended_max": 0.70},
    "very_short_assistant_share": {"recommended_max": 0.35},
}


def _read_jsonl(path: Path, version: str) -> list[dict[str, Any]]:
    try:
        if not path.is_file():
            return []
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetPlatformError("INVALID_DATASET", f"{path.name}:{line_number} contains invalid JSON", dataset=version, path=path) from exc
                if not isinstance(value, dict):
                    raise DatasetPlatformError("INVALID_DATASET", f"{path.name}:{line_number} must be an object", dataset=version, path=path)
                rows.append(value)
        return rows
    except DatasetPlatformError:
        raise
    except PermissionError as exc:
        raise DatasetPlatformError("ACCESS_DENIED", "Permission denied when reading the dataset", dataset=version, path=path) from exc
    except OSError as exc:
        raise DatasetPlatformError("BALANCE_ANALYSIS_FAILED", f"Unable to analyze the dataset: {exc}", dataset=version, path=path) from exc


def _messages(row: dict[str, Any]) -> list[dict[str, Any]] | None:
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    if any(not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "system", "tool"} for message in messages):
        return None
    return messages


def _texts(row: dict[str, Any]) -> tuple[str, str, str]:
    messages = _messages(row)
    if messages:
        users = [str(message.get("content") or "") for message in messages if message.get("role") == "user"]
        assistants = [str(message.get("content") or "") for message in messages if message.get("role") == "assistant"]
        return "\n".join(users), "\n".join(assistants), "\n".join(users + assistants)
    prompt = row.get("prompt") or row.get("input") or "\n".join(str(item.get("content") or "") for item in row.get("prompt_context", []) if isinstance(item, dict))
    assistant = row.get("preferred_response") or row.get("text") or row.get("output") or ""
    return str(prompt or ""), str(assistant or ""), f"{prompt or ''}\n{assistant or ''}".strip()


def _percentile(values: list[int], quantile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 2)


def _length_stats(values: list[int]) -> dict[str, Any]:
    buckets = Counter()
    for value in values:
        for name, lower, upper in LENGTH_BUCKETS:
            if value >= lower and (upper is None or value <= upper):
                buckets[name] += 1
                break
    total = len(values)
    return {
        "unit": "characters", "count": total, "min": min(values) if values else 0,
        "max": max(values) if values else 0, "mean": round(mean(values), 2) if values else 0,
        "median": round(median(values), 2) if values else 0, "p90": _percentile(values, .90), "p95": _percentile(values, .95),
        "buckets": {name: {"count": buckets[name], "share": round(buckets[name] / total, 4) if total else 0} for name, _, _ in LENGTH_BUCKETS},
        "bucket_limits": {name: {"min": lower, "max": upper} for name, lower, upper in LENGTH_BUCKETS},
    }


def _distribution(counter: Counter[str], total: int | None = None) -> dict[str, Any]:
    denominator = total if total is not None else sum(counter.values())
    return {"total": denominator, "items": [{"name": name, "count": count, "share": round(count / denominator, 4) if denominator else 0} for name, count in counter.most_common()]}


def _language_signal(text: str) -> str:
    if not text.strip():
        return "empty_invalid"
    arabic, latin = len(re.findall(r"[\u0600-\u06ff]", text)), len(re.findall(r"[A-Za-z]", text))
    if not arabic and not latin:
        return "empty_invalid"
    if arabic >= max(1, latin * 2):
        return "arabic_dominant"
    if latin >= max(1, arabic * 2):
        return "english_dominant"
    return "mixed"


def _duplicate_extra(values: Iterable[str]) -> tuple[int, int]:
    counts = Counter(value for value in values if value)
    return sum(count - 1 for count in counts.values() if count > 1), sum(1 for count in counts.values() if count > 1)


def _warning(code: str, severity: str, dimension: str, title: str, description: str, observed: Any, **recommended: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "dimension": dimension, "title": title, "description": description, "observed": observed, **recommended}


def analyze_dataset_balance(version: str) -> dict[str, Any]:
    directory = _version_dir(version)
    manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    rows_by_file = {name: _read_jsonl(directory / name, version) for name in DATASET_FILES if (directory / name).exists()}
    unknown_files = [path.name for path in directory.glob("*.jsonl") if path.name not in DATASET_FILES]
    typed_rows: list[tuple[str, str, dict[str, Any]]] = []
    malformed = 0
    for filename, rows in rows_by_file.items():
        kind = DATASET_FILES[filename]
        for row in rows:
            typed_rows.append((filename, kind, row))
            if kind in MESSAGE_KINDS and _messages(row) is None:
                malformed += 1
    record_counts = Counter()
    for _, kind, row in typed_rows:
        record_counts["unknown" if kind in MESSAGE_KINDS and _messages(row) is None else kind] += 1
    unknown_records = sum(len(_read_jsonl(directory / filename, version)) for filename in unknown_files)
    record_counts["unknown"] += unknown_records
    total_records = len(typed_rows) + unknown_records

    conversation_rows = [(kind, row, _messages(row)) for _, kind, row in typed_rows if _messages(row)]
    turn_counts = [sum(1 for message in messages or [] if message.get("role") == "user") for _, _, messages in conversation_rows]
    turn_buckets = Counter("1" if turns == 1 else "2-3" if turns <= 3 else "4-6" if turns <= 6 else "7-10" if turns <= 10 else "11+" for turns in turn_counts)
    conversation_total = len(turn_counts)
    conversation_structure = {
        "records": conversation_total, "single_turn": sum(turn == 1 for turn in turn_counts), "multi_turn": sum(turn > 1 for turn in turn_counts),
        "mean_turns": round(mean(turn_counts), 2) if turn_counts else 0, "median_turns": round(median(turn_counts), 2) if turn_counts else 0,
        "min_turns": min(turn_counts) if turn_counts else 0, "max_turns": max(turn_counts) if turn_counts else 0,
        "distribution": _distribution(turn_buckets, conversation_total),
    }
    text_triplets = [_texts(row) for _, _, row in typed_rows]
    user_lengths, assistant_lengths, total_lengths = ([len(parts[index]) for parts in text_triplets] for index in range(3))
    source_counts, review_counts, tag_counts, language_counts = Counter(), Counter(), Counter(), Counter()
    for (_, kind, row), (_, _, combined) in zip(typed_rows, text_triplets):
        source_counts[str(row.get("channel") or row.get("source") or row.get("origin") or row.get("source_type") or "Unknown")] += 1
        review = row.get("review_status")
        review_counts[str(review) if review else "PREFERENCE_PAIR" if kind == "preference" else "MANUAL_ADDITION" if row.get("origin") == "manual" else "MULTI_TURN" if kind == "multi_turn" else "UNSPECIFIED"] += 1
        tags = row.get("tags") or row.get("error_tags") or []
        if isinstance(tags, str): tags = [tags]
        if isinstance(tags, list): tag_counts.update(str(tag) for tag in tags if tag)
        language_counts[_language_signal(combined)] += 1

    exact_records, exact_record_groups = _duplicate_extra(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for _, _, row in typed_rows)
    exact_users, exact_user_groups = _duplicate_extra(_normalized(user) for user, _, _ in text_triplets)
    exact_assistants, exact_assistant_groups = _duplicate_extra(_normalized(assistant) for _, assistant, _ in text_triplets)
    conversation_extra, conversation_groups = _duplicate_extra(str(row.get("conversation_id")) for _, _, row in typed_rows if row.get("conversation_id"))
    try:
        health = dataset_health(version); integrity_warnings = health.get("warnings", []); eval_integrity = health.get("evaluation_integrity", {})
    except DatasetPlatformError:
        integrity_warnings, eval_integrity = [], {}

    warnings = []
    training_conversations = record_counts["sft"] + record_counts["multi_turn"]
    multi_share = record_counts["multi_turn"] / training_conversations if training_conversations else 0
    rule = BALANCE_RULES["multi_turn_share"]
    if training_conversations and multi_share < rule["recommended_min"]:
        warnings.append(_warning("MULTITURN_UNDERREPRESENTED", "warning", "record_type", "Multi-turn underrepresented", "The share of multi-turn records is below the recommended range for conversation data.", round(multi_share, 4), **rule))
    elif training_conversations and multi_share > rule["recommended_max"]:
        warnings.append(_warning("MULTITURN_OVERREPRESENTED", "warning", "record_type", "Multi-turn overrepresented", "The share of multi-turn records is above the recommended range for conversation data.", round(multi_share, 4), **rule))
    source_total = sum(source_counts.values()); top_source, top_count = source_counts.most_common(1)[0] if source_counts else ("Unknown", 0)
    source_share = top_count / source_total if source_total else 0
    if len(source_counts) > 1 and source_share > BALANCE_RULES["source_dominance"]["recommended_max"]:
        warnings.append(_warning("SOURCE_DOMINANCE", "warning", "source", "One source dominates", f"Source {top_source} dominates most records.", round(source_share, 4), **BALANCE_RULES["source_dominance"]))
    very_short_share = sum(length < 40 for length in assistant_lengths) / len(assistant_lengths) if assistant_lengths else 0
    if very_short_share > BALANCE_RULES["very_short_assistant_share"]["recommended_max"]:
        warnings.append(_warning("VERY_SHORT_ASSISTANT_RESPONSES", "warning", "text_length", "Too many very-short assistant responses", "The share of responses shorter than 40 characters is high.", round(very_short_share, 4), **BALANCE_RULES["very_short_assistant_share"]))
    if malformed or unknown_records: warnings.append(_warning("UNSUPPORTED_RECORDS", "error", "record_type", "Unsupported or malformed records", "Some records do not match the structure supported by this analysis.", malformed + unknown_records, recommended_max=0))
    if exact_records: warnings.append(_warning("EXACT_DUPLICATE_RECORDS", "error", "duplicates", "Exact duplicate records", "Exact duplicate records were found.", exact_records, recommended_max=0))
    if eval_integrity.get("conversation_overlap_count", 0):
        warnings.append(_warning("EVALUATION_CONVERSATION_OVERLAP", "warning", "evaluation_integrity", "Evaluation conversation overlap", "Some conversation identifiers occur in both training and evaluation; review split integrity before training.", eval_integrity["conversation_overlap_count"], recommended_max=0))
    if eval_integrity.get("exact_target_overlap_count", 0):
        warnings.append(_warning("EVALUATION_TARGET_OVERLAP", "error", "evaluation_integrity", "Evaluation target overlap", "Identical targets occur in training and evaluation.", eval_integrity["exact_target_overlap_count"], recommended_max=0))
    if total_records == 0: warnings.append(_warning("EMPTY_DATASET", "error", "record_type", "Empty dataset", "The version contains no analyzable records.", 0, recommended_min=1))

    actions = {
        "MULTITURN_UNDERREPRESENTED": ("high", "record_mix", "Add multi-turn samples after human review, without modifying this frozen version."),
        "MULTITURN_OVERREPRESENTED": ("medium", "record_mix", "Add single-turn SFT samples to a new version after approval."),
        "SOURCE_DOMINANCE": ("high", "source_diversity", "Collect and review samples from underrepresented sources in a new version."),
        "VERY_SHORT_ASSISTANT_RESPONSES": ("medium", "length_mix", "Review short-response representation and add longer examples where appropriate for the task."),
        "UNSUPPORTED_RECORDS": ("high", "data_quality", "Manually inspect unsupported records before using them for training."),
        "EXACT_DUPLICATE_RECORDS": ("high", "duplicates", "Review duplicates and create a new version only after the proposed remediation is approved."),
        "EVALUATION_CONVERSATION_OVERLAP": ("high", "evaluation_integrity", "Review overlapping conversation identifiers, then make a human decision about a future version."),
        "EVALUATION_TARGET_OVERLAP": ("high", "evaluation_integrity", "Remove evaluation-target leakage only in a new version after explicit approval."),
        "EMPTY_DATASET": ("high", "availability", "Select a readable version that contains records."),
    }
    recommendations = []
    for item in warnings:
        priority, category, action = actions[item["code"]]
        recommendations.append({"priority": priority, "category": category, "reason": item["title"], "evidence": {key: value for key, value in item.items() if key == "observed" or key.startswith("recommended_")}, "suggested_action": action})
    if not warnings:
        recommendations.append({"priority": "info", "category": "balance", "reason": "No balance rule was triggered", "evidence": {"rules": BALANCE_RULES}, "suggested_action": "Preserve the current mix and review it again when creating a new version."})
    status = "UNAVAILABLE" if total_records == 0 else "IMBALANCED" if any(item["severity"] == "error" for item in warnings) else "NEEDS_ATTENTION" if warnings else "BALANCED"
    return {
        "version": version, "state": _state(manifest, version), "analyzed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "read_only": True,
        "balance_status": status, "summary": {"total_records": total_records, "conversation_records": conversation_total, "warnings": len(warnings), "recommendations": len(recommendations)},
        "record_types": {"total": total_records, "counts": dict(record_counts), "distribution": _distribution(record_counts, total_records), "files": {name: len(rows) for name, rows in rows_by_file.items()}},
        "conversation_structure": conversation_structure,
        "length_distribution": {"user": _length_stats(user_lengths), "assistant": _length_stats(assistant_lengths), "conversation_total": _length_stats(total_lengths)},
        "sources": _distribution(source_counts), "review_types": _distribution(review_counts), "error_tags": _distribution(tag_counts),
        "language_signals": {"method": "simple Arabic/Latin character heuristic; not a language classifier", **_distribution(language_counts, total_records)},
        "duplicates": {"exact_records": exact_records, "exact_record_groups": exact_record_groups, "exact_user_inputs": exact_users, "exact_user_input_groups": exact_user_groups, "exact_assistant_targets": exact_assistants, "exact_assistant_target_groups": exact_assistant_groups, "conversation_id_extra": conversation_extra, "conversation_id_groups": conversation_groups, "evaluation_conversation_overlap": eval_integrity.get("conversation_overlap_count", 0), "evaluation_target_overlap": eval_integrity.get("exact_target_overlap_count", 0), "integrity_warnings": integrity_warnings},
        "rules": BALANCE_RULES, "warnings": warnings, "recommendations": recommendations,
    }
