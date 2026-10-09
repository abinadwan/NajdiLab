from __future__ import annotations

import json
from typing import Any

try:
    from .tool_runtime import ToolContractError, _validate_schema, canonical_json, parse_tool_call
except ImportError:  # deployed beside the standalone training adapter
    from tool_runtime import ToolContractError, _validate_schema, canonical_json, parse_tool_call


class NativeToolDataError(ValueError): pass


def validate_native_tool_record(record: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if record.get("record_type")!="native_tool_use" or record.get("schema_version")!=1: raise NativeToolDataError("unsupported native tool record")
    binding=record.get("capability_registry") or {}
    if binding.get("version")!=registry["registry_version"] or binding.get("fingerprint")!=registry["fingerprint"]: raise NativeToolDataError("capability registry mismatch")
    declared=record.get("available_tools")
    if not isinstance(declared,list) or len(declared)!=len(set(declared)): raise NativeToolDataError("available_tools must be unique")
    known={t["name"] for t in registry["tools"]}
    if not set(declared)<=known: raise NativeToolDataError("referenced tool does not exist")
    messages=record.get("messages")
    minimum=2 if record.get("expected_behavior") in {"unavailable_tool","no_tool_required"} else 4
    if not isinstance(messages,list) or len(messages)<minimum: raise NativeToolDataError("native tool conversation is incomplete")
    state="start"; pending={}; supervised=[]; results=set()
    for index,msg in enumerate(messages):
        role=msg.get("role") if isinstance(msg,dict) else None
        if role=="system" and state=="start": state="system"
        elif role=="user" and state in {"start","system","final"}: state="user"
        elif role=="assistant" and msg.get("tool_calls") and state in {"user","tool"}:
            for call in msg["tool_calls"]:
                try: parsed=parse_tool_call(call,registry,set(declared))
                except ToolContractError as exc: raise NativeToolDataError(str(exc)) from exc
                if parsed["id"] in pending or parsed["id"] in results: raise NativeToolDataError("duplicate tool call id")
                pending[parsed["id"]]=parsed; supervised.append({"message_index":index,"kind":"tool_call","call_id":parsed["id"]})
            state="call"
        elif role=="tool" and state=="call":
            call_id=msg.get("tool_call_id"); call=pending.pop(call_id,None)
            if call is None or msg.get("name")!=call["function"]["name"]: raise NativeToolDataError("orphan or mismatched tool result")
            if msg.get("authoritative") is not True: raise NativeToolDataError("tool result is not authoritative")
            try: content=json.loads(msg.get("content")) if isinstance(msg.get("content"),str) else msg.get("content")
            except json.JSONDecodeError as exc: raise NativeToolDataError("tool result is not JSON") from exc
            tool=next(t for t in registry["tools"] if t["name"]==msg["name"]); outcome=msg.get("outcome","result")
            if outcome not in {"result","error","denied"}: raise NativeToolDataError("invalid tool outcome")
            schema=tool["result_schema"] if outcome=="result" else tool["error_schema"]; errors=_validate_schema(content,schema)
            if errors: raise NativeToolDataError(f"invalid tool {outcome}: "+"; ".join(errors))
            msg["content"]=canonical_json(content); results.add(call_id); state="tool"
        elif role=="assistant" and isinstance(msg.get("content"),str) and msg["content"] and (state=="tool" or (state=="user" and record.get("expected_behavior") in {"unavailable_tool","no_tool_required"})):
            supervised.append({"message_index":index,"kind":"final_response"}); state="final"
        else: raise NativeToolDataError(f"invalid ordering at message {index}")
    if pending or state!="final": raise NativeToolDataError("missing matching tool result or final response")
    return {"valid":True,"tool_calls":sum(x["kind"]=="tool_call" for x in supervised),"tool_results":len(results),"supervised_segments":supervised}
