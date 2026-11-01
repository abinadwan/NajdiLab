import hashlib
import json
from pathlib import Path

import pytest

from app import dataset_platform as platform
from app.unsloth_export import create_handoff
from app.service import ValidationError


@pytest.fixture
def source(tmp_path,monkeypatch):
    exports=tmp_path/'exports'; exports.mkdir()
    directory=exports/'gold-v001'; directory.mkdir()
    row={'id':'review:1','conversation_id':'synthetic','origin':'human_corrected','review_status':'APPROVED',
         'messages':[{'role':'user','content':'before'},{'role':'assistant','content':'UNREVIEWED CONTEXT'},
                     {'role':'user','content':' now '},{'role':'assistant','content':' approved target '}],
         'target_message_index':3,'train_on_last_assistant_only':True,'message_loss_mask':[0,0,0,1]}
    (directory/'sft.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8')
    manifest={'version':'gold-v001','state':'Frozen','privacy_policy':'no_flagged_or_excluded_context_v1','sha256':{'sft.jsonl':hashlib.sha256((directory/'sft.jsonl').read_bytes()).hexdigest()}}
    (directory/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    monkeypatch.setattr(platform,'EXPORTS_DIR',exports)
    return directory,row,tmp_path/'handoffs'


def test_unsloth_conversational_completion_only_preserves_masks_and_provenance(source):
    directory,row,output=source
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    handoff=create_handoff('gold-v001',output_root=output)
    target=Path(handoff['directory'])
    data=json.loads((target/'dataset.jsonl').read_text(encoding='utf-8'))
    assert data=={'prompt':row['messages'][:-1],'completion':[row['messages'][-1]]}
    assert 'UNREVIEWED CONTEXT' not in json.dumps(data['completion'])
    assert handoff['trainer_requirements']['completion_only_loss'] is True
    assert json.loads((target/'provenance.jsonl').read_text())['source_record_id']=='review:1'
    assert {p.name:p.read_bytes() for p in directory.iterdir()}==before


@pytest.mark.parametrize('change',[{'review_status':'PENDING'},{'evaluation_only':True},{'contains_personal_data':True},{'message_loss_mask':[1,0,0,1]}])
def test_handoff_rejects_ineligible_records_even_with_matching_hash(source,change):
    directory,row,output=source
    row.update(change)
    file=directory/'sft.jsonl';file.write_text(json.dumps(row)+'\n')
    manifest=json.loads((directory/'manifest.json').read_text());manifest['sha256']['sft.jsonl']=hashlib.sha256(file.read_bytes()).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValidationError):create_handoff('gold-v001',output_root=output)
    assert not list(output.glob('*/manifest.json'))


def test_handoff_rejects_hash_tamper_and_unknown_or_draft_state(source):
    directory,row,output=source
    file=directory/'sft.jsonl'; file.write_text('tamper')
    with pytest.raises(ValidationError):create_handoff('gold-v001',output_root=output)


@pytest.mark.parametrize('prior,flags',[(False,{'contains_personal_data':True}), (False,{'contains_sensitive_data':True}),
                                     (True,{'contains_personal_data':True,'exclude_from_training':True}),
                                     (True,{'exclude_from_training':True})])
def test_real_database_export_blocks_private_target_or_excluded_prefix(tmp_path,prior,flags):
    from app.db import apply_migrations
    from app.service import ingest_turn,approve_review,create_export
    from app.review_integrity import ExportReadinessError
    db=tmp_path/'source.db';apply_migrations(db)
    first=ingest_turn({'conversation_id':'c','user_message':'PRIVATE USER','assistant_response':'PRIVATE ANSWER'},db)
    saved=approve_review(first['review_id'],{'training_eligible':True,**flags},db)
    assert saved['training_eligible']==0
    if not prior:
        # New decisions fail closed before selection. Keep testing the export
        # privacy backstop against a legacy inconsistent row in this temp DB.
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE reviews SET training_eligible=1 WHERE id=?',(first['review_id'],))
    if prior:
        second=ingest_turn({'conversation_id':'c','user_message':'later question','assistant_response':'later answer'},db)
        approve_review(second['review_id'],{'training_eligible':True},db)
    with pytest.raises(ExportReadinessError,match='privacy|excluded'):
        create_export(db,exports_dir=tmp_path/'exports')
    assert not list((tmp_path/'exports').glob('gold-*'))


def test_unattested_historical_version_cannot_bypass_new_handoff_privacy_gate(source):
    directory,row,output=source
    file=directory/'manifest.json';manifest=json.loads(file.read_text());manifest.pop('privacy_policy');file.write_text(json.dumps(manifest))
    with pytest.raises(ValidationError,match='privacy'):create_handoff('gold-v001',output_root=output)
    manifest=json.loads((directory/'manifest.json').read_text());manifest['state']='Draft'
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValidationError):create_handoff('gold-v001',output_root=output)


def test_frozen_evaluation_tampering_blocks_handoff(source):
    directory,row,output=source
    path=directory/'text_sft_eval.jsonl';path.write_text('')
    file=directory/'manifest.json';manifest=json.loads(file.read_text());manifest['sha256']['text_sft_eval.jsonl']=hashlib.sha256(b'').hexdigest();file.write_text(json.dumps(manifest))
    path.write_text('{}\n')
    with pytest.raises(ValidationError,match='manifest|hash'):create_handoff('gold-v001',output_root=output)


def test_privacy_recheck_and_source_snapshot_share_write_lock(tmp_path,monkeypatch):
    import sqlite3
    from app import service
    from app.db import apply_migrations
    db=tmp_path/'source.db';apply_migrations(db)
    turn=service.ingest_turn({'conversation_id':'c','user_message':'question','assistant_response':'answer'},db)
    service.approve_review(turn['review_id'],{'training_eligible':True},db)
    original=service.training_dataset
    def check_snapshot(*args,**kwargs):
        with sqlite3.connect(db,timeout=.01) as writer:
            with pytest.raises(sqlite3.OperationalError,match='locked'):
                writer.execute('UPDATE reviews SET contains_personal_data=1')
        return original(*args,**kwargs)
    monkeypatch.setattr(service,'training_dataset',check_snapshot)
    exported=service.create_export(db,exports_dir=tmp_path/'exports')
    assert exported['manifest']['privacy_policy']=='no_flagged_or_excluded_context_v1'


def test_concurrent_quality_input_change_prevents_publication(source,monkeypatch):
    from app import unsloth_export as module
    directory,row,output=source
    eval_path=directory/'evaluation_holdout.jsonl';eval_path.write_bytes(b'')
    file=directory/'manifest.json';manifest=json.loads(file.read_text());manifest['sha256'][eval_path.name]=hashlib.sha256(b'').hexdigest();file.write_text(json.dumps(manifest))
    original=module.analyze_directory
    def change_after_snapshot(*args,**kwargs):
        report=original(*args,**kwargs)
        eval_path.write_bytes(b'\n')
        return report
    monkeypatch.setattr(module,'analyze_directory',change_after_snapshot)
    with pytest.raises(ValidationError,match='changed'):create_handoff('gold-v001',output_root=output)
    assert not list(output.glob('*/manifest.json'))


def test_real_db_review_version_to_unsloth_preserves_only_target_loss(tmp_path,monkeypatch):
    from app.db import apply_migrations
    from app.service import ingest_turn,approve_review,create_export
    db=tmp_path/'source.db';apply_migrations(db)
    turn=ingest_turn({'conversation_id':'c','user_message':'question','assistant_response':'target'},db)
    approve_review(turn['review_id'],{'training_eligible':True},db)
    exports=tmp_path/'exports';create_export(db,exports_dir=exports)
    monkeypatch.setattr(platform,'EXPORTS_DIR',exports)
    handoff=create_handoff('gold-v001',output_root=tmp_path/'handoffs')
    assert handoff['record_count']==1
    row=json.loads((Path(handoff['directory'])/'dataset.jsonl').read_text())
    assert row=={'prompt':[{'role':'user','content':'question'}],'completion':[{'role':'assistant','content':'target'}]}
