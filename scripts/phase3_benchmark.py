#!/usr/bin/env python3
"""Deterministic Phase 3 Base/Adapter benchmark and approval-gated comparison."""
from __future__ import annotations

# Historical helpers only; no direct model/GGUF/runtime execution.
if __name__ == '__main__':
    raise SystemExit('This workflow is retired. Export a reviewed dataset for external Unsloth.')

import argparse, gc, hashlib, json, random, time
from difflib import SequenceMatcher
from pathlib import Path

EVAL_FILES=("text_sft_eval.jsonl","tool_eval.jsonl","vision_eval.jsonl","runtime_agent_eval.jsonl")
SEED=3407
GENERATION={"do_sample":False,"max_new_tokens":384}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(root: Path) -> list[dict]:
    rows=[]
    for name in EVAL_FILES:
        path=root/name
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row=json.loads(line); row["evaluation_file"]=name; rows.append(row)
    ids=[str(row.get("id")) for row in rows]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate evaluation ids")
    return rows


def evaluation_case(row: dict) -> tuple[list[dict],str]:
    messages=row.get("messages"); target=row.get("target_message_index"); mask=row.get("message_loss_mask")
    if not isinstance(messages,list) or target!=len(messages)-1 or mask!=[0]*target+[1]: raise ValueError(f"{row.get('id')}: invalid evaluation target")
    if messages[target].get("role")!="assistant" or not messages[:target] or messages[target-1].get("role")!="user": raise ValueError(f"{row.get('id')}: invalid roles")
    return messages[:target],messages[target]["content"]


def write_json(path: Path,value) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); tmp.replace(path)


def write_jsonl(path: Path,rows: list[dict]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text("".join(json.dumps(x,ensure_ascii=False,separators=(",",":"))+"\n" for x in rows),encoding="utf-8"); tmp.replace(path)


def benchmark(args) -> None:
    import numpy as np, torch
    from peft import PeftModel
    try:
        from unsloth import FastModel
    except Exception:
        from unsloth import FastLanguageModel as FastModel
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED)
    rows=read_rows(args.dataset); model,processor=FastModel.from_pretrained(model_name=str(args.model),max_seq_length=8192,load_in_4bit=True,load_in_8bit=False,full_finetuning=False)
    tokenizer=getattr(processor,"tokenizer",processor)
    if args.adapter:
        if not (args.adapter/"adapter_model.safetensors").is_file(): raise FileNotFoundError(args.adapter)
        model=PeftModel.from_pretrained(model,str(args.adapter))
    model.eval(); results=[]; started=time.time(); torch.cuda.reset_peak_memory_stats()
    for index,row in enumerate(rows,1):
        context,gold=evaluation_case(row); renderer=processor if hasattr(processor,"apply_chat_template") else tokenizer
        rendered=renderer.apply_chat_template(context,tokenize=False,add_generation_prompt=True); inputs=tokenizer(rendered,return_tensors="pt",add_special_tokens=False,truncation=False)
        prompt_tokens=int(inputs["input_ids"].shape[-1])
        if prompt_tokens>8192: raise RuntimeError(f"{row['id']}: prompt too long")
        inputs={k:v.to(model.device) for k,v in inputs.items()}
        print(f"{args.label} {index}/{len(rows)} {row['id']}",flush=True)
        with torch.inference_mode(): output=model.generate(**inputs,**GENERATION,pad_token_id=tokenizer.eos_token_id,eos_token_id=tokenizer.eos_token_id)
        response=tokenizer.decode(output[0][prompt_tokens:].tolist(),skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
        if not response: raise RuntimeError(f"{row['id']}: empty response")
        results.append({"id":str(row["id"]),"evaluation_file":row["evaluation_file"],"category":row.get("evaluation_subcategory") or row.get("evaluation_category"),"conversation_id":row.get("conversation_id"),"gold":gold,"response":response,"prompt_tokens":prompt_tokens})
    write_jsonl(args.output,results)
    meta={"phase":"3","label":args.label,"records":len(results),"seed":SEED,"generation":GENERATION,"dataset_fingerprint_files":{name:sha256(args.dataset/name) for name in EVAL_FILES},"model_config_sha256":sha256(args.model/"config.json"),"adapter":str(args.adapter) if args.adapter else None,"adapter_config_sha256":sha256(args.adapter/"adapter_config.json") if args.adapter else None,"elapsed_seconds":round(time.time()-started,3),"peak_vram_allocated_mib":round(torch.cuda.max_memory_allocated()/1024**2,1),"peak_vram_reserved_mib":round(torch.cuda.max_memory_reserved()/1024**2,1),"output_sha256":sha256(args.output),"completed_at":time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write_json(args.output.with_suffix(".meta.json"),meta); print(json.dumps(meta,ensure_ascii=False),flush=True); del model; gc.collect(); torch.cuda.empty_cache()


def comparison(base: list[dict],adapter: list[dict]) -> dict:
    b={x["id"]:x for x in base}; a={x["id"]:x for x in adapter}
    if set(b)!=set(a): raise ValueError("benchmark ids differ")
    samples=[]
    for sample_id in b:
        if b[sample_id]["gold"]!=a[sample_id]["gold"]: raise ValueError("gold target mismatch")
        gold=b[sample_id]["gold"]; br=b[sample_id]["response"]; ar=a[sample_id]["response"]
        samples.append({"id":sample_id,"evaluation_file":b[sample_id]["evaluation_file"],"category":b[sample_id].get("category"),"gold":gold,"base_response":br,"adapter_response":ar,"automatic":{"base_exact":br==gold,"adapter_exact":ar==gold,"base_similarity":round(SequenceMatcher(None,br,gold).ratio(),4),"adapter_similarity":round(SequenceMatcher(None,ar,gold).ratio(),4)},"human_review":{"winner":None,"scores":None,"notes":""}})
    return {"phase":"3","status":"PENDING_HUMAN_APPROVAL","records":len(samples),"automatic_summary":{"base_exact":sum(x["automatic"]["base_exact"] for x in samples),"adapter_exact":sum(x["automatic"]["adapter_exact"] for x in samples),"base_mean_similarity":round(sum(x["automatic"]["base_similarity"] for x in samples)/len(samples),4),"adapter_mean_similarity":round(sum(x["automatic"]["adapter_similarity"] for x in samples)/len(samples),4)},"approval_gate":{"status":"PENDING","approved":False,"phase4a_allowed":False,"requires_explicit_human_approval":True},"samples":samples}


def compare(args) -> None:
    base=[json.loads(x) for x in args.base.read_text(encoding="utf-8").splitlines() if x.strip()]; adapter=[json.loads(x) for x in args.adapter.read_text(encoding="utf-8").splitlines() if x.strip()]
    result=comparison(base,adapter); result["base_sha256"]=sha256(args.base); result["adapter_sha256"]=sha256(args.adapter); write_json(args.output,result); print(json.dumps({k:v for k,v in result.items() if k!="samples"},ensure_ascii=False))


def main() -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    b=sub.add_parser("benchmark"); b.add_argument("--dataset",type=Path,required=True); b.add_argument("--model",type=Path,required=True); b.add_argument("--adapter",type=Path); b.add_argument("--label",required=True); b.add_argument("--output",type=Path,required=True)
    c=sub.add_parser("compare"); c.add_argument("--base",type=Path,required=True); c.add_argument("--adapter",type=Path,required=True); c.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); benchmark(args) if args.command=="benchmark" else compare(args); return 0


if __name__=="__main__": raise SystemExit(main())
