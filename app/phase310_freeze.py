from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
from .dataset_platform import DATASETS_ROOT, freeze_dataset_version, regenerate_training_diagnostics, dataset_health, dataset_version_detail, _sha256, _training_fingerprint
from .training_control import freeze_readiness_gate, quality_gate
from .phase38_dataset import V008, HOLDOUT, PHASE3, now, write_json
from .phase39_edits import PHASE39

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports'/'phase310'; VERSION='gold-v009-remediation-draft'; V009=DATASETS_ROOT/VERSION
CONTENT_FILES=('sft.jsonl','multi_turn.jsonl','native_tool_use.jsonl','direct_language.jsonl','preference_pairs.jsonl','capability-registry.json')

def tree_hashes(root: Path) -> dict[str,str]:
    return {str(p.relative_to(root)): _sha256(p) for p in sorted(root.rglob('*')) if p.is_file()}

def emit(name: str, value: dict[str,Any]):
    write_json(OUT/f'{name}.json',value)
    (OUT/f'{name}.md').write_text(f"# {value.get('stage',name)}\n\nStatus: **{value.get('status')}**\n\n```json\n{json.dumps(value,ensure_ascii=False,indent=2)}\n```\n",encoding='utf-8')

def run():
    protected_before={'v008':tree_hashes(V008),'fresh_holdout':tree_hashes(HOLDOUT),'phase3':tree_hashes(PHASE3)}
    content_before={name:_sha256(V009/name) for name in CONTENT_FILES}
    review=json.loads((ROOT/'reports'/'phase38'/'v009-human-review.json').read_text(encoding='utf-8'))
    post=json.loads((PHASE39/'post-edit-verification.json').read_text(encoding='utf-8'))
    contam=json.loads((PHASE39/'phase39-contamination.json').read_text(encoding='utf-8'))
    health=regenerate_training_diagnostics(VERSION); readiness=freeze_readiness_gate(VERSION)
    extra=[]
    if review['summary']!={'total':36,'reviewed':36,'approved':29,'edited':7,'rejected':0,'remaining':0}: extra.append('ORIGINAL_HUMAN_REVIEW_MISMATCH')
    if post['summary'].get('verified')!=7 or post['summary'].get('approved')!=7 or post['summary'].get('additional_edit') or post['summary'].get('rejected'): extra.append('POST_EDIT_VERIFICATION_INCOMPLETE')
    if contam.get('status')!='PASS': extra.append('CONTAMINATION_BLOCKER')
    readiness['blocking_issues'].extend({'code':x,'message':x} for x in extra)
    readiness['status']='PASS' if not readiness['blocking_issues'] else 'BLOCKED'
    diagnostics={'stage':'Phase 3.10 Pre-freeze Diagnostics','status':'PASS' if readiness['status']=='PASS' else 'BLOCKED','dataset_health':health,'freeze_readiness':readiness,'human_review':review['summary'],'post_edit_verification':post['summary'],'contamination':contam,'content_fingerprints':content_before,'generated_at':now()}
    emit('pre-freeze-diagnostics',diagnostics)
    loss=json.loads((V009/'loss-mask-validation.json').read_text(encoding='utf-8')); emit('loss-mask-validation',{'stage':'Phase 3.10 Loss-mask Validation','status':'PASS' if loss.get('passed')==loss.get('total')==66 and not loss.get('failures') else 'FAIL',**loss})
    emit('freeze-readiness',{'stage':'Phase 3.10 Freeze Readiness',**readiness})
    if readiness['status']!='PASS': return {'status':'BLOCKED','readiness':readiness}
    frozen=freeze_dataset_version(VERSION)
    content_after={name:_sha256(V009/name) for name in CONTENT_FILES}
    if content_before!=content_after: raise RuntimeError('dataset content changed during freeze')
    manifest_sha=_sha256(V009/'manifest.json'); protected_after={'v008':tree_hashes(V008),'fresh_holdout':tree_hashes(HOLDOUT),'phase3':tree_hashes(PHASE3)}
    if protected_before!=protected_after: raise RuntimeError('historical protected asset changed')
    freeze_result={'stage':'Phase 3.10 Freeze Result','status':'PASS','version':VERSION,'state':frozen['state'],'manifest_sha256':manifest_sha,'training_fingerprint':_training_fingerprint(V009),'content_fingerprints':content_after,'capability_registry_fingerprint':json.loads((V009/'manifest.json').read_text(encoding='utf-8'))['capability_registry']['fingerprint'],'human_review':review['summary'],'post_edit_verification':post['summary'],'contamination_status':contam['status'],'historical_assets_unchanged':True,'generated_at':now()}; emit('freeze-result',freeze_result)
    post_health=dataset_health(VERSION); training_gate=quality_gate(VERSION)
    post_report={'stage':'Phase 3.10 Post-freeze Validation','status':'PASS' if post_health['training_readiness']['status']=='READY' and training_gate['status'] in {'PASS','PASS_WITH_WARNINGS'} else 'FAIL','dataset_health':post_health,'training_quality_gate':training_gate,'content_immutable':content_before==content_after,'historical_assets_unchanged':protected_before==protected_after,'generated_at':now()}; emit('post-freeze-validation',post_report)
    return {'status':post_report['status'],'freeze':freeze_result,'post':post_report}

if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False,indent=2))
