#!/usr/bin/env python3
"""NajdiLab generic validation/smoke adapter. Full training is deliberately unsupported."""
from __future__ import annotations

# Retained for historical validation imports, retired as an executable.
if __name__ == '__main__':
    raise SystemExit('Training is retired in NajdiLab. Export a reviewed dataset for external Unsloth.')


import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
from typing import Any

from train_najdi_sft import MaskedSFTDataCollator, load_masked_training_records


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def read_rows(paths: list[Path]) -> list[dict[str,Any]]:
    rows=[]
    for path in paths:
        if not path.is_file(): raise FileNotFoundError(path)
        for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            row=json.loads(line); messages=row.get("messages"); mask=row.get("message_loss_mask"); target=row.get("target_message_index")
            if not isinstance(messages,list) or not messages or target != len(messages)-1 or messages[-1].get("role") != "assistant": raise ValueError(f"invalid target at {path}:{number}")
            if not isinstance(mask,list) or len(mask)!=len(messages) or mask.count(1)!=1 or mask[target]!=1 or row.get("train_on_last_assistant_only") is not True: raise ValueError(f"invalid loss mask at {path}:{number}")
            rows.append(row)
    if not rows: raise ValueError("empty training dataset")
    return rows


def read_jsonl(path: Path) -> list[dict[str,Any]]:
    if not path.is_file(): raise FileNotFoundError(path)
    rows=[]
    for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"malformed JSON at {path}:{number}: {exc}") from exc
        if not isinstance(row,dict): raise ValueError(f"record must be an object at {path}:{number}")
        rows.append(row)
    return rows


def validate_native_inputs(native_path: Path | None, registry_path: Path | None, model_path: Path, max_length: int, *, tokenizer: Any | None=None) -> tuple[list[dict[str,Any]],dict[str,Any]|None,dict[str,Any]]:
    """Validate registry binding, every native record, and token-level masks before model load."""
    if bool(native_path) != bool(registry_path): raise ValueError("--native-tool-file and --capability-registry must be supplied together")
    if native_path is None: return [],None,{"status":"NOT_PRESENT","records":0,"loss_masks_valid":0,"optimizer_steps":0}
    if not native_path.is_file(): raise FileNotFoundError(native_path)
    if not registry_path or not registry_path.is_file(): raise FileNotFoundError(registry_path)
    try:
        from app.tool_runtime import load_registry
        from app.native_tool_data import validate_native_tool_record
    except ImportError:
        from tool_runtime import load_registry
        from native_tool_data import validate_native_tool_record
    from train_najdi_sft import encode_masked_native_tool_record, IGNORE_INDEX
    registry=load_registry(registry_path); rows=read_jsonl(native_path)
    if not rows: raise ValueError("native tool file is empty")
    manifest_path=native_path.parent/"manifest.json"
    if manifest_path.is_file():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8")); binding=manifest.get("capability_registry") or {}
        if binding.get("version")!=registry["registry_version"] or binding.get("fingerprint")!=registry["fingerprint"]: raise ValueError("capability registry does not match dataset manifest")
        expected_hash=(manifest.get("sha256") or {}).get("capability-registry.json")
        if expected_hash and sha256(registry_path)!=expected_hash: raise ValueError("capability registry file hash does not match dataset manifest")
    evidence_path=native_path.parent/"native-tool-loss-mask-validation.json"
    if not evidence_path.is_file(): raise FileNotFoundError(evidence_path)
    evidence=json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("capability_registry_fingerprint")!=registry["fingerprint"] or evidence.get("total")!=len(rows) or evidence.get("passed")!=len(rows) or evidence.get("failures"):
        raise ValueError("native tool loss-mask evidence is missing, stale, or incomplete")
    validations=[validate_native_tool_record(row,registry) for row in rows]
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(str(model_path),local_files_only=True,trust_remote_code=True)
    encoded=[encode_masked_native_tool_record(row,tokenizer,registry,max_length) for row in rows]
    for row,validation,item in zip(rows,validations,encoded):
        labels=item["labels"]
        if not item.get("tool_results_masked") or not any(x!=IGNORE_INDEX for x in labels): raise ValueError(f"invalid native loss mask for {row.get('id')}")
        kinds=item.get("supervised_segments") or []
        if "final_response" not in kinds or validation["tool_calls"] and "tool_call" not in kinds: raise ValueError(f"missing supervised native segment for {row.get('id')}")
    diagnostics={"status":"PASS","records":len(rows),"validated_records":len(validations),"loss_masks_valid":len(encoded),"tool_results_masked":sum(bool(x.get("tool_results_masked")) for x in encoded),"assistant_tool_call_records_supervised":sum("tool_call" in x.get("supervised_segments",[]) for x in encoded),"assistant_final_responses_supervised":sum("final_response" in x.get("supervised_segments",[]) for x in encoded),"registry_version":registry["registry_version"],"registry_fingerprint":registry["fingerprint"],"serialization":{"tools":"[AVAILABLE_TOOLS]...[/AVAILABLE_TOOLS]","tool_calls":"[TOOL_CALLS]<name>[ARGS]<canonical JSON>","tool_results":"[TOOL_RESULTS]<canonical JSON>[/TOOL_RESULTS]"},"optimizer_steps":0}
    return rows,registry,diagnostics


def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description=__doc__); mode=p.add_mutually_exclusive_group(required=True); mode.add_argument("--validate-only",action="store_true"); mode.add_argument("--smoke-test",action="store_true"); mode.add_argument("--full-training",action="store_true")
    for name in ("model-path","sft-file","multi-turn-file","output-dir","checkpoint-dir","logs-dir"): p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--model-id", default="legacy-unspecified"); p.add_argument("--model-revision", default="local")
    p.add_argument("--native-tool-file",type=Path); p.add_argument("--capability-registry",type=Path)
    p.add_argument("--epochs",type=float,default=1); p.add_argument("--max-steps",type=int,default=-1); p.add_argument("--expected-steps",type=int,required=True); p.add_argument("--save-steps",type=int,default=0); p.add_argument("--learning-rate",type=float,default=2e-4); p.add_argument("--batch-size",type=int,default=1); p.add_argument("--gradient-accumulation-steps",type=int,default=8); p.add_argument("--max-seq-length",type=int,default=2048); p.add_argument("--warmup-ratio",type=float,default=.03); p.add_argument("--weight-decay",type=float,default=.01); p.add_argument("--lr-scheduler",choices=("linear","cosine","constant","constant_with_warmup"),default="cosine"); p.add_argument("--seed",type=int,default=3407); p.add_argument("--optimizer",choices=("adamw_8bit","paged_adamw_8bit","adamw_torch"),default="adamw_8bit")
    p.add_argument("--bf16",action="store_true"); p.add_argument("--fp16",action="store_true"); p.add_argument("--lora-r",type=int,default=16); p.add_argument("--lora-alpha",type=int,default=32); p.add_argument("--lora-dropout",type=float,default=0); p.add_argument("--target-modules",default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj"); p.add_argument("--gradient-checkpointing",action="store_true"); p.add_argument("--packing",action="store_true")
    return p


def resolve_plan(records: int, batch_size: int, gradient_accumulation_steps: int, epochs: float, max_steps: int) -> dict[str,Any]:
    """Calculate training plan with proper handling of smoke test vs full training."""
    batches = math.ceil(records / batch_size)
    steps_epoch = math.ceil(batches / gradient_accumulation_steps)
    
    if max_steps == -1:
        # Full training: use epochs to calculate total steps
        total = steps_epoch * epochs
    else:
        # Limited training (smoke test): cap at max_steps
        total = min(steps_epoch * epochs, max_steps)
    
    return {
        "batches_per_epoch": batches,
        "optimizer_steps_per_epoch": steps_epoch,
        "estimated_total_optimizer_steps": total,
        "trainer_max_steps": max_steps if max_steps > 0 else -1,
        "max_steps_override": max_steps if max_steps > 0 else None
    }


def validate(a: argparse.Namespace) -> dict[str,Any]:
    if not a.model_path.is_dir(): raise FileNotFoundError(a.model_path)
    if a.bf16 and a.fp16: raise ValueError("bf16 and fp16 are mutually exclusive")
    if min(a.epochs,a.learning_rate,a.batch_size,a.gradient_accumulation_steps,a.max_seq_length,a.lora_r,a.lora_alpha)<=0: raise ValueError("positive training values required")
    if a.packing: raise ValueError("packing is not supported by the current masked-record pipeline")
    rows=read_rows([a.sft_file,a.multi_turn_file])
    native_rows,registry,native_diagnostics=validate_native_inputs(a.native_tool_file,a.capability_registry,a.model_path,a.max_seq_length)
    native_count=len(native_rows)
    tokenizer_paths=[p for p in a.model_path.iterdir() if p.name in {"tokenizer.json","tokenizer.model","tokenizer_config.json","chat_template.jinja"}]; tokenizer_files=[p.name for p in tokenizer_paths]
    if not tokenizer_files: raise FileNotFoundError("tokenizer files missing")
    for path in (a.output_dir,a.checkpoint_dir,a.logs_dir):
        parent=path if path.exists() else next((x for x in path.parents if x.exists()),None)
        if parent is None or not os.access(parent,os.W_OK): raise PermissionError(path)
    config=a.model_path/"config.json"
    
    # Validate Smoke Test and Full Training plans separately.
    if a.smoke_test and a.max_steps==2:
        # Smoke Test: compare the full plan (without max_steps) with expected-steps.
        full_plan=resolve_plan(len(rows)+native_count,a.batch_size,a.gradient_accumulation_steps,a.epochs,-1)
        if full_plan["estimated_total_optimizer_steps"] != a.expected_steps: raise RuntimeError(f"TRAINING_PLAN_MISMATCH: expected {a.expected_steps}, resolved {full_plan['estimated_total_optimizer_steps']}")
        # Apply max_steps=2 only to the actual execution.
        plan=resolve_plan(len(rows)+native_count,a.batch_size,a.gradient_accumulation_steps,a.epochs,a.max_steps)
    elif not a.smoke_test:
        # Full Training: validate the plan against max_steps and expected-steps.
        plan=resolve_plan(len(rows)+native_count,a.batch_size,a.gradient_accumulation_steps,a.epochs,a.max_steps)
        if plan["estimated_total_optimizer_steps"] != a.expected_steps or plan["trainer_max_steps"] != a.max_steps: raise RuntimeError(f"TRAINING_PLAN_MISMATCH: expected {a.expected_steps}, resolved {plan['estimated_total_optimizer_steps']}")
    else:
        # Validate-only or other modes.
        plan=resolve_plan(len(rows)+native_count,a.batch_size,a.gradient_accumulation_steps,a.epochs,a.max_steps)
    
    tokenizer_hashes={p.name:sha256(p) for p in tokenizer_paths}; tokenizer_fingerprint=hashlib.sha256(json.dumps(tokenizer_hashes,sort_keys=True).encode()).hexdigest()
    return {"status":"VALID","mode":"VALIDATE_ONLY" if a.validate_only else "SMOKE" if a.smoke_test else "FULL","training_started":False,"optimizer_steps_executed":0,"training_records":len(rows)+native_count,"sft":sum(1 for _ in a.sft_file.read_text(encoding="utf-8").splitlines() if _.strip()),"multi_turn":sum(1 for _ in a.multi_turn_file.read_text(encoding="utf-8").splitlines() if _.strip()),"native_tool_use":native_count,"direct_language":0,"preference_pairs":0,"native_tool_validation":native_diagnostics,"model_config_sha256":sha256(config) if config.is_file() else None,"tokenizer_files":tokenizer_files,"tokenizer_sha256":tokenizer_hashes,"tokenizer_fingerprint":tokenizer_fingerprint,"chat_template_file_sha256":tokenizer_hashes.get("chat_template.jinja"),"smoke_max_steps":2,"epochs":a.epochs,**plan}


class Rows:
    def __init__(self,rows): self.rows=rows
    def __len__(self): return len(self.rows)
    def __getitem__(self,index): return self.rows[index]


def train(a: argparse.Namespace, result: dict[str,Any]) -> dict[str,Any]:
    os.environ.setdefault("UNSLOTH_COMPILE_DISABLE","1")
    import torch
    from transformers import Trainer,TrainingArguments,TrainerCallback
    from unsloth import FastModel
    if not torch.cuda.is_available(): raise RuntimeError("CUDA unavailable")
    started=time.time(); a.output_dir.mkdir(parents=True,exist_ok=False); a.checkpoint_dir.mkdir(parents=True,exist_ok=False); a.logs_dir.mkdir(parents=True,exist_ok=True); metrics_path=a.logs_dir/"metrics.jsonl"
    model, processor=FastModel.from_pretrained(model_name=str(a.model_path),max_seq_length=a.max_seq_length,load_in_4bit=True,load_in_8bit=False,full_finetuning=False)
    tokenizer=getattr(processor,"tokenizer",processor)
    if not getattr(tokenizer,"chat_template",None): raise RuntimeError("tokenizer chat template missing")
    chat_hash=hashlib.sha256(tokenizer.chat_template.encode("utf-8")).hexdigest(); registry=None
    if a.native_tool_file:
        try: from app.tool_runtime import load_registry
        except ImportError: from tool_runtime import load_registry
        registry=load_registry(a.capability_registry)
    records=load_masked_training_records(a.sft_file.parent,tokenizer,a.max_seq_length,registry)
    if len(records)!=result["training_records"]: raise RuntimeError("loss-mask record count mismatch")
    model=FastModel.get_peft_model(model,finetune_vision_layers=False,finetune_language_layers=True,finetune_attention_modules=True,finetune_mlp_modules=True,r=a.lora_r,lora_alpha=a.lora_alpha,lora_dropout=a.lora_dropout,bias="none",random_state=a.seed,use_gradient_checkpointing="unsloth" if a.gradient_checkpointing else False)
    class Metrics(TrainerCallback):
        def on_log(self,args,state,control,logs=None,**kwargs):
            if logs and "loss" in logs:
                item={"step":int(state.global_step),"max_steps":int(state.max_steps),"epoch":float(state.epoch or 0),"loss":float(logs["loss"]),"learning_rate":logs.get("learning_rate"),"elapsed_seconds":round(time.time()-started,3),"vram_allocated_mib":round(torch.cuda.memory_allocated()/1024**2,1),"vram_reserved_mib":round(torch.cuda.memory_reserved()/1024**2,1)}
                with metrics_path.open("a",encoding="utf-8") as f: f.write(json.dumps(item)+"\n")
                print("NAJDILAB_METRIC="+json.dumps(item),flush=True)
    full=bool(a.full_training); enforced_steps=2 if a.smoke_test else (a.max_steps if a.max_steps>0 else -1)
    args=TrainingArguments(output_dir=str(a.checkpoint_dir),num_train_epochs=a.epochs,max_steps=enforced_steps,per_device_train_batch_size=a.batch_size,gradient_accumulation_steps=a.gradient_accumulation_steps,learning_rate=a.learning_rate,warmup_ratio=a.warmup_ratio,weight_decay=a.weight_decay,lr_scheduler_type=a.lr_scheduler,logging_steps=1,save_strategy="steps" if full and a.save_steps>0 else "no",save_steps=max(1,a.save_steps),save_total_limit=2,bf16=a.bf16,fp16=a.fp16,optim=a.optimizer,seed=a.seed,data_seed=a.seed,remove_unused_columns=False,report_to="none",dataloader_num_workers=0)
    trainer=Trainer(model=model,args=args,train_dataset=Rows(records),data_collator=MaskedSFTDataCollator(tokenizer),callbacks=[Metrics()])
    full_plan=resolve_plan(len(records),a.batch_size,a.gradient_accumulation_steps,a.epochs,-1)
    execution_plan=resolve_plan(len(records),a.batch_size,a.gradient_accumulation_steps,a.epochs,enforced_steps)
    plan_mismatch=full_plan["estimated_total_optimizer_steps"] != a.expected_steps
    if a.full_training: plan_mismatch = plan_mismatch or execution_plan["estimated_total_optimizer_steps"] != a.expected_steps
    if plan_mismatch or trainer.args.max_steps != execution_plan["trainer_max_steps"]: raise RuntimeError("TRAINING_PLAN_MISMATCH: adapter and manifest plans differ")
    torch.cuda.reset_peak_memory_stats(); train_result=trainer.train(); metrics=[json.loads(x) for x in metrics_path.read_text().splitlines()]
    losses=[x["loss"] for x in metrics];
    expected=2 if a.smoke_test else (a.max_steps if a.max_steps>0 else math.ceil(len(records)/a.batch_size/a.gradient_accumulation_steps*a.epochs))
    if trainer.state.global_step!=expected or not losses or not all(math.isfinite(x) for x in losses): raise RuntimeError("training success criteria failed")
    adapter=a.output_dir/"adapter"; adapter.mkdir(); model.save_pretrained(str(adapter)); tokenizer.save_pretrained(str(adapter))
    marker=a.output_dir/("TRAINED_ADAPTER_NOT_YET_EVALUATED_NOT_APPROVED_FOR_DEPLOYMENT" if full else "SMOKE_ONLY_NOT_FOR_DEPLOYMENT"); marker.write_text(("TRAINED ADAPTER\nNOT YET EVALUATED\nNOT APPROVED FOR DEPLOYMENT\n" if full else "SMOKE ONLY\nNOT APPROVED FOR DEPLOYMENT\n"))
    return {**result,"status":"PASSED","mode":"FULL" if full else "SMOKE","global_step":trainer.state.global_step,"expected_steps":expected,"epochs_completed":float(trainer.state.epoch or 0),"losses":losses,"first_loss":losses[0],"last_loss":losses[-1],"min_loss":min(losses),"max_loss":max(losses),"mean_loss":sum(losses)/len(losses),"nan_or_inf":False,"elapsed_seconds":round(time.time()-started,3),"peak_vram_allocated_mib":round(torch.cuda.max_memory_allocated()/1024**2,1),"peak_vram_reserved_mib":round(torch.cuda.max_memory_reserved()/1024**2,1),"adapter_path":str(adapter),"checkpoints":sorted(str(x) for x in a.checkpoint_dir.glob("checkpoint-*")),"chat_template_sha256":chat_hash,"tokenizer_class":type(tokenizer).__name__,"token_ids":{"bos":tokenizer.bos_token_id,"eos":tokenizer.eos_token_id,"pad":tokenizer.pad_token_id,"unk":tokenizer.unk_token_id},"trainer_metrics":{k:v for k,v in train_result.metrics.items() if isinstance(v,(int,float))}}


def main() -> int:
    try:
        a=parser().parse_args(); result=validate(a)
        if a.validate_only: print(json.dumps(result,ensure_ascii=False)); return 0
        result=train(a,result); (a.output_dir/("training-result.json" if a.full_training else "smoke-result.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print("NAJDILAB_RESULT="+json.dumps(result,ensure_ascii=False)); return 0
    except Exception as exc:
        print("NAJDILAB_ERROR="+json.dumps({"type":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr,flush=True); return 1

if __name__=="__main__": raise SystemExit(main())
