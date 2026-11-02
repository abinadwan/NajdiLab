"""Immutable conversational prompt/completion handoff. Never executes a trainer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from .db import ROOT, utc_now
from .dataset_platform import _version_dir, KNOWN_FILES, NATIVE_TRAIN_FILE
from .dataset_quality import analyze_directory
from .service import ValidationError, _validate_sft_record, TRAINING_REVIEW_STATUSES

HANDOFFS = ROOT / 'exports' / 'unsloth-handoffs'
FILES = ('sft.jsonl','multi_turn.jsonl')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def create_handoff(version, *, output_root=None):
    directory = _version_dir(version)
    manifest_raw = (directory/'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get('privacy_policy') != 'no_flagged_or_excluded_context_v1':
        raise ValidationError('This historical version has no verified context privacy policy. Keep it unchanged and create a fresh reviewed dataset version before Unsloth handoff.')
    legacy_validated = ('state' not in manifest and manifest.get('validation',{}).get('sft_targets_explicit') is True
                        and manifest.get('validation',{}).get('jsonl_parse_valid') is True)
    if manifest.get('state') != 'Frozen' and not legacy_validated:
        raise ValidationError('Unsloth handoff requires a frozen, explicitly validated dataset version.')
    hashes = manifest.get('sha256')
    if not isinstance(hashes, dict):
        raise ValidationError('Source manifest has no content hashes.')
    rows, provenance, source_bytes, seen = [], [], {}, set()
    quality_names = tuple(dict.fromkeys(KNOWN_FILES + (NATIVE_TRAIN_FILE,)))
    for name in quality_names:
        path = directory/name
        if not path.exists():
            if name in hashes:
                raise ValidationError('A manifest quality input is missing.')
            continue
        if path.is_symlink() or path.resolve().parent != directory.resolve() or path.stat().st_size > 128*1024*1024:
            raise ValidationError('Source training file is unsafe or exceeds the handoff size limit.')
        raw = source_bytes[name] = path.read_bytes()
        if hashes.get(name) != digest(raw):
            raise ValidationError('Source quality input no longer matches the frozen manifest hash.')
        if name not in FILES:
            continue
        for line in raw.decode('utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            _validate_sft_record(row,name)
            if (any(row.get(k) for k in ('evaluation_only','exclude_from_training','contains_personal_data','contains_sensitive_data','demo','deleted_at','ignored_at','archived'))
                or row.get('training_eligible') in (False,0) or
                ('review_status' in row and row['review_status'] not in TRAINING_REVIEW_STATUSES) or
                not row.get('origin') or not row.get('id')):
                raise ValidationError('A source record is not eligible for a reviewed conversational handoff.')
            messages = row['messages']
            if any(set(m) != {'role','content'} or m['role'] not in {'user','assistant'} or not isinstance(m['content'],str) for m in messages):
                raise ValidationError('This handoff supports plain user/assistant text only. System/tool/media objectives need a separate reviewed export.')
            if [m['role'] for m in messages] != ['user' if i%2==0 else 'assistant' for i in range(len(messages))]:
                raise ValidationError('Conversation roles must alternate and end with the sole approved assistant target.')
            converted = {'prompt':messages[:-1], 'completion':[messages[-1]]}
            key = digest(json.dumps(converted,ensure_ascii=False,sort_keys=True).encode('utf-8'))
            if key in seen:
                raise ValidationError('Duplicate training examples remain; review dataset deduplication before handoff.')
            seen.add(key)
            rows.append(converted)
            provenance.append({'line':len(rows),'source_file':name,'source_record_id':row['id'],
                'conversation_id':row.get('conversation_id'),'origin':row['origin'],'provider':row.get('provider'),
                'model_name':row.get('model_name'),'target_message_index':row['target_message_index'],
                'message_loss_mask':row['message_loss_mask'],
                **{key:row[key] for key in ('context_scope','context_complete') if key in row}})
    if not rows:
        raise ValidationError('The dataset has no eligible conversational targets.')
    # Reuse deterministic quality/leakage checks before publishing. Files not
    # used here (direct language, DPO, eval, native tools) are never mixed in.
    # Quality must see exactly the attested bytes, including holdout. Otherwise
    # an external writer could swap evaluation rows during leakage analysis.
    with tempfile.TemporaryDirectory(prefix='najdilab-quality-snapshot-') as snapshot:
        for name,raw in source_bytes.items():
            (Path(snapshot)/name).write_bytes(raw)
        quality = analyze_directory(Path(snapshot),version=version)
    if quality['counts']['confirmed_blocker']:
        raise ValidationError('Dataset quality/leakage checks have confirmed blockers.')
    output_root = Path(output_root) if output_root is not None else HANDOFFS
    output_root.mkdir(parents=True,exist_ok=True)
    handoff_id = uuid4().hex
    temp = Path(tempfile.mkdtemp(prefix='.handoff-',dir=output_root))
    final = output_root/handoff_id
    try:
        for name,items in (('dataset.jsonl',rows),('provenance.jsonl',provenance)):
            raw = ''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in items).encode('utf-8')
            (temp/name).write_bytes(raw)
        result = {'schema_version':1,'id':handoff_id,'created_at':utc_now(),'source_version':version,
                  'source_manifest_sha256':digest(manifest_raw),'source_sha256':{n:digest(b) for n,b in source_bytes.items()},
                  'record_count':len(rows),'format':'conversational_prompt_completion',
                  'trainer_requirements':{'completion_only_loss':True,'packing':False,'truncation':'reject_overlength_before_training'},
                  'sha256':{n:digest((temp/n).read_bytes()) for n in ('dataset.jsonl','provenance.jsonl')},
                  'omitted_objectives':['direct_language','preference_pairs','evaluation','native_tool_use'],
                  'warnings':['Prompt context is not a training target. Use completion_only_loss=True in external Unsloth/TRL; default all-assistant training changes the approved loss mask.',
                              'No model training or tokenizer compatibility test has run. Validate the chosen external model/template and reject overlength rows.'],
                  'quality_warning_count':quality['counts']['warning']}
        (temp/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # A concurrent source edit invalidates the handoff, never silently
        # changes its meaning. Existing source/export directories are untouched.
        if ((directory/'manifest.json').read_bytes()!=manifest_raw or
            any((directory/n).read_bytes()!=b for n,b in source_bytes.items()) or
            any((directory/n).exists() for n in quality_names if n not in source_bytes)):
            raise ValidationError('Source version changed while creating the handoff; retry after review.')
        os.rename(temp,final)
        return {**result,'directory':str(final),'download_url':f'/api/v1/unsloth-exports/{handoff_id}/dataset.jsonl'}
    except Exception:
        shutil.rmtree(temp,ignore_errors=True)
        raise


def read_handoff(handoff_id, name):
    if len(handoff_id)!=32 or any(c not in '0123456789abcdef' for c in handoff_id) or name not in {'dataset.jsonl','provenance.jsonl','manifest.json'}:
        raise ValidationError('Invalid handoff identifier.')
    directory=HANDOFFS/handoff_id
    path=directory/name
    if path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file():
        raise ValidationError('Handoff file is unavailable.')
    raw=path.read_bytes()
    if name!='manifest.json':
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        if digest(raw)!=manifest['sha256'].get(name):
            raise ValidationError('Handoff file no longer matches its manifest.')
    return raw
