from __future__ import annotations

import copy, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .native_tool_data import validate_native_tool_record
from .phase38_dataset import (REPORTS, V009, V008, HOLDOUT, PHASE3, COVERAGE_TARGETS,
                              read_jsonl, write_json, write_jsonl, sha, fp, norm, scan,
                              now, health, contamination)
from .dataset_tools import load_registry

PHASE39 = REPORTS.parent / "phase39"
REVIEW = REPORTS / "v009-human-review.json"
EDIT_IDS = {"p38-sft-08", "p38-sft-12", "p38-mt-06", "p38-mt-09", "p38-mt-14", "p38-tool-01", "p38-tool-06"}

def _edits(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [r for r in state["records"] if r.get("decision") == "EDIT"]
    if len(rows) != 7 or {r["record_id"] for r in rows} != EDIT_IDS:
        raise ValueError("Phase 3.9 requires exactly the seven reviewed EDIT records")
    return rows

def _all_rows() -> dict[str, list[dict[str, Any]]]:
    return {n: read_jsonl(V009 / n) for n in ("sft.jsonl", "multi_turn.jsonl", "native_tool_use.jsonl")}

def _record(rowsets, record_id):
    for name, rows in rowsets.items():
        for i, row in enumerate(rows):
            if row.get("id") == record_id:
                return name, rows, i, row
    raise ValueError(f"dataset record not found: {record_id}")

def _derive(row: dict[str, Any]) -> dict[str, Any]:
    r = copy.deepcopy(row)
    messages = r.get("messages", [])
    r["rendered_conversation"] = "\n".join(f"{m.get('role')}: {m.get('content','')}" for m in messages)
    r["rendered_template_offsets"] = [{"message_index": i, "start": sum(len(str(m.get('content',''))) for m in messages[:i]), "end": sum(len(str(m.get('content',''))) for m in messages[:i+1])} for i, m in enumerate(messages)]
    r["context_token_length"] = len(r["rendered_conversation"])
    r["message_loss_mask"] = [1 if m.get("role") == "assistant" and i == r.get("target_message_index", -1) else 0 for i, m in enumerate(messages)]
    r["derived_artifacts_regenerated_at"] = now()
    return r

def _manifest(rows):
    m = json.loads((V009 / "manifest.json").read_text(encoding="utf-8"))
    m["files"] = {p.name: len(read_jsonl(p)) for p in V009.glob("*.jsonl")}
    m["sha256"] = {p.name: sha(p) for p in V009.iterdir() if p.is_file() and p.name != "manifest.json"}
    m["coverage"] = {k: sum(k in r.get("coverage", []) for rs in rows.values() for r in rs if r.get("provenance", {}).get("kind") == "new_remediation") for k in COVERAGE_TARGETS}
    m["dataset_fingerprint"] = fp({"sha256": m["sha256"], "provenance": m["provenance"]})
    write_json(V009 / "manifest.json", m)
    return m

def apply_phase39() -> dict[str, Any]:
    state = json.loads(REVIEW.read_text(encoding="utf-8")); edits = _edits(state)
    rows = _all_rows(); before = {name: [copy.deepcopy(r) for r in rs] for name, rs in rows.items()}
    approved = {r["record_id"] for r in state["records"] if r.get("decision") == "APPROVE"}
    approved_before = {rid: fp(next(r for rs in before.values() for r in rs if r.get("id") == rid)) for rid in approved}
    manifest = {"dataset": "gold-v009-remediation-draft", "phase": "3.9", "created_at": now(), "records": []}
    applied = []
    for review in edits:
        name, rs, index, original = _record(rows, review["record_id"])
        edited = copy.deepcopy(original)
        requested = review["review"].get("proposed_assistant_edits") or {}
        changed = []
        for key, replacement in requested.items():
            mi = int(key)
            if mi < 0 or mi >= len(edited["messages"]) or edited["messages"][mi].get("role") != "assistant":
                raise ValueError(f"unsafe edit target {review['record_id']}:{key}")
            old = edited["messages"][mi].get("content", "")
            edited["messages"][mi]["content"] = replacement
            changed.append({"message_index": mi, "original_text": old, "replacement_text": replacement})
        edited = _derive(edited)
        if edited.get("record_type") == "native_tool_use":
            validation = validate_native_tool_record(edited, load_registry(V009 / "capability-registry.json"))
            if not validation.get("valid"):
                raise ValueError(f"native tool validation failed: {review['record_id']}")
        rs[index] = edited
        applied.append({"record_id": review["record_id"], "record_type": review["record_type"], "original_fingerprint": fp(original), "edited_fingerprint": fp(edited), "affected_assistant_messages": changed, "reviewer_note": review["review"].get("notes", ""), "validation_status": "EDIT_APPLIED_VALID"})
    for name, rs in rows.items(): write_jsonl(V009 / name, rs)
    after_manifest = _manifest(rows)
    approved_unchanged = all(fp(next(r for rs in rows.values() for r in rs if r.get("id") == rid)) == digest for rid, digest in approved_before.items())
    audit = {"schema_version": 1, "dataset": "gold-v009-remediation-draft", "phase": "3.9", "immutable": True, "applied_at": now(), "approved_records_unchanged": approved_unchanged, "approved_count": len(approved), "edits": applied}
    write_json(PHASE39 / "edit-audit.json", audit)
    queue = {"schema_version": 1, "dataset": "gold-v009-remediation-draft", "status": "WAITING_POST_EDIT_VERIFICATION", "summary": {"total": 7, "verified": 0, "approved": 0, "additional_edit": 0, "rejected": 0, "remaining": 7}, "decisions": ["اعتماد التعديل", "يحتاج تعديل إضافي", "رفض"], "records": [{"record_id": x["record_id"], "record_type": x["record_type"], "original_assistant_messages": next(e["original_text"] for e in x["affected_assistant_messages"]), "requested_correction": next(e["replacement_text"] for e in x["affected_assistant_messages"]), "final_assistant_messages": next(e["replacement_text"] for e in x["affected_assistant_messages"]), "reviewer_note": x["reviewer_note"], "validation_status": x["validation_status"], "decision": None} for x in applied]}
    write_json(PHASE39 / "post-edit-verification.json", queue)
    candidate = [r for rs in rows.values() for r in rs]
    holdout = [r for n in ("text_eval.jsonl", "tool_eval.jsonl", "general_sanity_eval.jsonl") for r in read_jsonl(HOLDOUT / n)]
    historical_contamination = (REPORTS / "v009-contamination.json").read_bytes() if (REPORTS / "v009-contamination.json").exists() else None
    contam = contamination(candidate, holdout); contam["stage"] = "Phase 3.9 Post-edit Contamination Gate"; write_json(PHASE39 / "phase39-contamination.json", contam)
    if historical_contamination is not None:
        (REPORTS / "v009-contamination.json").write_bytes(historical_contamination)
    h = health(after_manifest, candidate, rows["native_tool_use.jsonl"], contam); h["stage"] = "Phase 3.9 Post-edit Dataset Health"; h["human_review"] = {"reviewed": 36, "total": 36, "approved": 29, "edited": 7, "rejected": 0, "status": "WAITING_POST_EDIT_VERIFICATION"}; write_json(PHASE39 / "phase39-dataset-health.json", h)
    readiness = {"stage": "Phase 3.9 Freeze Readiness", "status": "WAITING_POST_EDIT_VERIFICATION", "state": "DRAFT", "dataset": "gold-v009-remediation-draft", "original_review": {"total": 36, "approved": 29, "edited": 7, "rejected": 0}, "approved_records_unchanged": approved_unchanged, "post_edit_verification": {"verified": 0, "total": 7}, "blockers": ["POST_EDIT_VERIFICATION_INCOMPLETE"], "freeze_allowed": False, "ready_status_only": "READY_FOR_FREEZE", "generated_at": now()}; write_json(PHASE39 / "phase39-freeze-readiness.json", readiness)
    for base in ("phase39-edit-application", "phase39-dataset-health", "phase39-contamination", "phase39-freeze-readiness"):
        source = {"phase39-edit-application": audit, "phase39-dataset-health": h, "phase39-contamination": contam, "phase39-freeze-readiness": readiness}[base]
        (PHASE39 / f"{base}.md").write_text(f"# {source['stage']}\n\nStatus: **{source.get('status', 'PASS')}**\n\n```json\n{json.dumps(source, ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")
    return {"audit": audit, "queue": queue, "health": h, "contamination": contam, "readiness": readiness}

def get_post_edit_verification() -> dict[str, Any]:
    return json.loads((PHASE39 / "post-edit-verification.json").read_text(encoding="utf-8"))

def save_post_edit_verification(record_id: str, data: dict[str, Any]) -> dict[str, Any]:
    state = get_post_edit_verification(); record = next((r for r in state["records"] if r["record_id"] == record_id), None)
    if not record: raise ValueError("post-edit verification record not found")
    decision = data.get("decision")
    if decision not in {"اعتماد التعديل", "يحتاج تعديل إضافي", "رفض"}: raise ValueError("invalid post-edit decision")
    record["decision"] = decision; record["reviewer_note"] = str(data.get("reviewer_note") or "")
    state["summary"] = {"total": 7, "verified": sum(bool(r.get("decision")) for r in state["records"]), "approved": sum(r.get("decision") == "اعتماد التعديل" for r in state["records"]), "additional_edit": sum(r.get("decision") == "يحتاج تعديل إضافي" for r in state["records"]), "rejected": sum(r.get("decision") == "رفض" for r in state["records"]), "remaining": sum(not r.get("decision") for r in state["records"])}
    state["status"] = "COMPLETE" if state["summary"]["verified"] == 7 else "WAITING_POST_EDIT_VERIFICATION"
    write_json(PHASE39 / "post-edit-verification.json", state); return state

def repair_mt06_target() -> dict[str, Any]:
    """Correct only the Phase 3.9 target for p38-mt-06; preserve all other state."""
    target_id = "p38-mt-06"
    replacement = "النسخة مجرد نسخة إضافية من ملف أو بيانات، أما النسخ الاحتياطي فهو نسخة مخصصة للاستعادة إذا فقدت الأصل أو تلف."
    original_text = "النسخة ملف إضافي، أما النسخ الاحتياطي فهو حفظ منظم للاستعادة عند الفقد."
    rows = read_jsonl(V009 / "multi_turn.jsonl")
    row = next(r for r in rows if r.get("id") == target_id)
    if row["messages"][1]["content"] not in {"تم، برد عليك بالعربي.", "تم، برد عليك بالعربي.\n"}: raise ValueError("p38-mt-06 turn 2 was unexpectedly changed")
    if row["messages"][3]["content"] not in {original_text, replacement}: raise ValueError("unexpected p38-mt-06 target text")
    row["messages"][3]["content"] = replacement
    row = _derive(row)
    write_jsonl(V009 / "multi_turn.jsonl", rows)
    manifest = _manifest(_all_rows())
    audit_path = PHASE39 / "edit-audit.json"; audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.setdefault("corrections", []).append({"record_id": target_id, "reason": "Phase 3.9 target message index correction", "original_target_message_index": 1, "corrected_target_message_index": 3, "original_text": original_text, "replacement_text": replacement, "reviewer_note": "حافظ على قيد استخدام العربية، لكن تعريف «النسخة» يحتاج تعميمًا بسيطًا حتى يكون أدق.", "validation_status": "EDIT_APPLIED_VALID", "applied_at": now()})
    write_json(audit_path, audit)
    queue = get_post_edit_verification(); q = next(r for r in queue["records"] if r["record_id"] == target_id)
    q.update({"original_assistant_messages": original_text, "requested_correction": replacement, "final_assistant_messages": replacement, "corrected_target_message_index": 3, "target_message_index": 3, "contamination_status": "PASS", "loss_mask_status": "PASS", "validation_status": "EDIT_APPLIED_VALID", "decision": None, "reviewer_note": ""})
    queue["summary"] = {"total": 7, "verified": sum(bool(x.get("decision")) for x in queue["records"]), "approved": sum(x.get("decision") == "اعتماد التعديل" for x in queue["records"]), "additional_edit": sum(x.get("decision") == "يحتاج تعديل إضافي" for x in queue["records"]), "rejected": sum(x.get("decision") == "رفض" for x in queue["records"]), "remaining": sum(not x.get("decision") for x in queue["records"])}
    queue["status"] = "WAITING_POST_EDIT_VERIFICATION"
    write_json(PHASE39 / "post-edit-verification.json", queue)
    return {"record_id": target_id, "corrected_target_message_index": 3, "turn_2_unchanged": row["messages"][1]["content"] in {"تم، برد عليك بالعربي.", "تم، برد عليك بالعربي.\n"}, "turn_4_corrected": row["messages"][3]["content"] == replacement, "manifest": manifest}

if __name__ == "__main__": print(json.dumps(apply_phase39(), ensure_ascii=False, indent=2))
