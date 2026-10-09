from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "tool-capabilities.v1.json"
EVENT_STATES = {"TOOL_CALL_REQUESTED", "TOOL_CALL_VALIDATED", "TOOL_EXECUTION_STARTED", "TOOL_RESULT", "TOOL_ERROR", "TOOL_EXECUTION_DENIED"}
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")


class ToolContractError(ValueError): pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def registry_fingerprint(registry: dict[str, Any]) -> str:
    value = {k: v for k, v in registry.items() if k != "fingerprint"}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not isinstance(value.get("registry_version"), str):
        raise ToolContractError("unsupported capability registry")
    names=set()
    for tool in value.get("tools", []):
        if not TOOL_NAME.fullmatch(str(tool.get("name") or "")) or tool["name"] in names:
            raise ToolContractError("invalid or duplicate tool name")
        names.add(tool["name"])
        for key in ("description", "arguments_schema", "result_schema", "error_schema", "execution_availability", "execution_target", "classification", "approval_required", "timeout_seconds", "controller_authority"):
            if key not in tool: raise ToolContractError(f"{tool['name']}: missing {key}")
    value["fingerprint"] = registry_fingerprint(value)
    return value


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors=[]; kind=schema.get("type")
    types={"object":dict,"array":list,"string":str,"integer":int,"number":(int,float),"boolean":bool}
    if kind in types and (not isinstance(value,types[kind]) or kind in {"integer","number"} and isinstance(value,bool)):
        return [f"{path}: expected {kind}"]
    if "enum" in schema and value not in schema["enum"]: errors.append(f"{path}: value not in enum")
    if kind=="object" and isinstance(value,dict):
        props=schema.get("properties",{}); required=schema.get("required",[])
        errors += [f"{path}.{x}: required" for x in required if x not in value]
        if schema.get("additionalProperties") is False: errors += [f"{path}.{x}: additional property" for x in value if x not in props]
        for name,item in value.items():
            if name in props: errors += _validate_schema(item,props[name],f"{path}.{name}")
    if kind=="array" and isinstance(value,list) and "items" in schema:
        for i,item in enumerate(value): errors += _validate_schema(item,schema["items"],f"{path}[{i}]")
    return errors


def visible_tools(registry: dict[str, Any], available: set[str]) -> list[dict[str, Any]]:
    return [{"type":"function","function":{"name":t["name"],"description":t["description"],"parameters":t["arguments_schema"]}} for t in registry["tools"] if t["name"] in available]


def capability_context(registry: dict[str, Any], available: set[str], runtime_target: str) -> dict[str, Any]:
    tools=visible_tools(registry,available)
    return {"registry_version":registry["registry_version"],"registry_fingerprint":registry["fingerprint"],"runtime_target":runtime_target,"tools":tools,"statement":"Only listed tools are available. Execution is real only after an authoritative controller TOOL_RESULT event."}


def canonical_conversation(messages: list[dict[str, Any]], registry: dict[str, Any], available: set[str]) -> dict[str, Any]:
    normalized=[]
    for message in messages:
        item={"role":message.get("role")}
        if "content" in message:
            content=message["content"]
            if item["role"]=="tool" and not isinstance(content,str): content=canonical_json(content)
            item["content"]=content
        if message.get("tool_calls"):
            item["tool_calls"]=[parse_tool_call(call,registry,available) for call in message["tool_calls"]]
        for key in ("tool_call_id","name","authoritative"):
            if key in message: item[key]=message[key]
        normalized.append(item)
    return {"serialization":"ministral-native-v1","tools":visible_tools(registry,available),"messages":normalized}


def parse_tool_call(value: Any, registry: dict[str, Any], available: set[str]) -> dict[str, Any]:
    if not isinstance(value,dict) or set(value) != {"id","type","function"} or value.get("type")!="function": raise ToolContractError("malformed tool call")
    fn=value.get("function");
    if not isinstance(fn,dict) or set(fn)!={"name","arguments"} or not isinstance(value["id"],str): raise ToolContractError("malformed tool function")
    tool=next((t for t in registry["tools"] if t["name"]==fn.get("name")),None)
    if tool is None or tool["name"] not in available: raise ToolContractError("tool unavailable")
    try: args=json.loads(fn["arguments"]) if isinstance(fn["arguments"],str) else fn["arguments"]
    except json.JSONDecodeError as exc: raise ToolContractError("arguments are not JSON") from exc
    errors=_validate_schema(args,tool["arguments_schema"])
    if errors: raise ToolContractError("; ".join(errors))
    return {"id":value["id"],"type":"function","function":{"name":tool["name"],"arguments":canonical_json(args)}}


def controller_execute(call: dict[str, Any], registry: dict[str, Any], available: set[str], handlers: dict[str,Callable[[dict[str,Any]],Any]], runtime_target: str, *, approved: bool=False) -> list[dict[str, Any]]:
    execution_id=str(uuid.uuid4()); now=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    base={"execution_id":execution_id,"runtime_target":runtime_target,"capability_registry_fingerprint":registry["fingerprint"]}
    events=[{**base,"state":"TOOL_CALL_REQUESTED","timestamp":now(),"call":call,"authoritative":False}]
    try: parsed=parse_tool_call(call,registry,available)
    except ToolContractError as exc:
        return events+[{**base,"state":"TOOL_EXECUTION_DENIED","timestamp":now(),"error":{"code":"INVALID_TOOL_CALL","message":str(exc)},"authoritative":True}]
    tool=next(t for t in registry["tools"] if t["name"]==parsed["function"]["name"]); args=json.loads(parsed["function"]["arguments"])
    events.append({**base,"state":"TOOL_CALL_VALIDATED","timestamp":now(),"tool_name":tool["name"],"arguments":args,"authoritative":True})
    if tool["approval_required"] and not approved: return events+[{**base,"state":"TOOL_EXECUTION_DENIED","timestamp":now(),"tool_name":tool["name"],"error":{"code":"APPROVAL_REQUIRED","message":"approval required"},"authoritative":True}]
    if tool["name"] not in handlers: return events+[{**base,"state":"TOOL_ERROR","timestamp":now(),"tool_name":tool["name"],"error":{"code":"NO_HANDLER","message":"runtime handler unavailable"},"authoritative":True}]
    events.append({**base,"state":"TOOL_EXECUTION_STARTED","timestamp":now(),"tool_name":tool["name"],"arguments":args,"authoritative":True})
    try:
        result=handlers[tool["name"]](args); errors=_validate_schema(result,tool["result_schema"])
        if errors: raise ToolContractError("; ".join(errors))
        events.append({**base,"state":"TOOL_RESULT","timestamp":now(),"tool_name":tool["name"],"arguments":args,"result":result,"authoritative":True})
    except Exception as exc: events.append({**base,"state":"TOOL_ERROR","timestamp":now(),"tool_name":tool["name"],"error":{"code":type(exc).__name__,"message":str(exc)},"authoritative":True})
    return events


def authoritative_result(trace: list[dict[str, Any]], execution_id: str) -> dict[str, Any] | None:
    return next((e for e in trace if e.get("execution_id")==execution_id and e.get("state")=="TOOL_RESULT" and e.get("authoritative") is True),None)


def repetition_diagnostic(text: str, *, max_token_ratio: float=.55, min_phrase_tokens: int=3, phrase_repeats: int=3, max_tokens: int|None=None) -> dict[str, Any]:
    tokens=text.split(); reasons=[]
    for width in range(min_phrase_tokens,min(12,len(tokens)//phrase_repeats)+1):
        grams=Counter(tuple(tokens[i:i+width]) for i in range(len(tokens)-width+1))
        if grams and max(grams.values())>=phrase_repeats: reasons.append("repeated_phrase_loop"); break
    sentences=[x.strip() for x in re.split(r"[.!؟\n]+",text) if x.strip()]
    if sentences and max(Counter(sentences).values())>=3: reasons.append("repeated_sentence_loop")
    if tokens and max(Counter(tokens).values())/len(tokens)>=max_token_ratio and len(tokens)>=12: reasons.append("abnormal_token_repetition")
    if max_tokens and len(tokens)>=max_tokens and reasons: reasons.append("max_tokens_duplication")
    return {"flagged":bool(reasons),"reasons":sorted(set(reasons)),"tokens":len(tokens),"thresholds":{"max_token_ratio":max_token_ratio,"min_phrase_tokens":min_phrase_tokens,"phrase_repeats":phrase_repeats}}


def tool_benchmark_verdict(expected: dict[str, Any], trace: list[dict[str, Any]], final_response: str) -> dict[str, Any]:
    results=[x for x in trace if x.get("state")=="TOOL_RESULT" and x.get("authoritative") is True]
    requested=any(x.get("state")=="TOOL_CALL_REQUESTED" for x in trace)
    result=next((x for x in results if x.get("tool_name")==expected.get("tool_name")),None)
    failures=[]
    if not requested: failures.append("AVAILABLE_TOOL_NOT_REQUESTED")
    if result is None: failures.append("NO_AUTHORITATIVE_RESULT")
    if any(x.get("state")=="TOOL_RESULT" and x.get("authoritative") is not True for x in trace): failures.append("FABRICATED_RESULT_EVENT")
    if result and expected.get("expected_result") is not None and result.get("result")!=expected["expected_result"]: failures.append("WRONG_RESULT")
    if result and expected.get("final_exact") and final_response!=expected["final_exact"]: failures.append("FINAL_CONSTRAINT_VIOLATION")
    if not final_response.strip() or re.fullmatch(r"\{[^{}]+\}",final_response.strip()): failures.append("EMPTY_OR_PLACEHOLDER_FINAL")
    return {"verdict":"PASS" if not failures else "FAIL","failures":failures,"expected_tool_behavior":expected,"observed_execution_trace":trace,"final_response":final_response}
