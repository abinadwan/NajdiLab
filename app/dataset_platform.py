from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

from .db import ROOT
from scripts.select_v007_windows import build_report as build_window_selection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_ROOT = PROJECT_ROOT / "exports"
DATASETS_ROOT = PROJECT_ROOT / "datasets"
# Backward-compatible alias used by existing tests and callers.
EXPORTS_DIR = EXPORTS_ROOT
TRAIN_FILES = ("sft.jsonl", "multi_turn.jsonl")
NATIVE_TRAIN_FILE = "native_tool_use.jsonl"
EVAL_FILES = ("text_sft_eval.jsonl", "tool_eval.jsonl", "vision_eval.jsonl", "runtime_agent_eval.jsonl", "evaluation_holdout.jsonl")
KNOWN_FILES = TRAIN_FILES + ("direct_language.jsonl", "preference_pairs.jsonl") + EVAL_FILES
SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
DIAGNOSTIC_PHRASES = ("أبشر", "يا هلا", "يا مرحبا", "الله يحييك", "وش عندك", "وش بغيت", "ولا تهون")


class DatasetPlatformError(ValueError):
    def __init__(self, code: str, message: str, *, dataset: str | None = None, path: Path | None = None):
        super().__init__(message)
        self.code = code
        self.dataset = dataset
        self.path = str(path) if path is not None else None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "dataset": self.dataset, "path": self.path, "message": str(self)}


def path_diagnostics(dataset: str | None = None) -> dict[str, Any]:
    exports = Path(EXPORTS_DIR).resolve()
    attempted = (exports / dataset).resolve() if dataset else exports
    return {
        "cwd": str(Path.cwd()), "project_root": str(PROJECT_ROOT),
        "project_root_exists": PROJECT_ROOT.is_dir(), "exports_root": str(exports),
        "exports_root_exists": exports.is_dir(), "attempted_path": str(attempted),
        "attempted_path_exists": attempted.exists(),
    }


def _exports_root() -> Path:
    if not PROJECT_ROOT.is_dir():
        raise DatasetPlatformError("PROJECT_ROOT_NOT_FOUND", "Unable to locate the NajdiLab project root", path=PROJECT_ROOT)
    root = Path(EXPORTS_DIR).resolve()
    try:
        exists = root.is_dir()
    except PermissionError as exc:
        raise DatasetPlatformError("ACCESS_DENIED", "Permission denied when reading the dataset versions directory", path=root) from exc
    except OSError as exc:
        raise DatasetPlatformError("IO_ERROR", f"Unable to inspect the dataset versions directory: {exc}", path=root) from exc
    if not exists:
        raise DatasetPlatformError("EXPORTS_ROOT_NOT_FOUND", "The dataset versions directory does not exist", path=root)
    return root


def _registry_roots() -> tuple[Path, ...]:
    exports = _exports_root()
    # Tests and callers may intentionally override EXPORTS_DIR for an isolated catalog.
    if exports != EXPORTS_ROOT.resolve():
        return (exports,)
    return (exports, DATASETS_ROOT.resolve())


def _version_dir(version: str) -> Path:
    if not SAFE_VERSION.fullmatch(version):
        raise DatasetPlatformError("DATASET_NOT_FOUND", "Invalid version name", dataset=version)
    roots = _registry_roots()
    matches = []
    for root in roots:
        path = (root / version).resolve()
        if path.parent != root:
            continue
        try:
            if path.is_dir(): matches.append(path)
        except PermissionError as exc:
            raise DatasetPlatformError("ACCESS_DENIED", "Permission denied when reading the dataset version", dataset=version, path=path) from exc
        except OSError as exc:
            raise DatasetPlatformError("IO_ERROR", f"Unable to inspect the dataset version: {exc}", dataset=version, path=path) from exc
    if len(matches) > 1:
        raise DatasetPlatformError("DUPLICATE_DATASET_VERSION", "Duplicate dataset version identifier across registered roots", dataset=version)
    if not matches:
        raise DatasetPlatformError("DATASET_NOT_FOUND", "Dataset version not found", dataset=version)
    return matches[0]


def _json(path: Path, fallback: Any, *, dataset: str | None = None, required: bool = False) -> Any:
    try:
        if not path.is_file():
            if required:
                raise DatasetPlatformError("MANIFEST_NOT_FOUND", "Manifest file not found", dataset=dataset, path=path)
            return fallback
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, type(fallback)):
            raise DatasetPlatformError("INVALID_MANIFEST", "Invalid manifest structure", dataset=dataset, path=path)
        return value
    except DatasetPlatformError:
        raise
    except PermissionError as exc:
        raise DatasetPlatformError("ACCESS_DENIED", "Permission denied when reading the file", dataset=dataset, path=path) from exc
    except json.JSONDecodeError as exc:
        raise DatasetPlatformError("INVALID_MANIFEST", f"Invalid JSON: {exc.msg}", dataset=dataset, path=path) from exc
    except OSError as exc:
        raise DatasetPlatformError("IO_ERROR", f"Unable to read the file: {exc}", dataset=dataset, path=path) from exc


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.is_file():
            return []
    except OSError as exc:
        raise DatasetPlatformError("ACCESS_DENIED", f"Unable to read {path.name}: file permissions prevent inspection", path=path) from exc
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetPlatformError("IO_ERROR", f"{path.name}:{number} contains invalid JSON", path=path) from exc
            if not isinstance(value, dict):
                raise DatasetPlatformError("IO_ERROR", f"{path.name}:{number} must be an object", path=path)
            rows.append(value)
    return rows


def _normalized(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _target(row: dict[str, Any]) -> str:
    messages = row.get("messages") or []
    index = row.get("target_message_index")
    if isinstance(index, int) and 0 <= index < len(messages):
        return _normalized(messages[index].get("content"))
    return _normalized(row.get("preferred_response") or row.get("text"))


def _conversation(row: dict[str, Any]) -> str | None:
    value = row.get("conversation_id")
    return str(value) if value else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state(manifest: dict[str, Any], version: str) -> str:
    declared = str(manifest.get("state") or "").strip().title()
    return declared if declared in {"Draft", "Frozen"} else "Frozen"


def _dataset_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.iterdir() if p.is_file()):
        digest.update(path.name.encode("utf-8") + b"\0" + _sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _refresh_manifest(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    counts, checksums = {}, {}
    for path in sorted(directory.glob("*.jsonl")):
        counts[path.name] = len(_jsonl(path)); checksums[path.name] = _sha256(path)
    manifest["files"], manifest["sha256"] = counts, checksums
    manifest["record_count"] = sum(counts.values())
    return manifest


def _training_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in TRAIN_FILES:
        path = directory / name
        digest.update(name.encode("utf-8") + b"\0")
        digest.update((_sha256(path) if path.is_file() else "missing").encode("ascii") + b"\0")
    native = directory / NATIVE_TRAIN_FILE
    if native.is_file():
        digest.update(NATIVE_TRAIN_FILE.encode("utf-8") + b"\0" + _sha256(native).encode("ascii") + b"\0")
    return digest.hexdigest()


def _words(value: Any) -> list[str]:
    return re.findall(r"[\w\u0600-\u06ff]+", str(value or ""), flags=re.UNICODE)


def _generate_training_diagnostics(directory: Path, manifest: dict[str, Any]) -> None:
    sft, multi = _jsonl(directory / "sft.jsonl"), _jsonl(directory / "multi_turn.jsonl")
    train = [(row, "single-turn") for row in sft] + [(row, "multi-turn") for row in multi]
    fingerprint = _training_fingerprint(directory)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    failures = []
    for row, _ in train:
        messages, index, mask = row.get("messages"), row.get("target_message_index"), row.get("message_loss_mask")
        reasons = []
        if not isinstance(messages, list) or not isinstance(index, int) or not 0 <= index < len(messages) or messages[index].get("role") != "assistant": reasons.append("invalid_target_message_index")
        if not isinstance(mask, list) or not isinstance(messages, list) or len(mask) != len(messages) or sum(value == 1 for value in mask) != 1 or (isinstance(index, int) and isinstance(mask, list) and 0 <= index < len(mask) and mask[index] != 1): reasons.append("invalid_message_loss_mask")
        if reasons: failures.append({"id": str(row.get("id") or ""), "reasons": reasons})
    native = _jsonl(directory / NATIVE_TRAIN_FILE)
    native_mask = _json(directory / "native-tool-loss-mask-validation.json", {}) if native else {}
    native_failures = list(native_mask.get("failures") or [])
    if native and (native_mask.get("total") != len(native) or native_mask.get("passed") != len(native)):
        native_failures.append({"id": "native_tool_use", "reasons": ["native_mask_count_mismatch"]})
    failures.extend(native_failures)
    loss = {"schema_version": 2, "version": manifest.get("version"), "training_fingerprint": fingerprint, "generated_at": generated_at,
        "by_format": {"sft": {"passed": len(sft), "total": len(sft)}, "multi_turn": {"passed": len(multi), "total": len(multi)}, "native_tool_use": {"passed": int(native_mask.get("passed") or 0), "total": len(native)}},
        "passed": len(train) - (len(failures) - len(native_failures)) + int(native_mask.get("passed") or 0), "total": len(train) + len(native), "failures": failures}

    conversations: dict[str, dict[str, Any]] = {}
    total_target_words = total_context_words = 0
    targets = []
    for row, kind in train:
        key = _conversation(row) or f"record:{row.get('id', '')}"
        messages = row.get("messages") or []; index = row.get("target_message_index")
        target = _target(row); targets.append(target)
        context = " ".join(str(message.get("content") or "") for message in messages[:index] if isinstance(message, dict)) if isinstance(index, int) else ""
        target_words, context_words = len(_words(target)), len(_words(context))
        item = conversations.setdefault(key, {"total_records": 0, "single_turn_count": 0, "multi_turn_count": 0, "target_words": 0, "context_words": 0, "ids": []})
        item["total_records"] += 1; item["single_turn_count"] += int(kind == "single-turn"); item["multi_turn_count"] += int(kind == "multi-turn")
        item["target_words"] += target_words; item["context_words"] += context_words; item["ids"].append(str(row.get("id") or ""))
        total_target_words += target_words; total_context_words += context_words
    total = len(train)
    for item in conversations.values():
        item["record_share"] = item["total_records"] / total if total else 0
        item["target_word_share"] = item["target_words"] / total_target_words if total_target_words else 0
        item["context_word_share"] = item["context_words"] / total_context_words if total_context_words else 0
    highest = lambda field: max(conversations.items(), key=lambda pair: pair[1][field]) if conversations else None
    counts = [len(_words(target)) for target in targets]; longest = sorted(range(len(targets)), key=lambda i: counts[i], reverse=True)[:10]
    balance = {"version": manifest.get("version"), "training_fingerprint": fingerprint, "generated_at": generated_at,
        "counts": {"sft": len(sft), "multi_turn": len(multi), "native_tool_use": len(native), "total_train": total + len(native)},
        "conversation_balance": {"total_records": total, "total_target_words": total_target_words, "total_context_words": total_context_words,
            "conversation_count": len(conversations), "conversations": conversations, "highest_record_share": highest("record_share"),
            "highest_target_word_share": highest("target_word_share"), "highest_context_word_share": highest("context_word_share")},
        "target_analysis": {"record_count": total, "unique_targets": len(set(targets)),
            "exact_duplicate_records_extra": sum(count - 1 for count in Counter(targets).values() if count > 1),
            "phrase_counts": {phrase: sum(phrase in target for target in targets) for phrase in DIAGNOSTIC_PHRASES},
            "longest_10_target_word_share": sum(counts[i] for i in longest) / sum(counts) if sum(counts) else 0},
        "multi_turn_overlap": {"conversation_count": len({_conversation(row) for row in multi if _conversation(row)})}}
    _write_json(directory / "loss-mask-validation.json", loss); _write_json(directory / "balancing_report.json", balance)
    manifest["loss_mask_validation"] = {key: loss[key] for key in ("version", "training_fingerprint", "generated_at", "passed", "total", "failures")}
    manifest["diagnostics"] = {"version": manifest.get("version"), "training_fingerprint": fingerprint, "generated_at": generated_at,
        "artifacts": {"loss-mask-validation.json": _sha256(directory / "loss-mask-validation.json"), "balancing_report.json": _sha256(directory / "balancing_report.json")}}


def _diagnostics_status(directory: Path, manifest: dict[str, Any]) -> tuple[bool, str | None]:
    expected_fingerprint = _training_fingerprint(directory); metadata = manifest.get("diagnostics") or {}
    if metadata.get("version") != manifest.get("version") or metadata.get("training_fingerprint") != expected_fingerprint:
        return False, "diagnostic version/source does not match current training files"
    for name, expected in (metadata.get("artifacts") or {}).items():
        path = directory / name
        if not path.is_file() or _sha256(path) != expected: return False, f"stale diagnostic artifact: {name}"
    if set((metadata.get("artifacts") or {})) != {"loss-mask-validation.json", "balancing_report.json"}:
        return False, "diagnostic artifacts are incomplete"
    return True, None


def regenerate_training_diagnostics(version: str) -> dict[str, Any]:
    directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    if _state(manifest, version) != "Draft":
        raise DatasetPlatformError("TARGET_NOT_DRAFT", "Diagnostics can only be regenerated for a Draft version", dataset=version)
    _generate_training_diagnostics(directory, manifest)
    manifest.setdefault("provenance", {})["diagnostics_regenerated_at"] = manifest["diagnostics"]["generated_at"]
    temp = directory / ".manifest.json.tmp"
    try:
        _write_json(temp, manifest); os.replace(temp, directory / "manifest.json")
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise DatasetPlatformError("APPLY_FAILED", f"Unable to save diagnostics: {exc}", dataset=version) from exc
    return dataset_health(version)


def create_derived_version(source_version: str, target_version: str) -> dict[str, Any]:
    if not SAFE_VERSION.fullmatch(target_version):
        raise DatasetPlatformError("INVALID_VERSION_NAME", "Invalid new version name", dataset=target_version)
    source = _version_dir(source_version)
    source_manifest = _json(source / "manifest.json", {}, dataset=source_version, required=True)
    if _state(source_manifest, source_version) != "Frozen":
        raise DatasetPlatformError("SOURCE_NOT_FROZEN", "A version can only be derived from a Frozen source", dataset=source_version)
    root = _exports_root(); target = (root / target_version).resolve()
    if target.parent != root:
        raise DatasetPlatformError("INVALID_VERSION_NAME", "Invalid new version name", dataset=target_version)
    if target.exists():
        raise DatasetPlatformError("VERSION_ALREADY_EXISTS", "Version name is already in use", dataset=target_version, path=target)
    source_fingerprint = _dataset_fingerprint(source)
    temp = Path(tempfile.mkdtemp(prefix=f".{target_version}-", dir=root))
    try:
        for item in source.iterdir():
            if item.is_file(): shutil.copy2(item, temp / item.name)
        manifest = _json(temp / "manifest.json", {}, dataset=target_version, required=True)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest.update({"version": target_version, "state": "Draft", "created_at": now, "source_version": source_version,
            "provenance": {"kind": "derived", "source_version": source_version, "source_fingerprint": source_fingerprint, "created_at": now},
            "training_started": False, "merge_started": False, "gguf_started": False, "ollama_started": False})
        manifest.pop("protected_hashes_before", None)
        _refresh_manifest(temp, manifest); _generate_training_diagnostics(temp, manifest); _write_json(temp / "manifest.json", manifest)
        os.replace(temp, target)
    except DatasetPlatformError:
        shutil.rmtree(temp, ignore_errors=True); raise
    except (OSError, PermissionError) as exc:
        shutil.rmtree(temp, ignore_errors=True)
        raise DatasetPlatformError("APPLY_FAILED", f"Unable to create the derived version: {exc}", dataset=target_version) from exc
    return dataset_version_detail(target_version)


def conversation_overlap_analysis(version: str) -> dict[str, Any]:
    directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    rows_by_file = {name: _jsonl(directory / name) for name in TRAIN_FILES + EVAL_FILES if (directory / name).is_file()}
    train_ids = {_conversation(row) for name in TRAIN_FILES for row in rows_by_file.get(name, []) if _conversation(row)}
    eval_ids = {_conversation(row) for name in EVAL_FILES for row in rows_by_file.get(name, []) if _conversation(row)}
    overlaps = []
    reserved_training_targets = {_target(row) for name in TRAIN_FILES for row in rows_by_file.get(name, []) if _target(row)}
    for conversation_id in sorted(train_ids & eval_ids):
        train_rows = [(name, row) for name in TRAIN_FILES for row in rows_by_file.get(name, []) if _conversation(row) == conversation_id]
        eval_rows = [(name, row) for name in EVAL_FILES for row in rows_by_file.get(name, []) if _conversation(row) == conversation_id]
        eval_targets = [_target(row) for _, row in eval_rows if _target(row)]
        would_duplicate_target = bool(reserved_training_targets.intersection(eval_targets)) or len(eval_targets) != len(set(eval_targets))
        destination = "Evaluation" if would_duplicate_target else "Training" if len(eval_rows) < len(train_rows) else "Evaluation"
        if destination == "Training": reserved_training_targets.update(eval_targets)
        moved = len(eval_rows) if destination == "Training" else len(train_rows)
        types = sorted({"SFT" if name == "sft.jsonl" else "Multi-turn SFT" if name == "multi_turn.jsonl" else "Evaluation" for name, _ in train_rows + eval_rows})
        overlaps.append({"conversation_id": conversation_id, "train_records": len(train_rows), "eval_records": len(eval_rows),
            "record_types": types, "source_files": sorted({name for name, _ in train_rows + eval_rows}),
            "message_count": sum(len(row.get("messages") or []) for _, row in train_rows + eval_rows),
            "turn_count": sum(1 for _, row in train_rows + eval_rows for message in (row.get("messages") or []) if message.get("role") == "user"),
            "proposed_destination": destination, "records_to_move": moved,
            "reason": "Keeping the conversation in evaluation prevents an exact duplicate in training." if would_duplicate_target else f"Move only {moved} records instead of {len(train_rows) + len(eval_rows) - moved} while keeping the complete conversation on one side."})
    # Select destinations globally because targets can repeat across different conversations.
    # The integrity constraints outrank the number of moved records.
    if overlaps and len(overlaps) <= 20:
        overlap_ids = {item["conversation_id"] for item in overlaps}
        base_train = [row for name in TRAIN_FILES for row in rows_by_file.get(name, []) if _conversation(row) not in overlap_ids]
        base_eval = [row for name in EVAL_FILES for row in rows_by_file.get(name, []) if _conversation(row) not in overlap_ids]
        grouped = {item["conversation_id"]: [row for name in TRAIN_FILES + EVAL_FILES for row in rows_by_file.get(name, []) if _conversation(row) == item["conversation_id"]] for item in overlaps}
        candidates = []
        original_eval_count = sum(len(rows_by_file.get(name, [])) for name in EVAL_FILES)
        for choices in product(("Training", "Evaluation"), repeat=len(overlaps)):
            final_train, final_eval = list(base_train), list(base_eval)
            moved = 0
            for item, destination in zip(overlaps, choices):
                (final_train if destination == "Training" else final_eval).extend(grouped[item["conversation_id"]])
                moved += item["eval_records"] if destination == "Training" else item["train_records"]
            train_targets = [_target(row) for row in final_train if _target(row)]
            eval_targets = {_target(row) for row in final_eval if _target(row)}
            duplicate_extra = sum(count - 1 for count in Counter(train_targets).values() if count > 1)
            target_overlap = len(set(train_targets) & eval_targets)
            integrity_errors = duplicate_extra + target_overlap
            candidates.append(((integrity_errors, moved, abs(len(final_eval) - original_eval_count)), choices, duplicate_extra, target_overlap))
        _, choices, duplicate_extra, target_overlap = min(candidates, key=lambda item: item[0])
        for item, destination in zip(overlaps, choices):
            item["proposed_destination"] = destination
            item["records_to_move"] = item["eval_records"] if destination == "Training" else item["train_records"]
            item["reason"] = f"The global plan preserves exact duplicates={duplicate_extra} and exact target overlaps={target_overlap} with the fewest possible moves."
    return {"version": version, "state": _state(manifest, version), "overlap_conversations": len(overlaps), "overlap_records": sum(x["eval_records"] for x in overlaps), "items": overlaps}


def create_overlap_plan(version: str) -> dict[str, Any]:
    directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    analysis = conversation_overlap_analysis(version); fingerprint = _dataset_fingerprint(directory)
    plan = {"version": version, "dry_run": True, "source_unchanged": True, "state": _state(manifest, version),
        "dataset_fingerprint": fingerprint, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy": "preserve_zero_exact_duplicates; then_minimize_moved_records; ties_to_evaluation", "items": analysis["items"],
        "summary": {"overlap_conversations": analysis["overlap_conversations"], "overlap_records": analysis["overlap_records"], "records_to_move": sum(x["records_to_move"] for x in analysis["items"])}}
    token_value = {key: value for key, value in plan.items() if key != "created_at"}
    plan["plan_token"] = hashlib.sha256(json.dumps(token_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return plan


def eval_leakage_on_path(directory: Path) -> dict[str, Any]:
    train = [row for name in TRAIN_FILES for row in _jsonl(directory / name)]
    eval_rows = [row for name in EVAL_FILES for row in _jsonl(directory / name)]
    train_ids = {_conversation(row) for row in train if _conversation(row)}
    return {"conversation_overlap_count": sum(_conversation(row) in train_ids for row in eval_rows)}


def apply_overlap_plan(version: str, plan_token: str, dataset_fingerprint: str) -> dict[str, Any]:
    directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    if _state(manifest, version) != "Draft":
        raise DatasetPlatformError("TARGET_NOT_DRAFT", "The plan can only be applied to a Draft version", dataset=version)
    current = create_overlap_plan(version)
    if not plan_token or plan_token != current["plan_token"] or dataset_fingerprint != current["dataset_fingerprint"]:
        raise DatasetPlatformError("OVERLAP_PLAN_STALE", "The version changed after the plan was created; create a new Dry Run", dataset=version)
    root = _exports_root(); staged = Path(tempfile.mkdtemp(prefix=f".{version}-apply-", dir=root)); backup = root / f".{version}-rollback"
    try:
        shutil.rmtree(staged); shutil.copytree(directory, staged)
        for item in current["items"]:
            cid, destination = item["conversation_id"], item["proposed_destination"]
            if destination == "Training":
                moved = []
                for name in EVAL_FILES:
                    path = staged / name; rows = _jsonl(path)
                    moved.extend(row for row in rows if _conversation(row) == cid)
                    if path.is_file(): _write_jsonl(path, [row for row in rows if _conversation(row) != cid])
                sft_path, multi_path = staged / "sft.jsonl", staged / "multi_turn.jsonl"
                sft_rows, multi_rows = _jsonl(sft_path), _jsonl(multi_path)
                for row in moved:
                    users = sum(message.get("role") == "user" for message in (row.get("messages") or []))
                    (multi_rows if users > 1 else sft_rows).append(row)
                _write_jsonl(sft_path, sft_rows); _write_jsonl(multi_path, multi_rows)
            else:
                moved = []
                for name in TRAIN_FILES:
                    path = staged / name; rows = _jsonl(path)
                    moved.extend(row for row in rows if _conversation(row) == cid); _write_jsonl(path, [row for row in rows if _conversation(row) != cid])
                target = staged / "text_sft_eval.jsonl"; _write_jsonl(target, _jsonl(target) + moved)
        updated = _json(staged / "manifest.json", {}, dataset=version, required=True); now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        updated["train_eval_conversation_overlap"] = 0
        updated["remediation"] = {"kind": "conversation_overlap", "applied_at": now, "policy": current["policy"], "plan_token": plan_token, "changes": current["items"], "texts_modified": False, "records_deleted": 0}
        updated.setdefault("provenance", {})["last_operation"] = updated["remediation"]
        updated.pop("diagnostics", None); updated.pop("loss_mask_validation", None)
        _refresh_manifest(staged, updated); _generate_training_diagnostics(staged, updated); _write_json(staged / "manifest.json", updated)
        if eval_leakage_on_path(staged)["conversation_overlap_count"]:
            raise DatasetPlatformError("APPLY_FAILED", "The plan did not fully separate conversations", dataset=version)
        if backup.exists(): shutil.rmtree(backup)
        os.replace(directory, backup); os.replace(staged, directory); shutil.rmtree(backup)
    except DatasetPlatformError:
        shutil.rmtree(staged, ignore_errors=True)
        if backup.exists() and not directory.exists(): os.replace(backup, directory)
        raise
    except Exception as exc:
        shutil.rmtree(staged, ignore_errors=True)
        if backup.exists() and not directory.exists(): os.replace(backup, directory)
        raise DatasetPlatformError("APPLY_FAILED", f"Unable to apply the plan safely: {exc}", dataset=version) from exc
    return {"ok": True, "applied": True, "version": version, "plan": current, "detail": dataset_version_detail(version)}


def freeze_dataset_version(version: str) -> dict[str, Any]:
    directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    if _state(manifest, version) != "Draft":
        raise DatasetPlatformError("TARGET_NOT_DRAFT", "The version is not a Draft", dataset=version)
    diagnostics_valid, diagnostics_error = _diagnostics_status(directory, manifest)
    training_count = sum(len(_jsonl(directory / name)) for name in TRAIN_FILES) + len(_jsonl(directory / NATIVE_TRAIN_FILE))
    loss = manifest.get("loss_mask_validation") or {}
    if not diagnostics_valid or loss.get("version") != version or loss.get("training_fingerprint") != _training_fingerprint(directory) or loss.get("total") != training_count or loss.get("passed") != training_count or loss.get("failures"):
        raise DatasetPlatformError("INVALID_MANIFEST", f"Cannot freeze: invalid diagnostics ({diagnostics_error or 'loss-mask mismatch'})", dataset=version)
    health = dataset_health(version)
    if health["training_readiness"]["status"] != "READY" or health["evaluation_integrity"]["status"] != "CLEAN":
        raise DatasetPlatformError("INVALID_MANIFEST", "Cannot freeze until Health and Evaluation Integrity checks pass", dataset=version)
    expected = manifest.get("sha256") or {}
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file() or _sha256(path) != digest:
            raise DatasetPlatformError("INVALID_MANIFEST", f"Checksum failed for file {name}", dataset=version, path=path)
    manifest["state"] = "Frozen"; manifest["frozen_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    temp = directory / ".manifest.json.tmp"
    try:
        _write_json(temp, manifest); os.replace(temp, directory / "manifest.json")
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise DatasetPlatformError("APPLY_FAILED", f"Unable to freeze the version: {exc}", dataset=version) from exc
    return dataset_version_detail(version)


def eval_leakage(version: str) -> dict[str, Any]:
    directory = _version_dir(version)
    train = [row for name in TRAIN_FILES for row in _jsonl(directory / name)]
    eval_groups = {name: _jsonl(directory / name) for name in EVAL_FILES if (directory / name).is_file()}
    train_conversations = {_conversation(row) for row in train if _conversation(row)}
    train_targets = {_target(row) for row in train if _target(row)}
    conversation_hits: list[dict[str, str]] = []
    target_hits: list[dict[str, str]] = []
    for filename, rows in eval_groups.items():
        for row in rows:
            conversation = _conversation(row)
            target = _target(row)
            if conversation and conversation in train_conversations:
                conversation_hits.append({"file": filename, "id": str(row.get("id", "")), "conversation_id": conversation})
            if target and target in train_targets:
                target_hits.append({"file": filename, "id": str(row.get("id", "")), "target": target[:160]})
    by_file = []
    for filename, rows in eval_groups.items():
        file_conversations = [x for x in conversation_hits if x["file"] == filename]
        file_targets = [x for x in target_hits if x["file"] == filename]
        by_file.append({
            "name": filename,
            "count": len(rows),
            "conversation_overlap_count": len(file_conversations),
            "exact_target_overlap_count": len(file_targets),
            "status": "CLEAN" if not file_conversations and not file_targets else "FAILED",
        })
    return {
        "locked": True,
        "training_files": list(TRAIN_FILES),
        "eval_files": [{"name": name, "count": len(rows)} for name, rows in eval_groups.items()],
        "integrity_by_file": by_file,
        "status": "CLEAN" if not conversation_hits and not target_hits else "FAILED",
        "train_count": len(train),
        "eval_count": sum(len(rows) for rows in eval_groups.values()),
        "conversation_overlap_count": len(conversation_hits),
        "exact_target_overlap_count": len(target_hits),
        "conversation_overlap": conversation_hits,
        "exact_target_overlap": target_hits,
        "leakage_free": not conversation_hits and not target_hits,
    }


def dataset_health(version: str) -> dict[str, Any]:
    directory = _version_dir(version)
    manifest = _json(directory / "manifest.json", {})
    diagnostics_valid, diagnostics_error = _diagnostics_status(directory, manifest)
    strict_diagnostics = manifest.get("state") in {"Draft", "Frozen"}
    balancing = _json(directory / "balancing_report.json", {}) if diagnostics_valid or not strict_diagnostics else {}
    rows_by_file = {name: _jsonl(directory / name) for name in KNOWN_FILES if (directory / name).is_file()}
    train = [row for name in TRAIN_FILES for row in rows_by_file.get(name, [])]
    native_train = _jsonl(directory / NATIVE_TRAIN_FILE)
    gradient_count = len(train) + len(native_train)
    targets = [_target(row) for row in train if _target(row)]
    duplicate_extra = sum(count - 1 for count in Counter(targets).values() if count > 1)
    invalid_targets = 0
    invalid_masks = 0
    for row in train:
        messages = row.get("messages")
        target_index = row.get("target_message_index")
        mask = row.get("message_loss_mask")
        if not isinstance(messages, list) or not isinstance(target_index, int) or not 0 <= target_index < len(messages) or messages[target_index].get("role") != "assistant":
            invalid_targets += 1
        if not isinstance(mask, list) or not isinstance(messages, list) or len(mask) != len(messages) or sum(value == 1 for value in mask) != 1 or (isinstance(target_index, int) and 0 <= target_index < len(mask) and mask[target_index] != 1):
            invalid_masks += 1
    leakage = eval_leakage(version)
    warnings = []
    balance = balancing.get("conversation_balance", {})
    if balance.get("highest_record_share", [None, {}])[1].get("record_share", 0) > .15:
        warnings.append({"level": "warning", "code": "conversation_concentration", "message": "A single conversation exceeds 15% of training records."})
    if balance.get("highest_context_word_share", [None, {}])[1].get("context_word_share", 0) > .30:
        warnings.append({"level": "warning", "code": "context_concentration", "message": "A single conversation context exceeds 30% of context words."})
    if duplicate_extra:
        warnings.append({"level": "error", "code": "exact_duplicates", "message": f"There are {duplicate_extra} extra duplicate training targets."})
    if not leakage["leakage_free"]:
        warnings.append({"level": "warning", "scope": "evaluation", "code": "eval_leakage", "message": f"Detected {leakage['conversation_overlap_count']} conversation overlaps in evaluation sets."})
    loss = manifest.get("loss_mask_validation", {}) if diagnostics_valid or not strict_diagnostics else {}
    loss_count_mismatch = bool(strict_diagnostics and (loss.get("version") != version or loss.get("training_fingerprint") != _training_fingerprint(directory) or loss.get("total") != gradient_count or loss.get("passed") != gradient_count))
    if strict_diagnostics and (not diagnostics_valid or loss_count_mismatch):
        warnings.append({"level": "error", "code": "stale_diagnostics", "message": f"Diagnostics do not match the current training files: {diagnostics_error or 'loss-mask total mismatch'}."})
    if loss and loss.get("failures"):
        warnings.append({"level": "error", "code": "loss_mask", "message": "Loss-mask validation failed for some records."})
    training_errors = duplicate_extra + invalid_targets + invalid_masks + len(loss.get("failures", [])) + int(strict_diagnostics and (not diagnostics_valid or loss_count_mismatch))
    readiness = "NOT_READY" if training_errors else "READY"
    target_analysis = balancing.get("target_analysis", {})
    return {
        "version": version,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "training_readiness": {"status": readiness, "invalid_target_indices": invalid_targets, "invalid_loss_masks": invalid_masks, "training_errors": training_errors},
        "evaluation_integrity": {"status": leakage["status"], "by_file": leakage["integrity_by_file"], "conversation_overlap_count": leakage["conversation_overlap_count"], "exact_target_overlap_count": leakage["exact_target_overlap_count"]},
        "status": "not_ready" if readiness == "NOT_READY" else "ready_with_warnings" if readiness == "READY_WITH_WARNINGS" else "ready",
        "counts": {name: len(rows) for name, rows in rows_by_file.items()},
        "training_count": gradient_count,
        "unique_targets": len(set(targets)),
        "exact_duplicate_extra": duplicate_extra,
        "conversation_count": balance.get("conversation_count"),
        "highest_record_share": balance.get("highest_record_share"),
        "highest_context_word_share": balance.get("highest_context_word_share"),
        "highest_target_word_share": balance.get("highest_target_word_share"),
        "multi_turn_overlap": balancing.get("multi_turn_overlap", {}),
        "phrase_counts": target_analysis.get("phrase_counts", {}),
        "longest_10_target_word_share": target_analysis.get("longest_10_target_word_share"),
        "loss_mask_validation": loss,
        "diagnostics": {"valid": diagnostics_valid or not strict_diagnostics, "error": diagnostics_error if strict_diagnostics else None, "training_fingerprint": _training_fingerprint(directory)},
        "leakage": leakage,
        "warnings": warnings,
    }


def balance_candidate(version: str) -> dict[str, Any]:
    directory = _version_dir(version)
    rows = _jsonl(directory / "multi_turn.jsonl")
    if not rows:
        return {"version": version, "candidate_only": True, "before": 0, "after": 0, "keep": [], "drop": [], "report": {}}
    selected, report = build_window_selection(rows)
    keep_ids = {str(row.get("id")) for row in selected}
    return {
        "version": version,
        "candidate_only": True,
        "source_unchanged": True,
        "before": len(rows),
        "after": len(selected),
        "keep": [{"id": str(row.get("id")), "conversation_id": _conversation(row), "target": _target(row)[:180]} for row in rows if str(row.get("id")) in keep_ids],
        "drop": [{"id": str(row.get("id")), "conversation_id": _conversation(row), "target": _target(row)[:180]} for row in rows if str(row.get("id")) not in keep_ids],
        "report": report,
    }


def dataset_version_detail(version: str) -> dict[str, Any]:
    directory = _version_dir(version)
    manifest = _json(directory / "manifest.json", {})
    files = []
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        count = len(_jsonl(path)) if path.suffix == ".jsonl" else None
        files.append({"name": path.name, "bytes": path.stat().st_size, "count": count, "sha256": _sha256(path)})
    return {
        "version": version,
        "state": _state(manifest, version),
        "path": str(directory),
        "manifest": manifest,
        "provenance": manifest.get("provenance") or manifest.get("source_version") or manifest.get("source") or "Undocumented",
        "files": files,
        "health": dataset_health(version),
        "eval": eval_leakage(version),
    }


def list_dataset_versions() -> list[dict[str, Any]]:
    roots = _registry_roots()
    result = []
    try:
        candidates = sorted((p for root in roots if root.is_dir() for p in root.iterdir() if p.name.startswith("gold-")), key=lambda p: p.name, reverse=True)
    except PermissionError as exc:
        raise DatasetPlatformError("ACCESS_DENIED", "Permission denied when indexing the dataset versions directory", path=root) from exc
    except OSError as exc:
        raise DatasetPlatformError("IO_ERROR", f"Unable to index the dataset versions directory: {exc}", path=root) from exc
    counts = Counter(path.name for path in candidates if path.is_dir())
    for path in candidates:
        try:
            if not path.is_dir():
                continue
            if counts[path.name] > 1:
                if any(item["version"] == path.name for item in result): continue
                raise DatasetPlatformError("DUPLICATE_DATASET_VERSION", "Duplicate dataset version identifier across registered roots", dataset=path.name)
            manifest = _json(path / "manifest.json", {}, dataset=path.name, required=True)
            result.append({"version": path.name, "name": path.name, "created_at": manifest.get("created_at"), "counts": manifest.get("files", {}), "state": _state(manifest, path.name), "readable": True, "manifest_status": "valid", "health_available": True, "error": None})
        except DatasetPlatformError as exc:
            result.append({"version": path.name, "name": path.name, "created_at": None, "counts": {}, "state": "Unavailable", "readable": False, "manifest_status": "unavailable", "health_available": False, "error": exc.as_dict()})
    return result
