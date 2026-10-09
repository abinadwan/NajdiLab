from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .dataset_platform import (
    DatasetPlatformError, EVAL_FILES, TRAIN_FILES, _dataset_fingerprint, _diagnostics_status,
    _json, _jsonl, _sha256, _state, _version_dir, dataset_health, list_dataset_versions,
)
from .dataset_quality import dataset_quality

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAINING_ROOT = PROJECT_ROOT / "training"
JOBS_ROOT = TRAINING_ROOT / "jobs"
MODELS_FILE = TRAINING_ROOT / "models.json"
MODEL_DISCOVERY_LIMIT = 100
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
JOB_ID = re.compile(r"^train-\d{8}-\d{3}$")
ALLOWED_METHODS = {"LoRA", "QLoRA"}
ALLOWED_SCHEDULERS = {"linear", "cosine", "constant", "constant_with_warmup"}
ALLOWED_OPTIMIZERS = {"adamw_8bit", "adamw_torch", "paged_adamw_8bit"}
ALLOWED_TARGET_MODULES = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


class TrainingControlError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 422):
        super().__init__(message); self.code = code; self.status = status
    def as_dict(self) -> dict[str, Any]: return {"ok": False, "code": self.code, "message": str(self)}


def _now() -> str: return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def initialize_training_control() -> None:
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    if not MODELS_FILE.exists():
        _atomic_json(MODELS_FILE, {"models": [{
            "id": "ministral-3-3b-unsloth-bnb4", "display_name": "Ministral 3 3B Instruct (Unsloth 4-bit)",
            "path": "/home/najdi/najdi-training/models/Ministral-3-3B-Instruct-2512-unsloth-bnb-4bit",
            "architecture": "Mistral3ForConditionalGeneration", "tokenizer_path": None,
            "quantization": "bnb-4bit", "context_length": None, "runtime": "wsl:NajdiTrain",
            "enabled": True, "model_size_gb": None, "source_type": "local", "revision": None,
            "validation_status": "VALID", "availability": "AVAILABLE", "last_verified_at": _now(),
            "notes": "مسار مرجعي من سكربتات المشروع؛ يتطلب Check Runtime صريحًا قبل التنفيذ.", "created_at": _now(),
        }]})


def _models() -> list[dict[str, Any]]:
    initialize_training_control(); value = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    return value.get("models", []) if isinstance(value, dict) else []


def _model_fingerprint(model: dict[str, Any]) -> str:
    identity = {key: model.get(key) for key in ("id", "source_type", "path", "repository_id", "revision", "architecture", "quantization", "weight_format")}
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _enrich_model(model: dict[str, Any]) -> dict[str, Any]:
    value = dict(model)
    value.setdefault("source_type", "local" if value.get("path") else "huggingface")
    value.setdefault("repository_id", None); value.setdefault("revision", None)
    value.setdefault("provider", "local" if value["source_type"] == "local" else value["source_type"])
    value.setdefault("parameter_count", None); value.setdefault("precision", None)
    value.setdefault("weight_format", "safetensors"); value.setdefault("tokenizer_available", None)
    value.setdefault("framework_compatibility", {"transformers": "NOT_CHECKED", "unsloth": "NOT_CHECKED", "peft": "NOT_CHECKED"})
    value.setdefault("estimated_memory_gb", value.get("model_size_gb")); value.setdefault("measured_memory_gb", None)
    value.setdefault("availability", "NOT_CHECKED"); value.setdefault("validation_status", "NOT_CHECKED")
    value.setdefault("excluded", False); value.setdefault("exclusion_reason", None); value.setdefault("last_verified_at", None)
    value["fingerprint"] = _model_fingerprint(value)
    value["trainable"] = bool(value.get("enabled")) and not value["excluded"] and value["source_type"] != "ollama" and value["validation_status"] == "VALID"
    return value


def list_models() -> list[dict[str, Any]]: return [_enrich_model(item) for item in _models()]


def get_model(model_id: str) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(model_id): raise TrainingControlError("MODEL_NOT_FOUND", "معرّف النموذج غير صالح", status=404)
    model = next((item for item in _models() if item.get("id") == model_id), None)
    if not model: raise TrainingControlError("MODEL_NOT_FOUND", "النموذج غير مسجل", status=404)
    return _enrich_model(model)


def register_model(data: dict[str, Any]) -> dict[str, Any]:
    model_id, path = str(data.get("id") or ""), str(data.get("path") or "")
    if not SAFE_ID.fullmatch(model_id): raise TrainingControlError("MODEL_UNAVAILABLE", "معرّف النموذج غير صالح")
    runtime = str(data.get("runtime") or "")
    source_type = str(data.get("source_type") or ("local" if path else "huggingface"))
    if source_type not in {"local", "huggingface", "ollama"}: raise TrainingControlError("MODEL_UNAVAILABLE", "مصدر النموذج غير مدعوم")
    repository_id = str(data.get("repository_id") or "") or None
    if source_type == "huggingface" and (not repository_id or not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repository_id)):
        raise TrainingControlError("MODEL_UNAVAILABLE", "معرّف مستودع Hugging Face غير صالح")
    if source_type == "ollama" and not repository_id: repository_id = path or model_id
    if source_type == "local" and runtime.startswith("wsl:"):
        pure = PurePosixPath(path)
        if not pure.is_absolute() or ".." in pure.parts: raise TrainingControlError("MODEL_UNAVAILABLE", "مسار WSL غير صالح")
    elif source_type == "local":
        candidate = Path(path)
        if not candidate.is_absolute() or ".." in candidate.parts: raise TrainingControlError("MODEL_UNAVAILABLE", "مسار النموذج غير صالح")
    models = _models()
    if any(item.get("id") == model_id for item in models): raise TrainingControlError("MODEL_UNAVAILABLE", "معرّف النموذج مستخدم بالفعل", status=409)
    model = {"id": model_id, "display_name": str(data.get("display_name") or model_id), "path": path or repository_id,
        "source_type": source_type, "provider": data.get("provider") or source_type, "repository_id": repository_id, "revision": data.get("revision"),
        "architecture": data.get("architecture"), "tokenizer_path": data.get("tokenizer_path"),
        "quantization": data.get("quantization"), "precision": data.get("precision"), "weight_format": data.get("weight_format"), "parameter_count": data.get("parameter_count"), "context_length": data.get("context_length"),
        "runtime": runtime, "enabled": bool(data.get("enabled", True)), "model_size_gb": data.get("model_size_gb"),
        "notes": data.get("notes"), "availability": "INFERENCE_ONLY" if source_type == "ollama" else "NOT_CHECKED", "validation_status": "EXCLUDED" if source_type == "ollama" else "NOT_CHECKED",
        "excluded": source_type == "ollama", "exclusion_reason": "Ollama/GGUF inference model is not a trainable checkpoint." if source_type == "ollama" else None, "created_at": _now()}
    models.append(model); _atomic_json(MODELS_FILE, {"models": models}); return _enrich_model(model)


def validate_model(model_id: str) -> dict[str, Any]:
    models = _models(); index = next((i for i, item in enumerate(models) if item.get("id") == model_id), None)
    if index is None: raise TrainingControlError("MODEL_NOT_FOUND", "النموذج غير مسجل", status=404)
    model = _enrich_model(models[index]); blockers, warnings = [], []
    if model["source_type"] == "ollama": blockers.append({"code": "INFERENCE_ONLY", "message": "نموذج Ollama/GGUF للاستدلال فقط."})
    elif model["source_type"] == "huggingface":
        blockers.append({"code": "REMOTE_WEIGHTS_UNAVAILABLE", "message": "لم تُنزّل الأوزان؛ يلزم staging مصرح به والتحقق المحلي قبل التدريب."})
    elif str(model.get("runtime") or "").startswith("wsl:"):
        warnings.append({"code": "RUNTIME_PATH_REQUIRES_LIVE_CHECK", "message": "يتطلب المسار تحققًا حيًا داخل WSL."})
    else:
        root = Path(str(model.get("path") or "")); config = root / "config.json"
        tokenizer = any((root / name).is_file() for name in ("tokenizer.json", "tokenizer.model", "tokenizer_config.json"))
        weights = list(root.glob("*.safetensors"))[:2] + list(root.glob("*.bin"))[:2]
        if not root.is_dir(): blockers.append({"code": "MODEL_PATH_NOT_ACCESSIBLE", "message": "مسار النموذج غير متاح."})
        if root.is_dir() and not config.is_file(): blockers.append({"code": "MODEL_CONFIG_MISSING", "message": "config.json مفقود."})
        if root.is_dir() and not tokenizer: blockers.append({"code": "TOKENIZER_NOT_AVAILABLE", "message": "ملفات tokenizer مفقودة."})
        if root.is_dir() and not weights: blockers.append({"code": "TRAINABLE_WEIGHTS_MISSING", "message": "لا توجد أوزان تدريب قابلة للاستخدام."})
        model["tokenizer_available"] = tokenizer
    model["validation_status"] = "INVALID" if blockers else "VALID"
    model["availability"] = "UNAVAILABLE" if blockers else "AVAILABLE"
    model["last_verified_at"] = _now(); model["validation"] = {"blockers": blockers, "warnings": warnings}
    model["fingerprint"] = _model_fingerprint(model); models[index] = {k: v for k, v in model.items() if k != "trainable"}
    _atomic_json(MODELS_FILE, {"models": models}); return _enrich_model(models[index])


def discover_models(data: dict[str, Any]) -> dict[str, Any]:
    roots = data.get("roots") or []; candidates = []
    if not isinstance(roots, list) or len(roots) > 10: raise TrainingControlError("INVALID_DISCOVERY_SCOPE", "نطاق الاكتشاف غير صالح")
    for raw in roots:
        root = Path(str(raw))
        if not root.is_absolute() or not root.is_dir(): continue
        for config in list(root.glob("*/config.json"))[:MODEL_DISCOVERY_LIMIT - len(candidates)]:
            candidates.append({"source_type": "local", "path": str(config.parent), "display_name": config.parent.name})
        if len(candidates) >= MODEL_DISCOVERY_LIMIT: break
    return {"items": candidates, "count": len(candidates), "limit": MODEL_DISCOVERY_LIMIT, "truncated": len(candidates) >= MODEL_DISCOVERY_LIMIT}


def training_datasets() -> list[dict[str, Any]]:
    return [{"version": item["version"], "state": item["state"], "readable": item["readable"], "quality_gate_available": item["readable"]} for item in list_dataset_versions()]


def native_tool_preflight(directory: Path) -> dict[str, Any]:
    path=directory/"native_tool_use.jsonl"
    empty={"count":0,"tool_schema_valid":True,"capability_registry_compatible":True,"valid_loss_masks":0,"unsupported_tools":0,"malformed_tool_calls":0,"orphan_tool_results":0,"status":"NOT_PRESENT","blocking_issues":[]}
    if not path.is_file(): return empty
    from .native_tool_data import NativeToolDataError, validate_native_tool_record
    from .tool_runtime import ToolContractError, load_registry
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
    if state != "Frozen": blockers.append({"code": "DATASET_NOT_FROZEN", "message": "Dataset يجب أن يكون Frozen."})
    native=native_tool_preflight(directory); checks["native_tool_use"]=native; blockers.extend(native["blocking_issues"])
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
        if not path.is_file() or not rows: blockers.append({"code": "TRAINING_FILE_INVALID", "message": f"ملف التدريب {name} مفقود أو فارغ."})
    expected = manifest.get("sha256") or {}; checksum_failures = []
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file() or _sha256(path) != digest: checksum_failures.append(name)
    checks["checksums"] = not checksum_failures
    if checksum_failures: blockers.append({"code": "STALE_CHECKSUM", "message": "Checksums غير مطابقة: " + ", ".join(checksum_failures)})
    diagnostics_valid, diagnostics_error = _diagnostics_status(directory, manifest); checks["diagnostics"] = diagnostics_valid
    if not diagnostics_valid: blockers.append({"code": "STALE_DIAGNOSTICS", "message": diagnostics_error or "Diagnostics غير صالحة."})
    health = dataset_health(version); loss = health.get("loss_mask_validation") or {}; training_count = health["training_count"]
    checks.update({"training_readiness": health["training_readiness"]["status"], "evaluation_integrity": health["evaluation_integrity"]["status"],
        "conversation_leakage": health["evaluation_integrity"]["conversation_overlap_count"], "exact_target_overlap": health["evaluation_integrity"]["exact_target_overlap_count"],
        "exact_duplicates": health["exact_duplicate_extra"], "loss_mask_total": loss.get("total"), "loss_mask_failures": len(loss.get("failures") or []), "training_files": required})
    conditions = [
        (health["training_readiness"]["status"] != "READY", "TRAINING_READINESS_BLOCKED", "Training Readiness ليست READY."),
        (health["evaluation_integrity"]["status"] != "CLEAN", "EVALUATION_INTEGRITY_BLOCKED", "Evaluation Integrity ليست CLEAN."),
        (checks["conversation_leakage"] > 0, "CONVERSATION_LEAKAGE", "يوجد conversation leakage."),
        (checks["exact_target_overlap"] > 0, "EXACT_TARGET_OVERLAP", "يوجد exact target overlap."),
        (checks["exact_duplicates"] > 0, "EXACT_TRAINING_DUPLICATES", "يوجد exact duplicate في التدريب."),
        (checks["loss_mask_failures"] > 0, "LOSS_MASK_FAILURE", "توجد failures في loss masks."),
        (loss.get("total") != training_count or loss.get("passed") != training_count, "LOSS_MASK_COUNT_MISMATCH", "Loss-mask count لا يطابق Training count."),
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


def validate_training_config(data: dict[str, Any]) -> dict[str, Any]:
    defaults = {"method": "QLoRA", "epochs": 3, "max_steps": None, "learning_rate": 0.0002, "batch_size": 1,
        "gradient_accumulation_steps": 8, "max_seq_length": 2048, "warmup_ratio": 0.03, "weight_decay": 0.01,
        "lr_scheduler": "cosine", "seed": 3407, "packing": False, "gradient_checkpointing": True,
        "bf16": True, "fp16": False, "optimizer": "adamw_8bit", "lora_rank": 16, "lora_alpha": 32,
        "lora_dropout": 0.0, "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], "save_steps": 10}
    config = {**defaults, **(data or {})}
    try:
        numeric_positive = ("epochs", "learning_rate", "batch_size", "gradient_accumulation_steps", "max_seq_length", "lora_rank", "lora_alpha")
        if any(float(config[key]) <= 0 for key in numeric_positive): raise ValueError
        raw_max_steps = config.get("max_steps")
        if raw_max_steps not in (None, 0, "0") and int(raw_max_steps) <= 0: raise ValueError
        if int(config["save_steps"]) < 0 or float(config["warmup_ratio"]) < 0 or float(config["warmup_ratio"]) >= 1: raise ValueError
    except (TypeError, ValueError, KeyError) as exc: raise TrainingControlError("INVALID_TRAINING_CONFIG", "قيم إعدادات التدريب غير صالحة") from exc
    if config["method"] not in ALLOWED_METHODS or config["lr_scheduler"] not in ALLOWED_SCHEDULERS or config["optimizer"] not in ALLOWED_OPTIMIZERS: raise TrainingControlError("INVALID_TRAINING_CONFIG", "إعداد غير مدعوم في stack الحالي")
    modules = config.get("target_modules")
    if not isinstance(modules, list) or not modules or not set(modules) <= ALLOWED_TARGET_MODULES: raise TrainingControlError("INVALID_TRAINING_CONFIG", "LoRA target modules غير صالحة")
    if bool(config["bf16"]) and bool(config["fp16"]): raise TrainingControlError("INVALID_TRAINING_CONFIG", "اختر bf16 أو fp16 وليس كليهما")
    for key in ("batch_size", "gradient_accumulation_steps", "max_seq_length", "seed", "lora_rank", "lora_alpha", "save_steps"): config[key] = int(config[key])
    config["max_steps"] = None if config.get("max_steps") in (None, 0, "0") else int(config["max_steps"])
    config["epochs"] = float(config["epochs"]); config["learning_rate"] = float(config["learning_rate"]); config["warmup_ratio"] = float(config["warmup_ratio"]); config["weight_decay"] = float(config["weight_decay"]); config["lora_dropout"] = float(config["lora_dropout"])
    return config


def calculate_plan(records: int, config: dict[str, Any]) -> dict[str, Any]:
    if records <= 0: raise TrainingControlError("INVALID_TRAINING_CONFIG", "Training records يجب أن تكون أكبر من صفر")
    cfg = validate_training_config(config); batches = math.ceil(records / cfg["batch_size"]); steps_epoch = math.ceil(batches / cfg["gradient_accumulation_steps"])
    total_steps = cfg["max_steps"] if cfg["max_steps"] is not None else math.ceil(steps_epoch * cfg["epochs"])
    checkpoints = math.ceil(total_steps / cfg["save_steps"]) if cfg["save_steps"] else 0
    return {"training_records": records, "epochs": cfg["epochs"], "batch_size": cfg["batch_size"], "gradient_accumulation_steps": cfg["gradient_accumulation_steps"],
        "effective_batch_size": cfg["batch_size"] * cfg["gradient_accumulation_steps"], "batches_per_epoch": batches,
        "optimizer_steps_per_epoch": steps_epoch, "estimated_total_optimizer_steps": total_steps, "max_steps_override": cfg["max_steps"],
        "trainer_max_steps": cfg["max_steps"] if cfg["max_steps"] is not None else -1,
        "max_seq_length": cfg["max_seq_length"], "estimated_tokens": None, "estimated_checkpoint_count": checkpoints, "estimated_output_size": None,
        "warnings": ["Token/output estimates unavailable until tokenizer and runtime are validated."]}


def estimate_vram(model: dict[str, Any], config: dict[str, Any], runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    size = model.get("model_size_gb"); total = (runtime or {}).get("gpu_vram_total_gb"); free = (runtime or {}).get("gpu_vram_free_gb")
    if not size: return {"status": "UNKNOWN", "estimated_requirement_gb": None, "gpu_total_gb": total, "gpu_available_gb": free, "margin_gb": None, "estimation_method": "unavailable_without_model_size", "confidence": "low", "assumptions": ["Runtime check and model size are required."]}
    multiplier = 1.45 if config["method"] == "QLoRA" else 3.0
    estimate = round(float(size) * multiplier + config["batch_size"] * config["max_seq_length"] / 4096 * 0.75, 2)
    margin = round(float(free) - estimate, 2) if free is not None else None
    status = "UNKNOWN" if margin is None else "LIKELY_SAFE" if margin >= 2 else "TIGHT" if margin >= 0 else "LIKELY_OOM"
    return {"status": status, "estimated_requirement_gb": estimate, "gpu_total_gb": total, "gpu_available_gb": free, "margin_gb": margin,
        "estimation_method": "conservative_parameter_plus_activation_heuristic_v1", "confidence": "low", "assumptions": ["Single GPU", "No optimizer offload", "Estimate is not a guarantee"]}


def training_preflight(data: dict[str, Any]) -> dict[str, Any]:
    version, model_id = str(data.get("dataset_version") or ""), str(data.get("model_id") or "")
    gate = quality_gate(version); model = get_model(model_id); config = validate_training_config(data.get("training_config") or {})
    native=(gate.get("checks") or {}).get("native_tool_use") or {}; template_supported=model.get("id")=="ministral-3-3b-unsloth-bnb4"
    if native.get("count") and not template_supported:
        gate["blocking_issues"].append({"code":"NATIVE_TOOL_TEMPLATE_UNSUPPORTED","message":"Configured model/template cannot consume Native Tool-Use records."}); gate["status"]="BLOCKED"
    gate.setdefault("checks",{})["native_tool_trainer"]={"supported":True,"template_supported":template_supported,"will_consume":bool(native.get("count"))}
    plan = calculate_plan(int((gate.get("dataset_counts") or {}).get("training") or 0), config) if gate["status"] not in {"BLOCKED", "UNAVAILABLE"} else None
    model_blockers = []
    if model.get("excluded"): model_blockers.append({"code": "MODEL_EXCLUDED", "message": model.get("exclusion_reason") or "النموذج مستبعد."})
    if model.get("validation_status") != "VALID": model_blockers.append({"code": "MODEL_NOT_VALIDATED", "message": "يجب اجتياز تحقق توافق النموذج قبل READY."})
    return {"dataset": gate, "model": model, "model_validation": {"status": "BLOCKED" if model_blockers else "PASS", "blocking_issues": model_blockers}, "training_config": config, "runtime_target": data.get("runtime_target") or {"type": "wsl", "distro": "NajdiTrain"},
        "runtime_check": {"status": "NOT_RUN", "message": "Check Runtime لا يعمل تلقائيًا."}, "training_plan": plan,
        "vram_estimate": estimate_vram(model, config), "can_create_draft": bool(model.get("enabled")) and model.get("source_type") != "ollama", "can_mark_ready": gate["status"] in {"PASS", "PASS_WITH_WARNINGS"} and not model_blockers}


def check_runtime(data: dict[str, Any]) -> dict[str, Any]:
    distro = str(data.get("distro") or "NajdiTrain")
    if not SAFE_ID.fullmatch(distro): raise TrainingControlError("INVALID_RUNTIME", "اسم WSL distro غير صالح")
    try:
        listed = subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc: return {"status": "UNAVAILABLE", "wsl_available": False, "error": str(exc), "checked_at": _now()}
    names = [line.strip().replace("\x00", "") for line in listed.stdout.splitlines() if line.strip()]
    return {"status": "AVAILABLE" if distro in names else "UNAVAILABLE", "wsl_available": listed.returncode == 0, "target_distro": distro, "distro_available": distro in names,
        "checks": {"python": "NOT_RUN", "venv": "NOT_RUN", "torch": "NOT_RUN", "cuda": "NOT_RUN", "gpu": "NOT_RUN", "unsloth": "NOT_RUN", "paths": "NOT_RUN"},
        "checked_at": _now(), "note": "Phase 2-A only lists WSL distributions; workload/runtime imports are deferred."}


def _next_job_id() -> str:
    prefix = datetime.now().strftime("train-%Y%m%d-")
    used = {path.name for path in JOBS_ROOT.iterdir() if path.is_dir()}
    for number in range(1, 1000):
        candidate = f"{prefix}{number:03d}"
        if candidate not in used: return candidate
    raise TrainingControlError("JOB_ID_EXHAUSTED", "تعذر تخصيص Job ID", status=500)


def _job_path(job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id): raise TrainingControlError("JOB_NOT_FOUND", "Job ID غير صالح", status=404)
    return JOBS_ROOT / job_id / "job.json"


def get_job(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.is_file(): raise TrainingControlError("JOB_NOT_FOUND", "Training Job غير موجود", status=404)
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs() -> list[dict[str, Any]]:
    initialize_training_control(); result = []
    for path in sorted(JOBS_ROOT.glob("train-*/job.json"), reverse=True):
        try: result.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError): continue
    return result


def create_job(data: dict[str, Any]) -> dict[str, Any]:
    preflight = training_preflight(data)
    if not preflight["can_create_draft"]: raise TrainingControlError("MODEL_UNAVAILABLE", "النموذج غير مفعّل")
    initialize_training_control(); job_id = _next_job_id(); now = _now(); job_dir = JOBS_ROOT / job_id
    try: job_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc: raise TrainingControlError("JOB_ALREADY_EXISTS", "Job ID مستخدم", status=409) from exc
    job = {"job_id": job_id, "created_at": now, "updated_at": now, "status": "DRAFT", "dataset_version": preflight["dataset"]["dataset"],
        "dataset_fingerprint": preflight["dataset"].get("dataset_fingerprint"), "dataset_counts": preflight["dataset"].get("dataset_counts"),
        "quality_gate_result": preflight["dataset"], "model_config": preflight["model"], "training_config": preflight["training_config"],
        "runtime_target": preflight["runtime_target"], "calculated_steps": preflight["training_plan"], "vram_estimate": preflight["vram_estimate"],
        "warnings": preflight["dataset"].get("warnings", []), "acknowledged_warnings": None,
        "output_directory": f"/home/najdi/najdi-training/outputs/{job_id}", "checkpoint_directory": f"/home/najdi/najdi-training/checkpoints/{job_id}",
        "logs_path": f"/home/najdi/najdi-training/logs/{job_id}.log", "provenance": {"created_by": "NajdiLab Phase 2-A", "execution_started": False}}
    _atomic_json(job_dir / "job.json", job); return job


def create_production_job(source_job_id: str) -> dict[str, Any]:
    source=get_job(source_job_id)
    smoke_dir=JOBS_ROOT/source_job_id/"attempts"/"attempt-001"/"result.json"
    if source.get("smoke_status")!="PASSED" or not smoke_dir.is_file() or json.loads(smoke_dir.read_text(encoding="utf-8")).get("status")!="PASSED":
        raise TrainingControlError("SMOKE_REFERENCE_INVALID","Successful approved Smoke attempt-001 is required",status=409)
    job=create_job({"dataset_version":source["dataset_version"],"model_id":source["model_config"]["id"],"training_config":source["training_config"],"runtime_target":source["runtime_target"]})
    total=int(job["calculated_steps"]["estimated_total_optimizer_steps"]); job["training_config"]["save_steps"]=max(1,total//2); job["calculated_steps"]=calculate_plan(int(job["dataset_counts"]["training"]),job["training_config"])
    job["provenance"]={"created_by":"NajdiLab Phase 2-C","derived_from_job":source_job_id,"reason":"production_full_training_after_successful_smoke","smoke_reference":{"job_id":source_job_id,"attempt_id":"attempt-001"},"execution_started":False}
    job["production_mode"]=True; _atomic_json(_job_path(job["job_id"]),job); return job


def update_job(job_id: str, data: dict[str, Any]) -> dict[str, Any]:
    job = get_job(job_id)
    if job["status"] != "DRAFT": raise TrainingControlError("JOB_NOT_EDITABLE", "يمكن تعديل DRAFT فقط", status=409)
    allowed = {"dataset_version", "model_id", "training_config", "runtime_target"}
    merged = {"dataset_version": data.get("dataset_version", job["dataset_version"]), "model_id": data.get("model_id", job["model_config"]["id"]),
        "training_config": data.get("training_config", job["training_config"]), "runtime_target": data.get("runtime_target", job["runtime_target"])}
    if not set(data) <= allowed: raise TrainingControlError("INVALID_TRAINING_CONFIG", "حقول تحديث غير مسموحة")
    fresh = create_job_snapshot(merged, job_id, job["created_at"]); _atomic_json(_job_path(job_id), fresh); return fresh


def create_job_snapshot(data: dict[str, Any], job_id: str, created_at: str) -> dict[str, Any]:
    preflight = training_preflight(data); now = _now()
    return {"job_id": job_id, "created_at": created_at, "updated_at": now, "status": "DRAFT", "dataset_version": preflight["dataset"]["dataset"],
        "dataset_fingerprint": preflight["dataset"].get("dataset_fingerprint"), "dataset_counts": preflight["dataset"].get("dataset_counts"), "quality_gate_result": preflight["dataset"],
        "model_config": preflight["model"], "training_config": preflight["training_config"], "runtime_target": preflight["runtime_target"], "calculated_steps": preflight["training_plan"],
        "vram_estimate": preflight["vram_estimate"], "warnings": preflight["dataset"].get("warnings", []), "acknowledged_warnings": None,
        "output_directory": f"/home/najdi/najdi-training/outputs/{job_id}", "checkpoint_directory": f"/home/najdi/najdi-training/checkpoints/{job_id}", "logs_path": f"/home/najdi/najdi-training/logs/{job_id}.log",
        "provenance": {"created_by": "NajdiLab Phase 2-A", "execution_started": False}}


def mark_job_ready(job_id: str, data: dict[str, Any]) -> dict[str, Any]:
    job = get_job(job_id)
    if job["status"] != "DRAFT": raise TrainingControlError("JOB_NOT_EDITABLE", "Job ليس DRAFT", status=409)
    gate = quality_gate(job["dataset_version"])
    if gate["status"] in {"BLOCKED", "UNAVAILABLE"}: raise TrainingControlError("QUALITY_GATE_BLOCKED", "Quality Gate يمنع READY", status=409)
    if gate["dataset_fingerprint"] != job["dataset_fingerprint"]: raise TrainingControlError("STALE_DATASET_FINGERPRINT", "Dataset تغير منذ إنشاء Job", status=409)
    current_model = get_model(str((job.get("model_config") or {}).get("id") or ""))
    if current_model.get("validation_status") != "VALID" or current_model.get("excluded"):
        raise TrainingControlError("MODEL_NOT_VALIDATED", "تحقق توافق النموذج غير ناجح", status=409)
    if current_model.get("fingerprint") != (job.get("model_config") or {}).get("fingerprint"):
        raise TrainingControlError("STALE_MODEL_VALIDATION", "تغير تعريف النموذج منذ إنشاء المهمة", status=409)
    acknowledged = bool(data.get("acknowledge_warnings"))
    if gate["warnings"] and not acknowledged: raise TrainingControlError("WARNING_ACK_REQUIRED", "يجب الإقرار بالتحذيرات قبل READY", status=409)
    job["status"] = "READY"; job["updated_at"] = _now(); job["quality_gate_result"] = gate; job["model_config"] = current_model
    job["acknowledged_warnings"] = {"acknowledged": acknowledged, "timestamp": job["updated_at"], "codes": [item.get("code") for item in gate["warnings"]]} if acknowledged else None
    _atomic_json(_job_path(job_id), job); return job


def cancel_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job["status"] not in {"DRAFT", "READY"}: raise TrainingControlError("JOB_NOT_EDITABLE", "لا يمكن إلغاء Job بهذه الحالة", status=409)
    job["status"] = "CANCELLED"; job["updated_at"] = _now(); _atomic_json(_job_path(job_id), job); return job
