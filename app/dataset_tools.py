from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "tool-capabilities.v1.json"
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
