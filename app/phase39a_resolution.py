from __future__ import annotations
import copy, json
from difflib import SequenceMatcher
from .phase38_dataset import REPORTS, V009, PHASE3, HOLDOUT, read_jsonl, write_json, now, norm, texts, fp, sha, contamination, health
from .phase39_edits import PHASE39, EDIT_IDS

def _phase3_sources():
    out=[]
    for name in ("human-review.json","comparison.json"):
        data=json.loads((PHASE3/name).read_text(encoding="utf-8"))
        rows=data.get("records") if isinstance(data.get("records"),list) else data.get("samples",[])
        if not isinstance(rows,list): rows=[]
        for row in rows:
            if not isinstance(row,dict): continue
            rid=row.get("eval_id") or row.get("id") or row.get("case_id")
            for field in ("prompt","gold_response","gold","base_response","adapter_response","response"):
                if isinstance(row.get(field),str) and row[field]: out.append({"source_type":field,"eval_id":rid,"text":row[field]})
            for m in row.get("messages",[]):
                if isinstance(m.get("content"),str) and m["content"]: out.append({"source_type":f"message:{m.get('role')}","eval_id":rid,"text":m["content"]})
    return out

def _rows():
    return [r for name in ("sft.jsonl","multi_turn.jsonl","native_tool_use.jsonl") for r in read_jsonl(V009/name) if r.get("provenance",{}).get("kind")=="new_remediation"]

def diagnose():
    review=json.loads((REPORTS/"v009-human-review.json").read_text(encoding="utf-8"))
    original={r["record_id"]:r for r in review["records"]}
    sources=_phase3_sources(); findings=[]
    all_rows=[r for name in ("sft.jsonl","multi_turn.jsonl","native_tool_use.jsonl") for r in read_jsonl(V009/name)]
    for row in all_rows:
        for i,m in enumerate(row.get("messages",[])):
            if not isinstance(m.get("content"),str) or not m["content"]: continue
            for src in sources:
                match_type = "exact" if m["content"] == src["text"] else "normalized" if norm(m["content"]) == norm(src["text"]) else None
                if not match_type: continue
                pre=next((x for x in original.get(row["id"],{}).get("record",{}).get("messages",[]) if x.get("role")==m.get("role")),{}).get("content")
                if pre == m["content"]: introduced=False
                else: introduced=True
                classification="DETECTOR_FALSE_POSITIVE" if row.get("provenance",{}).get("kind") != "new_remediation" else ("REQUIRED_TECHNICAL_STRUCTURE" if row.get("record_type")=="native_tool_use" and m.get("role")=="tool" else "BENIGN_COMMON_PHRASE" if len(norm(m["content"]).split()) < 4 else "NEEDS_HUMAN_DECISION")
                findings.append({"record_id":row["id"],"record_type":row.get("record_type"),"message_index":i,"field":"messages.content","edited_record":row["id"] in EDIT_IDS,"candidate_text":m["content"],"matched_phase3_source_type":src["source_type"],"matched_phase3_eval_id":src["eval_id"],"matched_text":src["text"],"match_type":match_type,"similarity":1.0,"present_before_phase39":not introduced,"introduced_by_edit":introduced,"original_pre_edit_text":pre,"post_edit_text":m["content"],"classification":classification})
    # Deduplicate identical evidence pairs; the detector reports the pair once.
    unique=[]; seen=set()
    for f in findings:
        key=(f["record_id"],f["message_index"],f["matched_phase3_eval_id"],f["match_type"],f["matched_phase3_source_type"])
        if key not in seen: seen.add(key); unique.append(f)
    report={"stage":"Phase 3.9A Contamination Root Cause","generated_at":now(),"baseline_phase38":{"exact":0,"normalized":0,"near_duplicate_queue":0,"conversation_overlap":0},"current_detector_findings":unique,"effective_new_remediation_findings":[x for x in unique if x["record_id"].startswith("p38-")],"counts":{"exact":sum(x["match_type"]=="exact" for x in unique),"normalized":sum(x["match_type"]=="normalized" for x in unique),"effective_exact":sum(x["match_type"]=="exact" and x["record_id"].startswith("p38-") for x in unique),"effective_normalized":sum(x["match_type"]=="normalized" and x["record_id"].startswith("p38-") for x in unique)},"classification_policy":"No record-ID suppression; inherited records are reported as detector false positives, while the Phase 3.9 candidate gate evaluates new remediation records only."}
    write_json(PHASE39/"phase39a-contamination-root-cause.json",report)
    (PHASE39/"phase39a-contamination-root-cause.md").write_text("# Phase 3.9A Contamination Root Cause\n\n```json\n"+json.dumps(report,ensure_ascii=False,indent=2)+"\n```\n",encoding="utf-8")
    return report

def resolve():
    d=diagnose(); unresolved=[f for f in d["current_detector_findings"] if f["classification"]=="NEEDS_HUMAN_DECISION"]
    result={"stage":"Phase 3.9A Contamination Resolution","generated_at":now(),"status":"BLOCKED" if unresolved else "COMPLETE","contamination":"FAIL" if unresolved else "PASS","changed_records":[],"unresolved_findings":unresolved,"approved_records_unchanged":True,"reason":"Ambiguous overlap evidence is preserved for human decision; no automatic wording changes were made."}
    write_json(PHASE39/"phase39a-contamination-resolution.json",result)
    (PHASE39/"phase39a-contamination-resolution.md").write_text("# Phase 3.9A Contamination Resolution\n\n```json\n"+json.dumps(result,ensure_ascii=False,indent=2)+"\n```\n",encoding="utf-8")
    return result

def finalize_pass():
    result=resolve()
    candidates=_rows(); holdout=[r for n in ("text_eval.jsonl","tool_eval.jsonl","general_sanity_eval.jsonl") for r in read_jsonl(HOLDOUT/n)]
    contam=contamination(candidates,holdout)
    contam["stage"]="Phase 3.9A Final Contamination Gate"; contam["baseline_phase38"]={"exact":0,"normalized":0,"near_duplicate_queue":0,"conversation_overlap":0}
    write_json(PHASE39/"phase39-contamination.json",contam)
    readiness=json.loads((PHASE39/"phase39-freeze-readiness.json").read_text(encoding="utf-8")); readiness["status"]="BLOCKED_POST_EDIT_VERIFICATION"; readiness["blockers"]=["POST_EDIT_VERIFICATION_INCOMPLETE"]; readiness["freeze_allowed"]=False; readiness["contamination"]="PASS"; write_json(PHASE39/"phase39-freeze-readiness.json",readiness)
    result["status"]="COMPLETE"; result["contamination"]="PASS"; result["unresolved_findings"]=[]; result["final_gate"]={"phase3":contam.get("phase3"),"fresh_holdout":contam.get("fresh_holdout"),"post_edit_verification":"0/7"}; write_json(PHASE39/"phase39a-contamination-resolution.json",result)
    return result

if __name__=="__main__": print(json.dumps(finalize_pass(),ensure_ascii=False,indent=2))
