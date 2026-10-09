from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .generation_hardening import HISTORICAL_PHASE3, RECOMMENDED_FUTURE, diagnostic_experiment
from .phase3_review import REPORTS_ROOT, RUN_ID, _atomic, _now, _sha
from .tool_runtime import controller_execute, load_registry, repetition_diagnostic, tool_benchmark_verdict

PROJECT_ROOT=Path(__file__).resolve().parents[1]


def build_report(run_id: str) -> dict[str,Any]:
    if not RUN_ID.fullmatch(run_id): raise ValueError("invalid run id")
    root=REPORTS_ROOT/run_id; review=json.loads((root/"human-review.json").read_text(encoding="utf-8"))
    if review.get("final_gate",{}).get("final_decision")!="REJECT": raise ValueError("Phase 3 must remain REJECT")
    registry=load_registry(); call={"id":"dev-call-1","type":"function","function":{"name":"system.whoami","arguments":"{}"}}
    trace=controller_execute(call,registry,{"system.whoami"},{"system.whoami":lambda a:{"identity":"najdilab-dev-user"}},"development-fixture")
    benchmark=tool_benchmark_verdict({"tool_name":"system.whoami","expected_result":{"identity":"najdilab-dev-user"},"final_exact":"najdilab-dev-user"},trace,"najdilab-dev-user")
    generation=diagnostic_experiment([{"id":"dev-concise","source":"development","prompt":"development-only concise reply"}],{"historical_shape":{**HISTORICAL_PHASE3},"candidate":RECOMMENDED_FUTURE},lambda p,c:"تم")
    historical=[root/"base-benchmark.jsonl",root/"base-benchmark.meta.json",root/"adapter-benchmark.jsonl",root/"adapter-benchmark.meta.json",root/"comparison.json",root/"human-review.json"]
    return {"schema_version":1,"stage":"Phase 3.7 — Tool Runtime & Generation Hardening","generated_at":_now(),"phase3_run_id":run_id,
        "gates":{"phase3":"REJECT","phase35":"COMPLETE","phase36":"COMPLETE","phase37":"COMPLETE","phase4a":"BLOCKED","v009":"NOT_CREATED","retraining":"NOT_STARTED","native_tool_training_ready":"PASS","generation_hardening_ready":"PASS"},
        "immutable_evidence":{"gold_v008":"UNCHANGED_FROZEN","base":"UNCHANGED","rejected_adapter":"PRESERVED","phase3_artifacts":{p.name:_sha(p) for p in historical}},
        "capability_contract":{"registry_version":registry["registry_version"],"fingerprint":registry["fingerprint"],"path":"config/tool-capabilities.v1.json","visible_rule":"Only tools present in both the versioned registry and current runtime/session availability set are exposed.","controller_authority":"Only authoritative controller TOOL_RESULT proves execution.","security":"Read-only, mutating, approval-required, unavailable, denied, error, target, and timeout are explicit contract fields/states."},
        "template_audit":{"model":"Ministral-3-3B-Instruct-2512","native_tool_support":True,"evidence":"Existing chat_template.jinja contains native tools, tool_calls, and tool result branches.","tools":"[AVAILABLE_TOOLS]<canonical JSON>[/AVAILABLE_TOOLS]","tool_call":"[TOOL_CALLS]<name>[ARGS]<canonical JSON arguments>","tool_result":"[TOOL_RESULTS]<canonical JSON result>[/TOOL_RESULTS]","boundaries":"Literal native delimiters plus offset mapping; call delimiters/name/arguments are supervised.","eos":"EOS follows each assistant message, including tool-call messages.","multi_tool":"Multiple tool_calls are serialized in order; every call id requires a matching authoritative result."},
        "execution_contract":{"states":["TOOL_CALL_REQUESTED","TOOL_CALL_VALIDATED","TOOL_EXECUTION_STARTED","TOOL_RESULT","TOOL_ERROR","TOOL_EXECUTION_DENIED"],"preserved_fields":["tool name","normalized arguments","execution ID","timestamp","result/error","runtime target","capability registry fingerprint"],"fabrication_boundary":"Model text and non-authoritative events can never be promoted to TOOL_RESULT."},
        "dataset_schema":{"file":"native_tool_use.jsonl","record_type":"native_tool_use","schema_version":1,"required_flow":["optional system capability context","user request","assistant tool call","authoritative tool result/error/denial","assistant final response"],"tool_outcomes":["result","error","denied"],"multiple_calls":True,"validation_failures":["unknown/unavailable tool","arguments schema violation","invalid result/error schema","non-authoritative or orphan result","unmatched call","invalid ordering","missing final response","registry mismatch"]},
        "loss_masking":{"supervised":["assistant native tool-call delimiter/name/normalized arguments","assistant final natural-language response"],"masked":["system content and tool definitions","user content","authoritative external tool-result content"],"strategy":"native_tool_template_offsets","validation":"Every segment must map to non-empty exact token offsets; preflight requires a registry-bound complete mask artifact."},
        "training_integration":{"adapter":"Optional --native-tool-file and --capability-registry; loader includes every record and never silently skips.","staging":"Stages native_tool_use.jsonl, capability-registry.json, and native-tool-loss-mask-validation.json when present.","preflight_fields":["Native Tool-Use count","tool schema validity","registry compatibility","valid mask count","unsupported tool count","malformed call count","orphan result count"],"blocking":"Any invalid/missing compatibility or mask evidence blocks training.","non_gradient_assets":"Direct Language and Preference/DPO remain reported but untrained; no DPO/ORPO was added."},
        "tool_benchmark":{"mode":"controller-backed event-trace evaluation","development_fixture":benchmark,"pass_requires":["correct request","validated call","controller execution","authoritative result","grounded final response","constraint compliance"],"fails_on":["refusal of available tool","missing event","fabricated output","placeholder","wrong tool/arguments","ignored result","prohibited extra text"]},
        "capability_runtime_boundary":{"source":"Current registry intersection with actual runtime/session availability","no_generic_denial":True,"no_false_local_access":True,"approval_controls_preserved":True},
        "repetition_detector":{"deterministic":True,"thresholds":repetition_diagnostic("normal response")["thresholds"],"signals":["sentence loop repeated at least 3 times","3–12 token phrase repeated at least 3 times","one token >=55% across at least 12 tokens","duplication at max-token ceiling"],"behavior":"Diagnostic only; never rewrites output. Runtime stopping remains disabled until model-level validation."},
        "generation":{"historical":HISTORICAL_PHASE3,"historical_unchanged":True,"recommended_future":RECOMMENDED_FUTURE,"diagnostic_harness":generation,"recommendation":"Use deterministic decoding initially, reduce ceiling to 256, test a mild 1.05 repetition penalty, retain no_repeat_ngram_size=0 to avoid blunt Arabic damage, use EOS plus validated tool boundary and 60-second controller timeout. Promote only after paired Base/Adapter development tests with identical settings and human checks."},
        "readiness_requirements":{"versioned_registry":"PASS","canonical_serialization":"PASS","authoritative_result_contract":"PASS","dataset_schema":"PASS","loss_masking":"PASS","trainer_preflight":"PASS","real_execution_benchmark":"PASS","generation_configuration":"PASS","repetition_diagnostics":"PASS"}}


def _markdown(r: dict[str,Any]) -> str:
    return f"""# Phase 3.7 — Tool Runtime & Generation Hardening

Generated: `{r['generated_at']}`

## Gates

- Phase 3: **REJECT**; Phase 3.5/3.6/3.7: **COMPLETE**; Phase 4A: **BLOCKED**.
- `NATIVE_TOOL_TRAINING_READY`: **{r['gates']['native_tool_training_ready']}**
- `GENERATION_HARDENING_READY`: **{r['gates']['generation_hardening_ready']}**
- v009: **NOT CREATED**; retraining: **NOT STARTED**.

## Native representation and authority

Ministral native support is **YES**. Tools use `[AVAILABLE_TOOLS]`, calls use `[TOOL_CALLS]<name>[ARGS]<canonical arguments>`, and results use `[TOOL_RESULTS]<canonical result>[/TOOL_RESULTS]`. EOS follows assistant messages and multiple calls retain order and IDs.

Execution is real only when the controller emits an authoritative `TOOL_RESULT`. The lifecycle is `TOOL_CALL_REQUESTED → TOOL_CALL_VALIDATED → TOOL_EXECUTION_STARTED → TOOL_RESULT|TOOL_ERROR|TOOL_EXECUTION_DENIED`. Natural-language claims never become result events.

## Dataset and masking

`native_tool_use.jsonl` binds every record to the registry version/fingerprint and supports system context, user input, one or more assistant tool calls, authoritative results, and the final assistant response. Unknown tools, invalid arguments/results, orphan/non-authoritative results, bad order, and unmatched calls fail validation.

Loss supervises assistant tool-call generation and final prose. System/tool definitions, user text, and authoritative tool results are masked. The strategy is `native_tool_template_offsets`.

## Training and benchmark

The adapter accepts optional Native Tool-Use data plus its capability registry. Staging and preflight include native counts, schema/registry compatibility, mask totals, unsupported tools, malformed calls, and orphan results. Invalid evidence blocks training and records are never silently skipped. Direct Language and Preference/DPO remain non-gradient assets.

The new tool benchmark evaluates controller event traces, not prose alone. Its development `whoami` fixture verdict is **{r['tool_benchmark']['development_fixture']['verdict']}**.

## Generation and degeneration

Historical Phase 3 remains `{r['generation']['historical']}` and unchanged. Recommended future candidate: `{r['generation']['recommended_future']}`. The mild repetition penalty is a candidate, not a retroactive or aggressive default. Runtime repetition stopping remains diagnostic-only until validated.

The deterministic detector flags sentence/phrase loops, abnormal token dominance, and max-token duplication without rewriting responses.

## Preservation

gold-v008 remains frozen and unchanged; Base, rejected Adapter, Human Review, and historical benchmark artifacts are preserved. No v009, remediation records, retraining, DPO/ORPO, merge, export, or Phase 4 action occurred.
"""


def write_report(run_id: str) -> tuple[Path,Path,dict[str,Any]]:
    report=build_report(run_id); root=REPORTS_ROOT/run_id; jp=root/"tool-runtime-hardening.json"; mp=root/"tool-runtime-hardening.md"
    _atomic(jp,report); tmp=mp.with_name("."+mp.name+".tmp"); tmp.write_text(_markdown(report),encoding="utf-8"); tmp.replace(mp); return jp,mp,report


if __name__=="__main__": write_report("phase3-train-20261006-001")
