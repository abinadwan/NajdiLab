from __future__ import annotations

from typing import Any, Callable

from .tool_runtime import repetition_diagnostic

HISTORICAL_PHASE3={"do_sample":False,"max_new_tokens":384}
RECOMMENDED_FUTURE={"do_sample":False,"max_new_tokens":256,"repetition_penalty":1.05,"no_repeat_ngram_size":0,"timeout_seconds":60,"eos":"tokenizer_eos","stop_behavior":"EOS plus validated tool-call boundary","runtime_repetition_stop":"diagnostic_only_until_model_validation"}


def validate_generation_config(value: dict[str, Any]) -> dict[str, Any]:
    allowed={"do_sample","max_new_tokens","repetition_penalty","no_repeat_ngram_size","timeout_seconds","eos","stop_behavior","runtime_repetition_stop"}
    if set(value)-allowed: raise ValueError("unsupported generation option")
    if not isinstance(value.get("max_new_tokens"),int) or not 1<=value["max_new_tokens"]<=4096: raise ValueError("invalid max_new_tokens")
    if not .9<=float(value.get("repetition_penalty",1))<=1.3: raise ValueError("unsafe repetition_penalty")
    if not 0<=int(value.get("no_repeat_ngram_size",0))<=12: raise ValueError("invalid no_repeat_ngram_size")
    if not 1<=int(value.get("timeout_seconds",60))<=600: raise ValueError("invalid timeout")
    return dict(value)


def diagnostic_experiment(prompts: list[dict[str,str]], candidates: dict[str,dict[str,Any]], runner: Callable[[str,dict[str,Any]],str]) -> dict[str,Any]:
    if not prompts or any(p.get("source")!="development" for p in prompts): raise ValueError("only non-holdout development prompts are allowed")
    output={}
    for name,config in candidates.items():
        validate_generation_config(config); cases=[]
        for prompt in prompts:
            response=runner(prompt["prompt"],config); cases.append({"id":prompt["id"],"response":response,"repetition":repetition_diagnostic(response,max_tokens=config["max_new_tokens"])})
        output[name]={"config":config,"cases":cases,"severe_repetition":sum(x["repetition"]["flagged"] for x in cases)}
    return {"development_only":True,"candidates":output,"selection_rule":"Prefer fewer severe repetitions only if human checks preserve Najdi language, instruction adherence, concision, tool calls, and normal conversation."}
