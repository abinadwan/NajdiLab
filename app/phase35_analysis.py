from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .phase3_review import REPORTS_ROOT, RUN_ID, _atomic, _now, _sha

CLUSTER_RULES = {
    "tool_behavior": lambda r: "tool_behavior" in r["error_tags"],
    "hallucination": lambda r: "hallucination" in r["error_tags"],
    "instruction_following": lambda r: "instruction_following" in r["error_tags"],
    "constraint_following": lambda r: "constraint_failure" in r["error_tags"],
    "context_understanding": lambda r: "context_failure" in r["error_tags"],
    "saudi_najdi_dialect": lambda r: "dialect_issue" in r["error_tags"],
    "unnatural_arabic": lambda r: "unnatural_arabic" in r["error_tags"],
    "repetition_degeneration": lambda r: "repetition" in r["error_tags"],
    "factual_accuracy": lambda r: "factual_error" in r["error_tags"],
    "verbosity_concision": lambda r: "verbosity" in r["error_tags"],
    "conversational_continuity": lambda r: r.get("category") == "context_following" and "context_failure" in r["error_tags"],
    "capability_misunderstanding": lambda r: "tool_behavior" in r["error_tags"] and any(x in r.get("notes","") for x in ("قدرة", "يستطيع", "صلاحيات", "ينفذ", "تنفيذ", "أداة")),
    "fabricated_tool_execution": lambda r: "tool_behavior" in r["error_tags"] and any(x in r.get("notes","") for x in ("يفبرك", "اختلاق", "افتراضية", "هلوسة", "غير موثوق")),
}

PRIMARY_PRIORITY = (
    "tool_behavior", "fabricated_tool_execution", "capability_misunderstanding", "hallucination",
    "constraint_following", "context_understanding", "instruction_following", "repetition_degeneration",
    "factual_accuracy", "saudi_najdi_dialect", "unnatural_arabic", "verbosity_concision",
)

REMEDIATION = {
    "tool_behavior": ("C/D", "Tool-use", "Execute available tools through the declared schema and return grounded results.", "Refusal, simulation, or manual instructions when an available tool should be called.", "hard", "Authoritative runtime tool schema and execution traces."),
    "fabricated_tool_execution": ("C/D/E", "Tool-use + Preference/DPO", "Never claim a tool ran unless a verified runtime result exists.", "Invented command output, prices, searches, calls, or administrative actions.", "hard", "Verified tool results and explicit no-result/error states."),
    "capability_misunderstanding": ("D/C", "Tool-use", "Accurately distinguish available, unavailable, and permission-gated capabilities.", "False capability claims or refusals of capabilities actually exposed by the runtime.", "hard", "Versioned runtime capability registry and tool schema."),
    "hallucination": ("A/E/D", "SFT + Preference/DPO", "State uncertainty and obtain evidence before making changing or external claims.", "Unsupported entities, events, prices, permissions, or results.", "hard", "Trusted supplied context or verified tool output."),
    "instruction_following": ("A/B", "SFT + Multi-turn", "Follow the requested action, format, and response boundary directly.", "Ignoring the requested action or answering a different task.", "medium", "Human-authored task constraints independent of evaluation wording."),
    "constraint_following": ("A/B", "SFT + Multi-turn", "Honor ordering, format, and explicit negative constraints.", "Adding forbidden prefixes, content, or actions.", "medium", "Machine-checkable constraint annotations."),
    "context_understanding": ("B/A", "Multi-turn + SFT", "Resolve intent from the current and prior turns without inventing context.", "Topic shifts, literal misreadings, or irrelevant assumptions.", "hard", "Complete synthetic conversation context with provenance."),
    "conversational_continuity": ("B", "Multi-turn", "Carry forward constraints and intent across turns.", "Dropping or contradicting earlier conversational state.", "hard", "Full multi-turn transcripts created independently of holdout cases."),
    "saudi_najdi_dialect": ("A/F", "SFT + Preference/DPO", "Use natural Saudi/Najdi register appropriate to the interaction.", "Formal, non-Saudi, or mismatched regional phrasing.", "medium", "Native-reviewed Saudi/Najdi references."),
    "unnatural_arabic": ("A/F", "SFT + Preference/DPO", "Produce fluent, idiomatic Arabic without malformed phrasing.", "Broken, translated, or socially inappropriate Arabic.", "medium", "Native-speaker review and diversity across intents."),
    "repetition_degeneration": ("E/A", "Preference/DPO + SFT", "Stop cleanly after a complete answer and avoid loops.", "Repeated phrases, laughter, disclaimers, or self-contradictory loops.", "medium", "Negative examples plus generation repetition controls."),
    "factual_accuracy": ("D/E/A", "SFT + Tool-use", "Ground factual and time-sensitive claims in an explicit source.", "Stale, mixed, invented, or unverified facts.", "hard", "Timestamped authoritative sources or verified retrieval output."),
    "verbosity_concision": ("A/E", "SFT + Preference/DPO", "Match answer length to the request while preserving required content.", "Unnecessary suggestions, disclaimers, or long detours.", "easy-medium", "Length-labelled examples and output-token controls."),
    "insufficient_evidence": ("G", "None yet", "Collect reviewer evidence before prescribing a fix.", "Do not infer a failure mode from winner alone.", "unknown", "Additional human annotation, not holdout prompt reuse."),
}


def _clusters(record: dict[str, Any]) -> list[str]:
    found=[name for name,rule in CLUSTER_RULES.items() if rule(record)]
    return found or ["insufficient_evidence"]


def _explanation(record: dict[str, Any], clusters: list[str]) -> str:
    if clusters == ["insufficient_evidence"]:
        return "Base was preferred, but the record has no tags or reviewer note sufficient to infer why."
    descriptions={"tool_behavior":"tool handling or execution failed","fabricated_tool_execution":"an action or result was claimed without verified execution","capability_misunderstanding":"available capability was misrepresented","hallucination":"unsupported claims were introduced","instruction_following":"the requested task or response boundary was missed","constraint_following":"an explicit constraint was not followed","context_understanding":"the request context was misunderstood","saudi_najdi_dialect":"the Saudi/Najdi register did not fit","unnatural_arabic":"Arabic phrasing was unnatural","repetition_degeneration":"the response repeated or degenerated","factual_accuracy":"facts were inaccurate or ungrounded","verbosity_concision":"length or focus did not fit","conversational_continuity":"prior conversational state was not maintained"}
    clauses=[descriptions[x] for x in clusters if x in descriptions]
    return "Reviewer tags indicate that " + "; ".join(clauses[:3]) + ". The accompanying reviewer note contains the case-specific evidence."


def _recommended_count(case_count: int, major: int, critical: int) -> int:
    # One fresh example per affected case, with one additional example per two severe cases.
    if case_count == 0: return 0
    return case_count + (major + critical + 1) // 2


def build_failure_analysis(run_id: str) -> dict[str, Any]:
    if not RUN_ID.fullmatch(run_id): raise ValueError("invalid Phase 3 run id")
    root=REPORTS_ROOT/run_id; review_path=root/"human-review.json"
    state=json.loads(review_path.read_text(encoding="utf-8"))
    if state.get("summary",{}).get("reviewed") != len(state.get("records",[])) or state.get("final_gate",{}).get("final_decision") != "REJECT":
        raise ValueError("failure analysis requires a completed REJECT review")
    regressions=[]; tag_counts=Counter(); cluster_counts=Counter(); cluster_severity=defaultdict(Counter); type_counts=Counter()
    for record in state["records"]:
        if record.get("decision") != "BASE_WIN": continue
        clusters=_clusters(record); primary=next((name for name in PRIMARY_PRIORITY if name in clusters),clusters[0])
        item={"eval_id":record["eval_id"],"severity":record["severity"],"critical_fail":record["critical_fail"],"error_tags":record.get("error_tags",[]),"reviewer_note":record.get("notes","") or None,"prompt_category":record.get("category"),"evaluation_type":record.get("evaluation_type"),"why_adapter_lost":_explanation(record,clusters),"likely_root_cause":primary,"root_cause_clusters":clusters}
        regressions.append(item); tag_counts.update(item["error_tags"]); type_counts[item["evaluation_type"]]+=1
        for cluster in clusters: cluster_counts[cluster]+=1; cluster_severity[cluster][item["severity"]]+=1
    cluster_critical={}
    for cluster in cluster_counts:
        cluster_critical[cluster]=sum(cluster in r["root_cause_clusters"] and (r["severity"]=="CRITICAL" or r["critical_fail"] is True) for r in regressions)
    specs=[]
    for cluster,count in cluster_counts.most_common():
        strategy,fmt,desired,undesired,difficulty,truth=REMEDIATION[cluster]; sev=cluster_severity[cluster]; recommended=0 if cluster=="insufficient_evidence" else _recommended_count(count,sev["MAJOR"],cluster_critical[cluster])
        specs.append({"cluster":cluster,"evidence":{"cases":count,"severity":dict(sev)},"best_addressed_by":strategy,"desired_behavior":desired,"undesirable_behavior":undesired,"recommended_new_examples":recommended,"recommended_format":fmt,"difficulty":difficulty,"diversity_requirements":"Use materially different intents, wording, entities, domains, and conversation shapes; avoid templates derived from holdout cases.","saudi_najdi_requirements":"Use native-reviewed Saudi/Najdi language when conversational language is relevant; do not force dialect into tool payloads or factual source text.","safeguards":"Include non-repetition negatives, grounded uncertainty, bounded answer length, and explicit failure behavior.","source_of_truth":truth})
    severe=[x for x in regressions if x["severity"] in {"MAJOR","CRITICAL"}]
    cluster_major={cluster:count for cluster,values in cluster_severity.items() if (count:=values["MAJOR"])}
    summary=state.get("summary",{})
    return {"schema_version":1,"stage":"Phase 3.5 — Failure Analysis & Remediation Planning","generated_at":_now(),"phase3_run_id":run_id,"production_job_id":state.get("production_job_id"),"adapter_disposition":"REJECTED_FOR_PROMOTION","phase4a":"BLOCKED","source":{"human_review_sha256":_sha(review_path),"phase3_artifact_fingerprints":state.get("source_fingerprints",{}),"reviewed":len(state["records"]),"final_decision":"REJECT"},"holdout_policy":{"classification":"HOLDOUT_EVALUATION_DATA","prohibitions":["No exact evaluation prompt may enter training.","No gold evaluation answer may enter training.","No Response A/B output may enter training.","No near-duplicate or trivial paraphrase of an evaluation case may enter training."],"requirements":["New examples must test the same skill with materially different wording, context, and entities.","Future evaluation must include a new untouched holdout set."]},"summary":{"total_review_cases":len(state["records"]),"review_outcomes":{"adapter_wins":summary.get("adapter_wins"),"base_wins":summary.get("base_wins"),"ties":summary.get("ties")},"analyzed_regressions":len(regressions),"major_or_critical_regressions":len(severe),"failure_count_per_tag":dict(tag_counts.most_common()),"failure_count_per_root_cause_cluster":dict(cluster_counts.most_common()),"severity_per_cluster":{k:dict(v) for k,v in cluster_severity.items()},"text_vs_tool_regressions":dict(type_counts),"critical_regressions_by_cluster":{k:v for k,v in cluster_critical.items() if v},"major_regressions_by_cluster":cluster_major},"base_win_cases":regressions,"remediation_specification":{"target_dataset":"gold-v009-remediation-draft (PROPOSED_ONLY_NOT_CREATED)","example_count_method":"One fresh example per affected case plus one additional example per two Major/Critical cases, minimum zero for no evidence; counts are indicative per cluster, and multi-skill examples may share coverage but must have one declared primary skill. Insufficient-evidence clusters receive zero examples until annotated.","action_key":{"A":"SFT data improvement","B":"Multi-turn data improvement","C":"Tool-use training","D":"System/runtime/tool schema fixes","E":"Inference configuration/generation controls","F":"Dataset balancing","G":"Not enough evidence"},"clusters":specs,"future_dataset_structure":{"state":"proposal_only","sources":["new_sft.jsonl","new_multi_turn.jsonl","new_tool_use.jsonl","new_preference.jsonl"],"required_checks":["exact and near-duplicate scan against all Phase 3 holdout prompts, gold answers, and outputs","conversation-level split isolation","loss-mask validation","tool-schema validation","native Saudi/Najdi review where applicable"]},"future_evaluation":{"old_phase3_holdout":"Preserve unchanged as a regression benchmark only.","new_holdout":"Create a separately sourced, untouched benchmark with unseen prompts and materially different contexts/entities.","anti_overfitting":"Keep the new holdout inaccessible to training construction and include adjacent skills, not paraphrases of known failures."}}}


def _markdown(report: dict[str, Any]) -> str:
    s=report["summary"]; lines=["# Phase 3.5 — Failure Analysis & Remediation Planning","",f"Generated: `{report['generated_at']}`",f"Adapter disposition: **{report['adapter_disposition']}**  ","Phase 4A: **BLOCKED**","","## Holdout boundary","",*['- '+x for x in report['holdout_policy']['prohibitions']],*['- '+x for x in report['holdout_policy']['requirements']],"","## Aggregate findings","",f"- Reviewed cases: **{s['total_review_cases']}**; outcomes: **{s['review_outcomes']}**",f"- Analyzed regressions: **{s['analyzed_regressions']}**",f"- Major/Critical regressions: **{s['major_or_critical_regressions']}**",f"- Text vs Tool: **{s['text_vs_tool_regressions']}**",f"- Tag counts: **{s['failure_count_per_tag']}**",f"- Root-cause clusters: **{s['failure_count_per_root_cause_cluster']}**",f"- Critical by cluster (CRITICAL severity or critical flag): **{s['critical_regressions_by_cluster']}**",f"- Major by cluster (MAJOR severity): **{s['major_regressions_by_cluster']}**","","## Base-win cases",""]
    for x in report["base_win_cases"]:
        lines += [f"### {x['eval_id']}",f"- Severity: `{x['severity']}`; critical: `{str(x['critical_fail']).lower()}`; type: `{x['evaluation_type']}`; category: `{x['prompt_category']}`",f"- Tags: `{', '.join(x['error_tags']) or 'none'}`",f"- Why Adapter lost: {x['why_adapter_lost']}",f"- Likely root cause: `{x['likely_root_cause']}`",f"- Reviewer note: {x['reviewer_note'] or 'No note supplied.'}",""]
    lines += ["## Remediation specification","",f"Proposed dataset: **{report['remediation_specification']['target_dataset']}**","",f"Sizing method: {report['remediation_specification']['example_count_method']}","",f"Action key: {report['remediation_specification']['action_key']}",""]
    for x in report["remediation_specification"]["clusters"]:
        lines += [f"### {x['cluster']}",f"- Evidence: {x['evidence']}",f"- Address with: **{x['best_addressed_by']}**; format: **{x['recommended_format']}**; new examples: **{x['recommended_new_examples']}**",f"- Desired: {x['desired_behavior']}",f"- Avoid: {x['undesirable_behavior']}",f"- Source of truth: {x['source_of_truth']}",""]
    lines += ["## Future evaluation","",f"- {report['remediation_specification']['future_evaluation']['old_phase3_holdout']}",f"- {report['remediation_specification']['future_evaluation']['new_holdout']}",f"- {report['remediation_specification']['future_evaluation']['anti_overfitting']}",""]
    return "\n".join(lines)


def write_failure_analysis(run_id: str) -> tuple[Path,Path,dict[str,Any]]:
    report=build_failure_analysis(run_id); root=REPORTS_ROOT/run_id; json_path=root/"failure-analysis.json"; md_path=root/"failure-analysis.md"
    _atomic(json_path,report)
    text=_markdown(report); tmp=md_path.with_name(f".{md_path.name}.tmp"); tmp.write_text(text,encoding="utf-8"); tmp.replace(md_path)
    return json_path,md_path,report


if __name__ == "__main__":
    write_failure_analysis("phase3-train-20261006-001")
