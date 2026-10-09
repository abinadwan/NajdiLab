from __future__ import annotations

import hashlib, json, os, re, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import training_control as training

REPORTS_ROOT=training.PROJECT_ROOT/"reports"
EXPORTS_ROOT=training.PROJECT_ROOT/"exports"
RUN_ID=re.compile(r"^phase3-(train-\d{8}-\d{3})$")
DECISIONS={"ADAPTER_WIN","TIE","BASE_WIN"}
SEVERITIES={"NONE","MINOR","MAJOR","CRITICAL"}
FINAL_DECISIONS={"APPROVE","NEEDS_RETRAINING","REJECT"}
TAGS={"instruction_following","factual_error","hallucination","dialect_issue","unnatural_arabic","repetition","verbosity","too_short","context_failure","constraint_failure","tool_behavior","formatting","safety","other"}
DIMENSIONS={"content_correctness","instruction_following","constraint_adherence","najdi_saudi_dialect","natural_arabic","context_handling","multi_turn_behavior","relevance","conciseness","repetition","hallucination","tool_behavior","overall_usefulness"}


class Phase3ReviewError(ValueError):
    def __init__(self,code: str,message: str,status: int=422): super().__init__(message); self.code=code; self.status=status
    def as_dict(self): return {"ok":False,"code":self.code,"message":str(self)}


def _now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def _sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _blind_mapping(eval_id: str) -> dict[str,str]:
    swap=sum(ord(char) for char in eval_id)%2==1
    return {"A":"ADAPTER" if swap else "BASE","B":"BASE" if swap else "ADAPTER"}
def _atomic(path: Path,value: Any):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try: tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)
    finally: tmp.unlink(missing_ok=True)


def _tree_sha(path: Path) -> str:
    if not path.is_dir(): return ""
    entries={p.relative_to(path).as_posix():_sha(p) for p in sorted(path.rglob("*")) if p.is_file()}
    return hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _adapter_tree_sha(adapter_path: str) -> str:
    """Fingerprint the actual WSL adapter tree, not merely benchmark metadata."""
    if not isinstance(adapter_path,str) or not adapter_path.startswith("/home/najdi/"):
        raise Phase3ReviewError("ADAPTER_FINGERPRINT_MISMATCH","Adapter path is invalid",409)
    script="import hashlib,json,pathlib,sys;p=pathlib.Path(sys.argv[1]);e={str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(p.rglob('*')) if x.is_file()};print(hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':')).encode()).hexdigest())"
    try:
        result=subprocess.run(["wsl.exe","-d","NajdiTrain","--","python3","-c",script,adapter_path],capture_output=True,text=True,timeout=45,check=True)
        value=result.stdout.strip()
    except (OSError,subprocess.SubprocessError) as exc:
        raise Phase3ReviewError("ADAPTER_FINGERPRINT_MISMATCH",f"Cannot fingerprint adapter artifact: {exc}",409) from exc
    if not re.fullmatch(r"[0-9a-f]{64}",value):
        raise Phase3ReviewError("ADAPTER_FINGERPRINT_MISMATCH","Adapter artifact fingerprint is unavailable",409)
    return value


def _paths(run_id: str):
    match=RUN_ID.fullmatch(run_id)
    if not match: raise Phase3ReviewError("PHASE3_RUN_NOT_FOUND","Phase 3 run id is invalid",404)
    root=REPORTS_ROOT/run_id
    required={name:root/name for name in ("comparison.json","base-benchmark.jsonl","adapter-benchmark.jsonl")}
    if not root.is_dir() or not all(p.is_file() for p in required.values()): raise Phase3ReviewError("PHASE3_RUN_NOT_FOUND","Phase 3 artifacts are missing",404)
    return match.group(1),root,required


def _evaluation_rows() -> dict[str,dict]:
    root=EXPORTS_ROOT/"gold-v008-split-clean"; result={}
    for name in ("text_sft_eval.jsonl","tool_eval.jsonl","vision_eval.jsonl","runtime_agent_eval.jsonl"):
        for line in (root/name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row=json.loads(line); row["evaluation_file"]=name; result[str(row["id"])]=row
    return result


def _fingerprints(job_id: str,required: dict[str,Path]) -> dict[str,Any]:
    job=training.get_job(job_id); attempt=training.JOBS_ROOT/job_id/"attempts"/"attempt-002"/"attempt.json"
    if not attempt.is_file(): raise Phase3ReviewError("ADAPTER_FINGERPRINT_MISMATCH","Production attempt is missing",409)
    adapter=(((json.loads(attempt.read_text(encoding="utf-8")).get("result") or {}).get("adapter_result") or {}).get("adapter_path"))
    # WSL adapter content is represented by immutable hashes recorded in its result and local validation/benchmark evidence.
    adapter_meta=(required["adapter-benchmark.jsonl"].with_suffix(".meta.json"))
    meta=json.loads(adapter_meta.read_text(encoding="utf-8")) if adapter_meta.is_file() else {}
    return {"comparison_sha256":_sha(required["comparison.json"]),"base_benchmark_sha256":_sha(required["base-benchmark.jsonl"]),"adapter_benchmark_sha256":_sha(required["adapter-benchmark.jsonl"]),"adapter_output_sha256":meta.get("output_sha256"),"adapter_config_sha256":meta.get("adapter_config_sha256"),"adapter_artifact_sha256":_adapter_tree_sha(adapter),"adapter_path":adapter,"dataset_fingerprint":job.get("dataset_fingerprint"),"base_model_fingerprint":meta.get("model_config_sha256")}


def _summary(records: list[dict]) -> dict[str,Any]:
    reviewed=[r for r in records if r.get("decision") in DECISIONS]; decisions=Counter(r.get("decision") for r in reviewed); tags=Counter(t for r in reviewed for t in r.get("error_tags",[])); breakdown=defaultdict(lambda:Counter())
    for r in reviewed: breakdown[r.get("evaluation_type") or "other"][r["decision"]]+=1
    cross_tab={winner:{severity:sum(r.get("decision")==winner and r.get("severity")==severity for r in reviewed) for severity in sorted(SEVERITIES)} for winner in ("ADAPTER_WIN","BASE_WIN","TIE")}
    base_wins=decisions["BASE_WIN"]
    adapter_minor=sum(r.get("decision")=="BASE_WIN" and r.get("severity")=="MINOR" for r in reviewed)
    adapter_major=sum(r.get("decision")=="BASE_WIN" and r.get("severity")=="MAJOR" for r in reviewed)
    adapter_critical=sum(r.get("decision")=="BASE_WIN" and (r.get("severity")=="CRITICAL" or r.get("critical_fail") is True) for r in reviewed)
    base_major=sum(r.get("decision")=="ADAPTER_WIN" and r.get("severity")=="MAJOR" for r in reviewed)
    base_critical=sum(r.get("decision")=="ADAPTER_WIN" and (r.get("severity")=="CRITICAL" or r.get("critical_fail") is True) for r in reviewed)
    tie_critical=sum(r.get("decision")=="TIE" and (r.get("severity")=="CRITICAL" or r.get("critical_fail") is True) for r in reviewed)
    critical_cases=sum(bool(r.get("critical_fail")) for r in reviewed)
    critical_tool_regression=any(r.get("decision")=="BASE_WIN" and r.get("evaluation_type")=="tool" and (r.get("severity")=="CRITICAL" or r.get("critical_fail") is True) for r in reviewed)
    recommendation="RECOMMEND_APPROVE" if decisions["ADAPTER_WIN"]>base_wins and adapter_critical==0 and not critical_tool_regression else "RECOMMEND_REJECT" if base_wins>decisions["ADAPTER_WIN"] or adapter_critical>=2 else "RECOMMEND_NEEDS_RETRAINING"
    total=len(records); count=len(reviewed)
    return {"summary_semantics_version":2,"total":total,"reviewed":count,"remaining":total-count,"adapter_wins":decisions["ADAPTER_WIN"],"ties":decisions["TIE"],"base_wins":base_wins,"win_rate":round(decisions["ADAPTER_WIN"]/count,4) if count else 0,"regression_rate":round(base_wins/count,4) if count else 0,"critical_cases":critical_cases,"adapter_minor_regressions":adapter_minor,"adapter_major_regressions":adapter_major,"adapter_critical_regressions":adapter_critical,"base_major_failures":base_major,"base_critical_failures":base_critical,"tie_critical_cases":tie_critical,"winner_severity_cross_tab":cross_tab,"tag_frequency":dict(tags),"breakdown":{k:dict(v) for k,v in breakdown.items()},"recommendation":recommendation if count==total else None}


def get_review(run_id: str) -> dict[str,Any]:
    job_id,root,required=_paths(run_id); path=root/"human-review.json"
    if path.is_file():
        state=json.loads(path.read_text(encoding="utf-8"))
        migrated=False
        for record in state.get("records",[]):
            if "blind_mapping" not in record:
                record["blind_mapping"]=_blind_mapping(str(record.get("eval_id") or "")); migrated=True
        if state.get("summary",{}).get("summary_semantics_version")!=2:
            state["summary"]=_summary(state.get("records",[])); migrated=True
        if "adapter_artifact_sha256" not in state.get("source_fingerprints",{}) and state.get("summary",{}).get("reviewed",0)==0:
            state["source_fingerprints"]=_fingerprints(job_id,required); migrated=True
        if migrated:
            state["updated_at"]=_now(); _atomic(path,state)
        return state
    comparison=json.loads(required["comparison.json"].read_text(encoding="utf-8")); eval_rows=_evaluation_rows(); now=_now(); records=[]
    for item in comparison.get("samples",[]):
        source=eval_rows.get(str(item["id"]))
        if not source: raise Phase3ReviewError("REVIEW_CASE_NOT_FOUND",f"Evaluation source missing: {item['id']}",409)
        messages=source["messages"][:source["target_message_index"]]
        eval_id=str(item["id"])
        records.append({"eval_id":eval_id,"category":item.get("category"),"evaluation_type":"tool" if item.get("evaluation_file")=="tool_eval.jsonl" else "text","prompt":messages,"gold_response":item["gold"],"base_response":item["base_response"],"adapter_response":item["adapter_response"],"blind_mapping":_blind_mapping(eval_id),"diagnostic":{**item.get("automatic",{}),"delta":round(item["automatic"]["adapter_similarity"]-item["automatic"]["base_similarity"],4),"label":"Diagnostic only"},"decision":None,"severity":"NONE","critical_fail":False,"error_tags":[],"dimension_scores":{},"notes":"","reviewed_at":None})
    state={"schema_version":1,"phase3_run_id":run_id,"production_job_id":job_id,"created_at":now,"updated_at":now,"source_fingerprints":_fingerprints(job_id,required),"records":records,"summary":_summary(records),"review_status":"IN_PROGRESS","final_gate":{"status":"BLOCKED_REVIEW_INCOMPLETE","final_decision":None,"phase4a":"BLOCKED","decided_at":None}}
    _atomic(path,state); return state


def save_case(run_id: str,eval_id: str,data: dict[str,Any]) -> dict[str,Any]:
    if not isinstance(data,dict): raise Phase3ReviewError("INVALID_REVIEW_DECISION","Review payload must be an object")
    state=get_review(run_id); record=next((r for r in state["records"] if r["eval_id"]==eval_id),None)
    if not record: raise Phase3ReviewError("REVIEW_CASE_NOT_FOUND","Review case not found",404)
    blind_choice=data.get("blind_choice")
    if blind_choice is not None:
        if blind_choice not in {"A","B","TIE"}: raise Phase3ReviewError("INVALID_REVIEW_DECISION","Blind choice is invalid")
        decision="TIE" if blind_choice=="TIE" else f"{record['blind_mapping'][blind_choice]}_WIN"
    else: decision=data.get("decision")
    severity=data.get("severity","NONE"); tags=data.get("error_tags") or []; scores=data.get("dimension_scores") or {}; critical=data.get("critical_fail",False)
    valid_scores=isinstance(scores,dict) and set(scores)<=DIMENSIONS and all(type(v) is int and v in {0,1,2} for v in scores.values())
    if decision not in DECISIONS or severity not in SEVERITIES or type(critical) is not bool or not isinstance(tags,list) or any(not isinstance(t,str) for t in tags) or not set(tags)<=TAGS or not valid_scores: raise Phase3ReviewError("INVALID_REVIEW_DECISION","Review values are invalid")
    severity="CRITICAL" if critical else severity
    record.update({"decision":decision,"severity":severity,"critical_fail":critical,"error_tags":sorted(set(tags)),"dimension_scores":scores,"notes":str(data.get("notes") or "")[:4000],"reviewed_at":_now()})
    state["summary"]=_summary(state["records"]); state["updated_at"]=_now(); state["review_status"]="COMPLETE" if state["summary"]["remaining"]==0 else "IN_PROGRESS"; state["final_gate"]["status"]="PENDING_FINAL_DECISION" if state["review_status"]=="COMPLETE" else "BLOCKED_REVIEW_INCOMPLETE"; _atomic(REPORTS_ROOT/run_id/"human-review.json",state); return state


def submit_final_decision(run_id: str,decision: str) -> dict[str,Any]:
    if decision not in FINAL_DECISIONS: raise Phase3ReviewError("FINAL_DECISION_NOT_ALLOWED","Invalid final decision")
    state=get_review(run_id)
    if state["summary"]["remaining"]: raise Phase3ReviewError("REVIEW_INCOMPLETE","All cases must be reviewed",409)
    job_id,root,required=_paths(run_id); current=_fingerprints(job_id,required); expected=state["source_fingerprints"]
    for key in ("comparison_sha256","base_benchmark_sha256","adapter_benchmark_sha256","dataset_fingerprint","base_model_fingerprint"):
        if current.get(key)!=expected.get(key): raise Phase3ReviewError("STALE_PHASE3_ARTIFACT",f"Fingerprint changed: {key}",409)
    for key in ("adapter_output_sha256","adapter_config_sha256","adapter_artifact_sha256","adapter_path"):
        if current.get(key)!=expected.get(key): raise Phase3ReviewError("ADAPTER_FINGERPRINT_MISMATCH",f"Adapter fingerprint changed: {key}",409)
    state["final_gate"]={"status":"APPROVED" if decision=="APPROVE" else decision,"final_decision":decision,"phase4a":"READY" if decision=="APPROVE" else "BLOCKED","decided_at":_now()}; state["review_status"]="APPROVED" if decision=="APPROVE" else "NEEDS_RETRAINING" if decision=="NEEDS_RETRAINING" else "REJECTED"; state["updated_at"]=_now(); _atomic(root/"human-review.json",state); return state
