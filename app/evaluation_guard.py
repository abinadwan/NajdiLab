from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class EvaluationGuardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message); self.code = code


def verify_adapter_evaluation(config: dict[str, Any], load_evidence: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless the requested adapter is demonstrably active and distinct from Base."""
    base = str(config.get("base_model_id") or "").strip()
    adapter = str(config.get("adapter_path") or "").strip()
    if not base or not adapter:
        raise EvaluationGuardError("EXPLICIT_MODELS_REQUIRED", "The base model and adapter must be specified explicitly")
    requested_revision = str(config.get("adapter_revision") or "").strip()
    loaded_path = str(load_evidence.get("loaded_adapter_path") or "").strip()
    active = bool(load_evidence.get("adapter_active"))
    if not active or Path(loaded_path).resolve() != Path(adapter).resolve():
        raise EvaluationGuardError("ADAPTER_FALLBACK_DETECTED", "Loading the requested adapter has not been established; stop evaluation to prevent a misleading comparison")
    loaded_revision = str(load_evidence.get("adapter_revision") or "").strip()
    if requested_revision and loaded_revision != requested_revision:
        raise EvaluationGuardError("ADAPTER_REVISION_MISMATCH", "The loaded adapter revision does not match the requested revision")
    if load_evidence.get("base_output_fingerprint") and load_evidence.get("base_output_fingerprint") == load_evidence.get("adapter_output_fingerprint"):
        raise EvaluationGuardError("ADAPTER_IDENTITY_UNVERIFIED", "Unable to establish that the adapter path differs from the base model")
    payload = {"base_model_id": base, "adapter_path": str(Path(adapter).resolve()), "adapter_revision": loaded_revision,
               "dataset_version": config.get("dataset_version"), "run_id": config.get("run_id"),
               "inference": config.get("inference") or {}}
    return {"status": "VERIFIED", "adapter_fallback": False, "evaluation_fingerprint": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), **payload}
