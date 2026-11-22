from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dataset_platform import EVAL_FILES, KNOWN_FILES, NATIVE_TRAIN_FILE, TRAIN_FILES, _dataset_fingerprint, _jsonl, _version_dir


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("messages")
    return value if isinstance(value, list) else []


def _prompt_target(row: dict[str, Any]) -> tuple[str, str]:
    messages = _messages(row)
    users = [_norm(x.get("content")) for x in messages if isinstance(x, dict) and x.get("role") == "user"]
    index = row.get("target_message_index")
    if isinstance(index, int) and 0 <= index < len(messages) and isinstance(messages[index], dict):
        target = _norm(messages[index].get("content"))
    else:
        assistants = [_norm(x.get("content")) for x in messages if isinstance(x, dict) and x.get("role") == "assistant"]
        target = assistants[-1] if assistants else _norm(row.get("preferred_response") or row.get("text"))
    return "\n".join(users), target


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w\u0600-\u06ff]+", value))


def _stable_id(code: str, samples: list[str], evidence: str) -> str:
    material = json.dumps([code, sorted(samples), evidence], ensure_ascii=False, separators=(",", ":"))
    return "qf-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def analyze_directory(directory: Path, *, version: str | None = None) -> dict[str, Any]:
    records: list[tuple[str, int, dict[str, Any], str]] = []
    parse_findings: list[dict[str, Any]] = []
    names = tuple(dict.fromkeys(KNOWN_FILES + (NATIVE_TRAIN_FILE,)))
    for name in names:
        path = directory / name
        if not path.is_file():
            continue
        try:
            rows = _jsonl(path)
        except Exception as exc:
            parse_findings.append(_finding("MALFORMED_FILE", "confirmed_blocker", [name], str(exc)))
            continue
        split = "evaluation" if name in EVAL_FILES else "training"
        records.extend((name, i, row, split) for i, row in enumerate(rows, 1))

    findings = list(parse_findings)
    exact: dict[str, list[str]] = defaultdict(list)
    prompt_targets: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    prompt_rows: list[tuple[str, set[str], str, str]] = []
    prompts_by_split: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    conversations: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    targets_by_split: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for name, line, row, split in records:
        sample = str(row.get("id") or f"{name}:{line}")
        prompt, target = _prompt_target(row)
        canonical = json.dumps({"messages": row.get("messages"), "preferred_response": row.get("preferred_response"), "text": row.get("text")}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        exact[hashlib.sha256(canonical.encode()).hexdigest()].append(sample)
        if prompt:
            prompt_targets[prompt][target].append(sample)
            prompt_rows.append((prompt, _tokens(prompt), sample, split))
            prompts_by_split[prompt][split].append(sample)
        if target:
            targets_by_split[target][split].append(sample)
        cid = str(row.get("conversation_id") or "").strip()
        if cid:
            conversations[cid][split].append(sample)

        messages = row.get("messages")
        if name == "direct_language.jsonl":
            if not _norm(row.get("text") or row.get("content")):
                findings.append(_finding("DIRECT_TEXT_EMPTY", "confirmed_blocker", [sample], name))
            continue
        if name == "preference_pairs.jsonl":
            chosen = _norm(row.get("chosen") or row.get("preferred_response"))
            rejected = _norm(row.get("rejected") or row.get("rejected_response"))
            if not chosen or not rejected or chosen == rejected:
                findings.append(_finding("PREFERENCE_PAIR_INVALID", "confirmed_blocker", [sample], name))
            continue
        if not isinstance(messages, list) or not messages:
            findings.append(_finding("MESSAGES_MISSING", "confirmed_blocker", [sample], name))
            continue
        roles = [x.get("role") if isinstance(x, dict) else None for x in messages]
        if any(role not in {"system", "user", "assistant", "tool"} for role in roles) or "user" not in roles or "assistant" not in roles:
            findings.append(_finding("ROLE_STRUCTURE_INVALID", "confirmed_blocker", [sample], ",".join(map(str, roles))))
        non_system = [role for role in roles if role != "system"]
        if non_system and non_system[0] != "user":
            findings.append(_finding("TURN_ORDER_INVALID", "confirmed_blocker", [sample], ",".join(map(str, roles))))
        if not target:
            findings.append(_finding("ASSISTANT_TARGET_EMPTY", "confirmed_blocker", [sample], name))
        if not row.get("source") and not row.get("source_type") and not row.get("provenance"):
            findings.append(_finding("PROVENANCE_MISSING", "warning", [sample], name))
        if row.get("training_eligible") is True and row.get("evaluation_only") is True:
            findings.append(_finding("REVIEW_STATE_INCONSISTENT", "confirmed_blocker", [sample], "training_eligible+evaluation_only"))
        if target and ("```" in target and target.count("```") % 2 or "\ufffd" in target):
            findings.append(_finding("SUSPICIOUS_FORMATTING", "warning", [sample], "unbalanced_or_replacement_character"))
        instructions = [_norm(x.get("content")) for x in messages if isinstance(x, dict) and x.get("role") == "system"]
        if len(instructions) != len(set(instructions)):
            findings.append(_finding("REPEATED_INSTRUCTIONS", "warning", [sample], "duplicate_system_instruction"))

    for values in exact.values():
        if len(values) > 1:
            findings.append(_finding("EXACT_DUPLICATE", "confirmed_blocker", values, "identical_record"))
    for prompt, variants in prompt_targets.items():
        nonempty = {target: samples for target, samples in variants.items() if target}
        if len(nonempty) > 1:
            samples = [x for group in nonempty.values() for x in group]
            findings.append(_finding("CONTRADICTORY_TARGETS", "confirmed_blocker", samples, hashlib.sha256(prompt.encode()).hexdigest()[:12]))
    for cid, splits in conversations.items():
        if splits["training"] and splits["evaluation"]:
            findings.append(_finding("TRAIN_EVAL_CONVERSATION_LEAKAGE", "confirmed_blocker", splits["training"] + splits["evaluation"], cid))
    for target, splits in targets_by_split.items():
        if splits["training"] and splits["evaluation"]:
            findings.append(_finding("TRAIN_EVAL_TARGET_LEAKAGE", "confirmed_blocker", splits["training"] + splits["evaluation"], hashlib.sha256(target.encode()).hexdigest()[:12]))

    # The same context in training and evaluation: the evaluated question has been trained on.
    for prompt, splits in prompts_by_split.items():
        if splits["training"] and splits["evaluation"]:
            findings.append(_finding("TRAIN_EVAL_CONTEXT_LEAKAGE", "confirmed_blocker", splits["training"] + splits["evaluation"], hashlib.sha256(prompt.encode()).hexdigest()[:12]))

    # Deterministic, conservative near-duplicate candidates; never delete automatically.
    for i, (left, left_tokens, left_id, left_split) in enumerate(prompt_rows):
        if len(left_tokens) < 5:
            continue
        for right, right_tokens, right_id, right_split in prompt_rows[i + 1:]:
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 0.0
            if 0.85 <= score < 1.0:
                code = "TRAIN_EVAL_NEAR_DUPLICATE" if left_split != right_split else "NEAR_DUPLICATE_PROMPT"
                findings.append(_finding(code, "warning", [left_id, right_id], f"jaccard={score:.4f}"))

    findings.sort(key=lambda x: (x["severity"], x["code"], x["finding_id"]))
    counts = {severity: sum(x["severity"] == severity for x in findings) for severity in ("confirmed_blocker", "warning", "informational")}
    return {"schema_version": 1, "dataset_version": version or directory.name, "dataset_fingerprint": _dataset_fingerprint(directory),
            "status": "BLOCKED" if counts["confirmed_blocker"] else ("WARNING" if counts["warning"] else "READY"),
            "counts": {**counts, "records": len(records)}, "findings": findings,
            "policy": {"near_duplicates": "review_only_no_automatic_deletion", "result_order": "deterministic"}}


def _finding(code: str, severity: str, samples: list[str], evidence: str) -> dict[str, Any]:
    samples = sorted(set(map(str, samples)))
    return {"finding_id": _stable_id(code, samples, evidence), "code": code, "severity": severity,
            "sample_ids": samples, "explanation_ar": _AR.get(code, code), "evidence": evidence}


_AR = {
    "MALFORMED_FILE": "The data file is invalid or unreadable.", "MESSAGES_MISSING": "The record has no valid messages.",
    "DIRECT_TEXT_EMPTY": "The direct-language text is empty.", "PREFERENCE_PAIR_INVALID": "The preference pair is incomplete or identical.",
    "ROLE_STRUCTURE_INVALID": "Message order or roles are invalid for training.", "ASSISTANT_TARGET_EMPTY": "The assistant target is empty or missing.",
    "PROVENANCE_MISSING": "Record provenance is undocumented and requires review.", "REVIEW_STATE_INCONSISTENT": "The review state combines training and evaluation.",
    "SUSPICIOUS_FORMATTING": "Suspicious formatting requires human review.", "EXACT_DUPLICATE": "The record is an exact duplicate.",
    "TURN_ORDER_INVALID": "The turn sequence does not start with a valid user request.", "REPEATED_INSTRUCTIONS": "System instructions are repeated within the record.",
    "CONTRADICTORY_TARGETS": "The same prompt has contradictory targets.", "TRAIN_EVAL_CONVERSATION_LEAKAGE": "The same conversation appears in training and evaluation.",
    "TRAIN_EVAL_TARGET_LEAKAGE": "An identical response appears in training and evaluation.", "NEAR_DUPLICATE_PROMPT": "Two highly similar prompts require review.",
}


def dataset_quality(version: str) -> dict[str, Any]:
    return analyze_directory(_version_dir(version), version=version)


def validate_candidate_release(directory: Path, *, source_version: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = analyze_directory(directory)
    file_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.glob("*.jsonl"))}
    manifest_core = {"source_version": source_version, "configuration": config or {}, "files": file_hashes,
                     "record_counts": {p.name: len(_jsonl(p)) for p in sorted(directory.glob("*.jsonl"))}}
    release_fp = hashlib.sha256(json.dumps(manifest_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    checks = {"quality_no_blockers": quality["counts"]["confirmed_blocker"] == 0,
              "sft_present": (directory / "sft.jsonl").is_file(),
              "response_only_loss_masks": _loss_masks_valid(directory)}
    return {"schema_version": 1, "status": "VALID" if all(checks.values()) else "BLOCKED", "release_fingerprint": release_fp,
            "manifest": manifest_core, "checks": checks, "quality": quality}


def _loss_masks_valid(directory: Path) -> bool:
    for name in TRAIN_FILES:
        for row in _jsonl(directory / name):
            messages, index, mask = row.get("messages"), row.get("target_message_index"), row.get("message_loss_mask")
            if not isinstance(messages, list) or not isinstance(index, int) or not isinstance(mask, list): return False
            if len(mask) != len(messages) or not 0 <= index < len(mask) or mask[index] != 1 or sum(v == 1 for v in mask) != 1: return False
    return True
