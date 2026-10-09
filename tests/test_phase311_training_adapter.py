import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

from najdilab_training_adapter import parser, resolve_plan, validate_native_inputs
from app.tool_runtime import load_registry
from tests.test_phase37_tool_hardening import CharTokenizer, record


def test_parser_accepts_native_contract_and_old_invocation():
    base=["--validate-only","--model-path","m","--sft-file","s","--multi-turn-file","x","--output-dir","o","--checkpoint-dir","c","--logs-dir","l","--expected-steps","1"]
    old=parser().parse_args(base); assert old.native_tool_file is None and old.capability_registry is None
    new=parser().parse_args(base+["--native-tool-file","n","--capability-registry","r"]); assert new.native_tool_file==Path("n") and new.capability_registry==Path("r")


def test_native_arguments_are_required_together(tmp_path):
    with pytest.raises(ValueError,match="supplied together"): validate_native_inputs(tmp_path/"native.jsonl",None,tmp_path,2048,tokenizer=CharTokenizer())


def _fixture(tmp_path):
    registry=load_registry(ROOT/"config"/"tool-capabilities.v1.json")
    registry_path=tmp_path/"capability-registry.json"; registry_path.write_text(json.dumps({k:v for k,v in registry.items() if k!="fingerprint"}),encoding="utf-8")
    native=tmp_path/"native_tool_use.jsonl"; native.write_text(json.dumps(record(registry),ensure_ascii=False)+"\n",encoding="utf-8")
    evidence={"capability_registry_fingerprint":registry["fingerprint"],"total":1,"passed":1,"failures":[]}
    (tmp_path/"native-tool-loss-mask-validation.json").write_text(json.dumps(evidence),encoding="utf-8")
    return native,registry_path,registry


def test_native_validation_checks_registry_and_masks(tmp_path):
    native,registry_path,registry=_fixture(tmp_path)
    rows,loaded,diagnostics=validate_native_inputs(native,registry_path,tmp_path,2048,tokenizer=CharTokenizer())
    assert len(rows)==1 and loaded["fingerprint"]==registry["fingerprint"]
    assert diagnostics["loss_masks_valid"]==1 and diagnostics["tool_results_masked"]==1
    assert diagnostics["assistant_tool_call_records_supervised"]==1 and diagnostics["assistant_final_responses_supervised"]==1
    assert diagnostics["optimizer_steps"]==0


def test_missing_or_stale_registry_blocks(tmp_path):
    native,registry_path,_=_fixture(tmp_path); registry_path.unlink()
    with pytest.raises(FileNotFoundError): validate_native_inputs(native,registry_path,tmp_path,2048,tokenizer=CharTokenizer())
    native,registry_path,_=_fixture(tmp_path)
    evidence=json.loads((tmp_path/"native-tool-loss-mask-validation.json").read_text()); evidence["capability_registry_fingerprint"]="stale"
    (tmp_path/"native-tool-loss-mask-validation.json").write_text(json.dumps(evidence),encoding="utf-8")
    with pytest.raises(ValueError,match="stale"): validate_native_inputs(native,registry_path,tmp_path,2048,tokenizer=CharTokenizer())


def test_malformed_and_unsupported_tool_records_block(tmp_path):
    native,registry_path,registry=_fixture(tmp_path); native.write_text("{bad\n",encoding="utf-8")
    with pytest.raises(ValueError,match="malformed JSON"): validate_native_inputs(native,registry_path,tmp_path,2048,tokenizer=CharTokenizer())
    native,registry_path,registry=_fixture(tmp_path); bad=record(registry); bad["messages"][2]["tool_calls"][0]["function"]["name"]="missing.tool"
    native.write_text(json.dumps(bad)+"\n",encoding="utf-8")
    with pytest.raises(ValueError): validate_native_inputs(native,registry_path,tmp_path,2048,tokenizer=CharTokenizer())


def test_max_steps_zero_never_reaches_trainer():
    assert resolve_plan(66,1,8,2.0,0)["trainer_max_steps"]==-1
