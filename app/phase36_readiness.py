from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .phase3_review import REPORTS_ROOT, RUN_ID, _atomic, _now, _sha

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_VERSION = "gold-v008-split-clean"
ATTEMPT = "attempt-002"

CLUSTER_PLAN: dict[str, dict[str, str]] = {
    "instruction_following": {"layer": "training data", "remediation": "SFT and Multi-turn examples with explicit, machine-checkable instructions", "support": "SUPPORTED"},
    "context_understanding": {"layer": "training data", "remediation": "Multi-turn examples with materially varied contexts", "support": "SUPPORTED"},
    "verbosity_concision": {"layer": "data + inference", "remediation": "Concise SFT targets plus bounded generation experiments", "support": "PARTIAL"},
    "unnatural_arabic": {"layer": "training data + review", "remediation": "Native-reviewed Saudi Arabic SFT/Multi-turn examples", "support": "SUPPORTED"},
    "tool_behavior": {"layer": "runtime/controller + training", "remediation": "Implement an authoritative tool contract before first-class tool examples", "support": "BLOCKED"},
    "saudi_najdi_dialect": {"layer": "training data + balancing", "remediation": "Native-reviewed SFT/Multi-turn coverage balanced across intents", "support": "SUPPORTED"},
    "repetition_degeneration": {"layer": "data + inference", "remediation": "Non-repetitive targets and a controlled decoding matrix", "support": "PARTIAL"},
    "hallucination": {"layer": "data + runtime grounding", "remediation": "Grounded SFT plus authoritative tool-result enforcement", "support": "PARTIAL"},
    "conversational_continuity": {"layer": "training data", "remediation": "Multi-turn state and constraint carry-forward examples", "support": "SUPPORTED"},
    "capability_misunderstanding": {"layer": "system prompt + tool registry + controller", "remediation": "Versioned capability disclosure and permission/error states", "support": "BLOCKED"},
    "fabricated_tool_execution": {"layer": "runtime/controller", "remediation": "Disallow execution claims without a verified tool-result event", "support": "BLOCKED"},
    "factual_accuracy": {"layer": "data + retrieval/runtime", "remediation": "Grounded static SFT and verified retrieval for changing facts", "support": "PARTIAL"},
    "constraint_following": {"layer": "training data", "remediation": "SFT/Multi-turn examples with positive and negative constraints", "support": "SUPPORTED"},
    "insufficient_evidence": {"layer": "evidence", "remediation": "Collect additional annotation before prescribing remediation", "support": "NOT_APPLICABLE"},
}

COVERAGE = {
    "instruction_following": 12, "context_understanding": 10, "verbosity_concision": 8,
    "unnatural_arabic": 8, "tool_behavior": 8, "saudi_najdi_dialect": 8,
    "repetition_degeneration": 6, "hallucination": 8, "conversational_continuity": 8,
    "capability_misunderstanding": 8, "fabricated_tool_execution": 6, "factual_accuracy": 6,
    "constraint_following": 6, "insufficient_evidence": 0,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _record_types(manifest: dict[str, Any], staged: set[str]) -> list[dict[str, Any]]:
    files = manifest["files"]
    return [
        {"record_type": "SFT", "file": "sft.jsonl", "count": files["sft.jsonl"], "exists_in_schema": True, "health_validated": True, "consumed": "sft.jsonl" in staged, "gradient_updates": "sft.jsonl" in staged, "chat_template_support": "VERIFIED_TEXT_MESSAGES", "future_remediation": "SAFE_WITH_LEAKAGE_CHECKS", "gap": None},
        {"record_type": "Multi-turn", "file": "multi_turn.jsonl", "count": files["multi_turn.jsonl"], "exists_in_schema": True, "health_validated": True, "consumed": "multi_turn.jsonl" in staged, "gradient_updates": "multi_turn.jsonl" in staged, "chat_template_support": "VERIFIED_TEXT_MESSAGES", "future_remediation": "SAFE_WITH_LEAKAGE_CHECKS", "gap": None},
        {"record_type": "Direct Language", "file": "direct_language.jsonl", "count": files["direct_language.jsonl"], "exists_in_schema": True, "health_validated": True, "consumed": False, "gradient_updates": False, "chat_template_support": "NOT_EXERCISED", "future_remediation": "ONLY_AFTER_TRANSFORMATION_OR_LOADER_SUPPORT", "gap": "Not staged and has no production trainer argument."},
        {"record_type": "Preference/DPO", "file": "preference_pairs.jsonl", "count": files["preference_pairs.jsonl"], "exists_in_schema": True, "health_validated": True, "consumed": False, "gradient_updates": False, "chat_template_support": "NOT_EXERCISED", "future_remediation": "BLOCKED_UNTIL_PREFERENCE_PIPELINE_EXISTS", "gap": "No DPO/ORPO trainer stage, staging rule, loss contract, or promotion gate."},
        {"record_type": "Evaluation", "file": "text_sft_eval.jsonl + tool_eval.jsonl", "count": files["text_sft_eval.jsonl"] + files["tool_eval.jsonl"], "exists_in_schema": True, "health_validated": True, "consumed": False, "gradient_updates": False, "chat_template_support": "BENCHMARK_TEXT_ONLY", "future_remediation": "PROHIBITED_HOLDOUT", "gap": "Must remain immutable and excluded from training."},
        {"record_type": "Native tool-use", "file": None, "count": 0, "exists_in_schema": False, "health_validated": False, "consumed": False, "gradient_updates": False, "chat_template_support": "UNVERIFIED", "future_remediation": "BLOCKED_UNTIL_IMPLEMENTED", "gap": "No first-class tool schema, tools argument, tool-call/result serialization validation, or controller-backed trainer path."},
    ]


def _generation(base: dict[str, Any], adapter: dict[str, Any]) -> dict[str, Any]:
    base_cfg = base.get("generation", {})
    adapter_cfg = adapter.get("generation", {})
    return {
        "identical_base_adapter": base_cfg == adapter_cfg,
        "base": base_cfg,
        "adapter": adapter_cfg,
        "effective_audit": {
            "max_new_tokens": base_cfg.get("max_new_tokens"), "do_sample": base_cfg.get("do_sample"),
            "temperature": "not set; irrelevant while do_sample=false", "top_p": "not set; irrelevant while do_sample=false",
            "top_k": "not set; irrelevant while do_sample=false", "repetition_penalty": "not set (library default)",
            "frequency_penalty": "not applicable/not set", "presence_penalty": "not applicable/not set",
            "eos": "tokenizer EOS passed to generate; PAD set to EOS", "stop_tokens": "no additional stop strings/tokens",
            "chat_template": "same tokenizer template; add_generation_prompt=true", "bos_eos": "delegated to chat template; tokenization uses add_special_tokens=false",
            "timeout": "no per-generation timeout", "tool_call_stopping": "not implemented",
        },
        "assessment": "The comparison was fair because settings were identical. A 384-token ceiling with no repetition penalty or extra stop condition can amplify an already-degenerate continuation, but does not by itself prove a training cause. Preserve history and run a controlled decoding matrix only on a future candidate.",
    }


def build_readiness(run_id: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid Phase 3 run id")
    report_root = REPORTS_ROOT / run_id
    review_path = report_root / "human-review.json"
    failure_path = report_root / "failure-analysis.json"
    dataset_path = PROJECT_ROOT / "exports" / DATASET_VERSION / "manifest.json"
    execution_path = PROJECT_ROOT / "training" / "jobs" / "train-20261006-001" / "attempts" / ATTEMPT / "execution-manifest.json"
    result_path = execution_path.with_name("result.json")
    base_meta_path = report_root / "base-benchmark.meta.json"
    adapter_meta_path = report_root / "adapter-benchmark.meta.json"
    review, failure, manifest, execution, result = map(_load, (review_path, failure_path, dataset_path, execution_path, result_path))
    base_meta, adapter_meta = _load(base_meta_path), _load(adapter_meta_path)
    if review.get("final_gate", {}).get("final_decision") != "REJECT" or review.get("summary", {}).get("reviewed") != 24:
        raise ValueError("readiness audit requires the completed 24-case REJECT decision")
    if manifest.get("state") != "Frozen" or manifest.get("version") != DATASET_VERSION:
        raise ValueError("source dataset must remain the expected Frozen version")
    staged = set(execution["staged_dataset"]["manifest"]["staged_files"])
    types = _record_types(manifest, staged)
    trained = {x["record_type"]: x["count"] for x in types if x["gradient_updates"]}
    adapter_result = result.get("adapter_result", result)
    if trained != {"SFT": 12, "Multi-turn": 18} or adapter_result.get("training_records") != 30:
        raise ValueError("attempt-002 consumption evidence does not match 12 SFT + 18 Multi-turn")
    failure_clusters = failure["summary"]["failure_count_per_root_cause_cluster"]
    severity = failure["summary"]["severity_per_cluster"]
    matrix=[]
    for cluster, plan in CLUSTER_PLAN.items():
        matrix.append({"cluster": cluster, "observed_regressions": failure_clusters.get(cluster, 0), "severity": severity.get(cluster, {}), "primary_suspected_layer": plan["layer"], "recommended_remediation": plan["remediation"], "currently_supported": plan["support"], "required_implementation_work": ({"SUPPORTED": "No new trainer mechanism; add provenance, leakage gates, balancing, and validation.", "PARTIAL": "Add the missing runtime/inference validation before relying on data alone.", "BLOCKED": "Implement and test the platform contract before generating records for this mechanism.", "NOT_APPLICABLE": "Obtain evidence first."})[plan["support"]], "validation_method": "Fresh independent holdout plus original Phase 3 regression benchmark; tool clusters additionally require controller event assertions."})
    return {
        "schema_version": 1, "stage": "Phase 3.6 — Remediation Readiness Audit", "generated_at": _now(),
        "phase3_run_id": run_id, "production_attempt": "train-20261006-001/attempt-002",
        "gates": {"phase3_final_decision": "REJECT", "phase35": "COMPLETE", "phase36": "COMPLETE", "phase4a": "BLOCKED", "retraining_started": False, "v009_created": False, "dataset_mutated": False, "rejected_adapter_preserved": True},
        "evidence": {"human_review_sha256": _sha(review_path), "failure_analysis_sha256": _sha(failure_path), "dataset_manifest_sha256": _sha(dataset_path), "execution_manifest_sha256": _sha(execution_path), "result_sha256": _sha(result_path), "dataset_fingerprint": execution["dataset_fingerprint"], "adapter_sha256": execution.get("adapter_sha256")},
        "production_pipeline": {"trained_records": trained, "total": sum(trained.values()), "record_types": types, "preference_optimization": {"dpo": False, "orpo": False, "assessment": "Preference assets contribute no gradient updates in attempt-002. Installed/cache trainer classes are not a configured production stage."}, "rendering": {"loss_scope": "final assistant textual target only", "mask_strategy": "rendered_template_offsets (or tokenizer generation mask when available)", "tools_argument_supplied": False, "structured_tool_calls_verified": False, "structured_tool_results_verified": False, "adapter_preserves_tool_structure": "UNPROVEN"}},
        "tool_contract": {"overall": "NOT_READY_FOR_NATIVE_TOOL_REMEDIATION", "system_prompt": "No benchmark-wide authoritative capability contract was injected.", "registry": "No production tool registry is connected to the Phase 3 harness.", "schemas": "No tool schemas are passed to the model chat template.", "serialization": "Tool calls/results are not validated as first-class events.", "availability_behavior": "No controller-enforced available/unavailable/permission-gated state.", "authority": "No authoritative tool-result channel; the harness cannot prevent textual execution claims.", "benchmark": "The three tool cases are text-generation cases; no tool is registered or executed.", "failure_attribution": [
            {"failure": "refusing an available tool", "primary_cause": "F_MIXED", "details": "Training behavior is implicated, but the benchmark does not expose an executable tool contract."},
            {"failure": "claiming execution without execution", "primary_cause": "F_MIXED", "details": "Training behavior plus missing controller enforcement."},
            {"failure": "fabricating terminal output", "primary_cause": "D_RUNTIME_CONTROLLER", "details": "A controller must make verified results authoritative; training remains a secondary safeguard."},
            {"failure": "returning placeholders", "primary_cause": "F_MIXED", "details": "Instruction behavior and absent harness execution path both contribute."},
            {"failure": "misunderstanding local-device boundaries", "primary_cause": "F_MIXED", "details": "Requires an explicit system capability contract, schemas, permission state, and matching training."},
            {"failure": "sandbox/runtime/device confusion", "primary_cause": "F_MIXED", "details": "The model needs runtime-supplied boundaries; static training alone cannot establish current capabilities."},
        ]},
        "generation_audit": _generation(base_meta, adapter_meta),
        "remediation_support_matrix": matrix,
        "unique_dataset_plan": {"method": "Coverage-set sizing: each record has one primary skill and may cover up to three compatible secondary skills; tool cases remain separate and are not relabelled as plain SFT support.", "minimum_defensible_unique_records": 28, "recommended_unique_records": 36, "minimum_breakdown": {"SFT": 10, "Multi-turn": 12, "Native tool-use": 6, "Preference/DPO_effective_next_SFT_run": 0}, "recommended_breakdown": {"SFT": 12, "Multi-turn": 16, "Native tool-use": 8, "Preference/DPO_effective_next_SFT_run": 0}, "implementation_note": "Only the SFT and Multi-turn portions are trainable today. Native tool-use records must wait for the tool pipeline. Preference pairs must not be credited unless a separate preference stage is implemented and gated.", "coverage_per_cluster": COVERAGE, "overload_guard": "Do not assign more than one primary and three compatible secondary objectives to one example."},
        "contamination_design": {"protected_sources": ["Phase 3 prompts", "Phase 3 gold answers", "Phase 3 Base outputs", "Phase 3 Adapter outputs"], "checks": [
            {"kind": "exact", "method": "SHA-256 over canonical serialized text fields."},
            {"kind": "normalized", "method": "Unicode NFKC, Arabic diacritic/tatweel normalization, whitespace and punctuation normalization, then hash comparison."},
            {"kind": "near_duplicate", "method": "Arabic-aware token and character n-gram similarity with conservative thresholds and surfaced candidate pairs."},
            {"kind": "conversation_overlap", "method": "Compare complete-turn fingerprints, conversation/provenance IDs, ordered n-grams, and distinctive entity combinations."},
            {"kind": "semantic_manual_review", "method": "Blind human review of every flagged pair for trivial paraphrase or reused unique details; no automatic destructive filtering."},
        ], "prohibitions": ["No exact prompt, gold answer, Base output, or Adapter output.", "No trivial paraphrase.", "No reuse of the same unique entities/details in a slightly rearranged scenario."], "acceptance": "Candidate v009 cannot be frozen until exact/normalized overlap is zero and all near-semantic flags are resolved and documented."},
        "future_evaluation": {"A_original_phase3": {"purpose": "Immutable regression comparison only", "training_access": "PROHIBITED"}, "B_fresh_remediation_holdout": {"purpose": "Test the same categories with unseen wording, entities, scenarios, and conversation structures", "independence": "Created by a separate workflow after training data is locked; zero author/reuse path from training examples."}, "C_general_capability_sanity": {"purpose": "Detect damage to unrelated instruction, Arabic, factual, safety, and conversation abilities", "independence": "Unrelated balanced cases, preserved before candidate evaluation."}},
        "required_platform_changes_before_v009": ["Implement and test a versioned runtime capability/tool registry and schema injection.", "Define first-class tool-call and tool-result serialization, tokenizer rendering, assistant-loss masks, and controller execution events.", "Make verified tool results authoritative and reject unbacked execution claims in runtime validation.", "Upgrade the tool benchmark from text-only generation to controller-backed execution tests.", "Either implement a gated DPO/ORPO stage or remove Preference/DPO from the effective remediation count.", "Add the contamination gate covering prompts, gold answers, and both model outputs.", "Define a controlled generation experiment for repetition/verbosity without rewriting Phase 3 history."],
    }


def _markdown(r: dict[str, Any]) -> str:
    lines = ["# Phase 3.6 — Remediation Readiness Audit", "", f"Generated: `{r['generated_at']}`", "", "## Decision", "", "Phase 3 remains **REJECT**. Phase 3.5 and Phase 3.6 are **COMPLETE**. Phase 4A is **BLOCKED**. No retraining or dataset mutation occurred, no v009 was created, and the rejected Adapter is preserved.", "", "## Actual production consumption", "", "| Type | Count | Health | Trainer | Gradient | Template/tool support | Future use |", "|---|---:|---|---|---|---|---|"]
    for x in r["production_pipeline"]["record_types"]:
        lines.append(f"| {x['record_type']} | {x['count']} | {x['health_validated']} | {x['consumed']} | {x['gradient_updates']} | {x['chat_template_support']} | {x['future_remediation']} |")
    lines += ["", "Only **12 SFT + 18 Multi-turn = 30** records contributed gradients. Direct Language and Preference/DPO are assets only. There is no DPO/ORPO stage.", "", "## Tool contract", "", f"Status: **{r['tool_contract']['overall']}**", "", f"{r['tool_contract']['benchmark']} {r['tool_contract']['authority']}", "", "| Failure class | Attribution | Finding |", "|---|---|---|"]
    for x in r["tool_contract"]["failure_attribution"]: lines.append(f"| {x['failure']} | {x['primary_cause']} | {x['details']} |")
    g=r["generation_audit"]
    lines += ["", "## Generation audit", "", f"Base/Adapter settings identical: **{g['identical_base_adapter']}**. Configuration: `{g['base']}`.", "", g["assessment"], "", "## Remediation support matrix", "", "| Cluster | Cases | Severity | Layer | Remediation | Support |", "|---|---:|---|---|---|---|"]
    for x in r["remediation_support_matrix"]: lines.append(f"| {x['cluster']} | {x['observed_regressions']} | {x['severity']} | {x['primary_suspected_layer']} | {x['recommended_remediation']} | {x['currently_supported']} |")
    p=r["unique_dataset_plan"]
    lines += ["", "## Unique remediation sizing", "", f"- Minimum defensible: **{p['minimum_defensible_unique_records']}** — `{p['minimum_breakdown']}`", f"- Recommended: **{p['recommended_unique_records']}** — `{p['recommended_breakdown']}`", f"- {p['implementation_note']}", "", "These are unique records, not a sum of overlapping cluster recommendations. Coverage targets: ", "", f"`{p['coverage_per_cluster']}`", "", "## Leakage prevention", ""]
    lines += [f"- {x}" for x in r["contamination_design"]["prohibitions"]]
    lines += ["", "Required checks: exact hashes, Arabic-aware normalized hashes, near-duplicate similarity, conversation-level overlap, and explicit blinded semantic review. Filtering is not destructive or automatic.", "", "## Future evaluation", "", "- A: preserve the original Phase 3 benchmark for regression comparison only.", "- B: create a fresh independent remediation holdout after training data is locked.", "- C: run an unrelated general-capability sanity benchmark.", "", "## Required platform changes before v009", ""]
    lines += [f"- {x}" for x in r["required_platform_changes_before_v009"]]
    return "\n".join(lines) + "\n"


def write_readiness(run_id: str) -> tuple[Path, Path, dict[str, Any]]:
    report = build_readiness(run_id)
    root = REPORTS_ROOT / run_id
    json_path, md_path = root / "remediation-readiness.json", root / "remediation-readiness.md"
    _atomic(json_path, report)
    tmp = md_path.with_name(f".{md_path.name}.tmp")
    tmp.write_text(_markdown(report), encoding="utf-8")
    tmp.replace(md_path)
    return json_path, md_path, report


if __name__ == "__main__":
    write_readiness("phase3-train-20261006-001")
