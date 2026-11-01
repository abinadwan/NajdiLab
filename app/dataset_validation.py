"""Dataset-only validation gates for reviewed exports and freeze readiness."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset_platform import (
    DatasetPlatformError, TRAIN_FILES, _dataset_fingerprint, _diagnostics_status,
    _json, _jsonl, _sha256, _state, _version_dir, dataset_health,
)
from .dataset_quality import dataset_quality


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_native_dataset(directory: Path) -> dict[str, Any]:
    path=directory/"native_tool_use.jsonl"
    empty={"count":0,"tool_schema_valid":True,"capability_registry_compatible":True,"valid_loss_masks":0,"unsupported_tools":0,"malformed_tool_calls":0,"orphan_tool_results":0,"status":"NOT_PRESENT","blocking_issues":[]}
    if not path.is_file(): return empty
    from .native_tool_data import NativeToolDataError, validate_native_tool_record
    from .dataset_tools import ToolContractError, load_registry
    blockers=[]; rows=_jsonl(path); report={**empty,"count":len(rows),"status":"PASS"}
    try: registry=load_registry(directory/"capability-registry.json")
    except (OSError,json.JSONDecodeError,ToolContractError) as exc:
        report.update({"tool_schema_valid":False,"capability_registry_compatible":False,"status":"BLOCKED"}); blockers.append({"code":"NATIVE_TOOL_REGISTRY_INVALID","message":str(exc)}); report["blocking_issues"]=blockers; return report
    malformed=unsupported=orphan=0
    for row in rows:
        try: validate_native_tool_record(row,registry)
        except NativeToolDataError as exc:
            message=str(exc); unsupported+=int("does not exist" in message or "unavailable" in message); orphan+=int("orphan" in message or "matching tool result" in message); malformed+=int(not ("does not exist" in message or "unavailable" in message or "orphan" in message or "matching tool result" in message))
    mask_path=directory/"native-tool-loss-mask-validation.json"; mask=_json(mask_path,{},required=False) if mask_path.is_file() else {}
    valid_masks=int(mask.get("passed") or 0); fingerprint_ok=mask.get("capability_registry_fingerprint")==registry["fingerprint"]
    report.update({"tool_schema_valid":malformed==0 and orphan==0 and unsupported==0,"capability_registry_compatible":fingerprint_ok,"valid_loss_masks":valid_masks,"unsupported_tools":unsupported,"malformed_tool_calls":malformed,"orphan_tool_results":orphan,"capability_registry_version":registry["registry_version"],"capability_registry_fingerprint":registry["fingerprint"]})
    if unsupported or malformed or orphan: blockers.append({"code":"NATIVE_TOOL_DATA_INVALID","message":"Native Tool-Use records contain unsupported, malformed, or orphaned events."})
    if valid_masks!=len(rows) or mask.get("total")!=len(rows) or mask.get("failures"): blockers.append({"code":"NATIVE_TOOL_MASKS_INVALID","message":"Native Tool-Use loss masks are missing, stale, or incomplete."})
    if not fingerprint_ok: blockers.append({"code":"NATIVE_TOOL_REGISTRY_MISMATCH","message":"Loss-mask validation does not bind the active capability registry."})
    report["blocking_issues"]=blockers; report["status"]="BLOCKED" if blockers else "PASS"; return report


def quality_gate(version: str) -> dict[str, Any]:
    checked_at = _now()
    try:
        directory = _version_dir(version); manifest = _json(directory / "manifest.json", {}, dataset=version, required=True)
    except DatasetPlatformError as exc:
        return {"dataset": version, "status": "UNAVAILABLE", "blocking_issues": [{"code": exc.code, "message": str(exc)}], "warnings": [], "checks": {}, "dataset_fingerprint": None, "checked_at": checked_at}
    blockers, warnings, checks = [], [], {}
    state = _state(manifest, version); checks["frozen"] = state == "Frozen"
    if state != "Frozen": blockers.append({"code": "DATASET_NOT_FROZEN", "message": "The dataset must be Frozen."})
    native=validate_native_dataset(directory); checks["native_tool_use"]=native; blockers.extend(native["blocking_issues"])
    deterministic_quality = dataset_quality(version)
    checks["deterministic_quality"] = {
        "status": deterministic_quality["status"],
        "counts": deterministic_quality["counts"],
        "dataset_fingerprint": deterministic_quality["dataset_fingerprint"],
    }
    for finding in deterministic_quality["findings"]:
        if finding["severity"] == "confirmed_blocker":
            blockers.append({"code": finding["code"], "message": finding["explanation_ar"], "finding_id": finding["finding_id"], "sample_ids": finding["sample_ids"]})
        elif finding["severity"] == "warning":
            warnings.append({"code": finding["code"], "message": finding["explanation_ar"], "finding_id": finding["finding_id"], "sample_ids": finding["sample_ids"]})
    required = {}
    for name in TRAIN_FILES:
        path = directory / name; rows = _jsonl(path); required[name] = len(rows)
        if not path.is_file() or not rows: blockers.append({"code": "TRAINING_FILE_INVALID", "message": f"Training file {name} is missing or empty."})
    expected = manifest.get("sha256") or {}; checksum_failures = []
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file() or _sha256(path) != digest: checksum_failures.append(name)
    checks["checksums"] = not checksum_failures
    if checksum_failures: blockers.append({"code": "STALE_CHECKSUM", "message": "Checksum mismatches: " + ", ".join(checksum_failures)})
    diagnostics_valid, diagnostics_error = _diagnostics_status(directory, manifest); checks["diagnostics"] = diagnostics_valid
    if not diagnostics_valid: blockers.append({"code": "STALE_DIAGNOSTICS", "message": diagnostics_error or "Diagnostics are invalid."})
    health = dataset_health(version); loss = health.get("loss_mask_validation") or {}; training_count = health["training_count"]
    checks.update({"training_readiness": health["training_readiness"]["status"], "evaluation_integrity": health["evaluation_integrity"]["status"],
        "conversation_leakage": health["evaluation_integrity"]["conversation_overlap_count"], "exact_target_overlap": health["evaluation_integrity"]["exact_target_overlap_count"],
        "exact_duplicates": health["exact_duplicate_extra"], "loss_mask_total": loss.get("total"), "loss_mask_failures": len(loss.get("failures") or []), "training_files": required})
    conditions = [
        (health["training_readiness"]["status"] != "READY", "TRAINING_READINESS_BLOCKED", "Training Readiness is not READY."),
        (health["evaluation_integrity"]["status"] != "CLEAN", "EVALUATION_INTEGRITY_BLOCKED", "Evaluation Integrity is not CLEAN."),
        (checks["conversation_leakage"] > 0, "CONVERSATION_LEAKAGE", "Conversation leakage was found."),
        (checks["exact_target_overlap"] > 0, "EXACT_TARGET_OVERLAP", "Exact target overlap was found."),
        (checks["exact_duplicates"] > 0, "EXACT_TRAINING_DUPLICATES", "Exact duplicates were found in training."),
        (checks["loss_mask_failures"] > 0, "LOSS_MASK_FAILURE", "Loss-mask validation failures were found."),
        (loss.get("total") != training_count or loss.get("passed") != training_count, "LOSS_MASK_COUNT_MISMATCH", "The loss-mask count does not match the training count."),
    ]
    seen = {item["code"] for item in blockers}
    for failed, code, message in conditions:
        if failed and code not in seen: blockers.append({"code": code, "message": message}); seen.add(code)
    warnings = [item for item in health["warnings"] if item.get("level") != "error"]
    status = "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS"
    return {"dataset": version, "status": status, "blocking_issues": blockers, "warnings": warnings, "checks": checks,
        "dataset_fingerprint": _dataset_fingerprint(directory), "training_fingerprint": (manifest.get("diagnostics") or {}).get("training_fingerprint"),
        "dataset_counts": {"training": training_count, "sft": health["counts"].get("sft.jsonl", 0), "multi_turn": health["counts"].get("multi_turn.jsonl", 0), "native_tool_use":native["count"], "direct_language":health["counts"].get("direct_language.jsonl",0), "preference_pairs":health["counts"].get("preference_pairs.jsonl",0)}, "checked_at": checked_at}


def freeze_readiness_gate(version: str) -> dict[str, Any]:
    """Validate a registered Draft without requiring it to already be Frozen."""
    result = quality_gate(version)
    result["gate"] = "FREEZE_READINESS"
    result["blocking_issues"] = [item for item in result.get("blocking_issues", []) if item.get("code") != "DATASET_NOT_FROZEN"]
    result["status"] = "BLOCKED" if result["blocking_issues"] else "PASS_WITH_WARNINGS" if result.get("warnings") else "PASS"
    return result
