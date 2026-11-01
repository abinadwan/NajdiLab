from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.native_tool_data import NativeToolDataError, validate_native_tool_record
from app.dataset_tools import (ToolContractError, canonical_conversation,
    load_registry, parse_tool_call, visible_tools)
from app.dataset_validation import validate_native_dataset
from app.dataset_masks import IGNORE_INDEX, encode_masked_native_tool_record



class CharTokenizer:
    chat_template="[AVAILABLE_TOOLS][TOOL_CALLS][ARGS][TOOL_RESULTS]"
    def apply_chat_template(self,messages,tools=None,tokenize=False,add_generation_prompt=False,return_tensors=None,**kwargs):
        out="[AVAILABLE_TOOLS]"+json.dumps(tools or [],ensure_ascii=False,sort_keys=True,separators=(",",":"))+"[/AVAILABLE_TOOLS]"
        for m in messages:
            if m["role"]=="system": out += "[SYSTEM_PROMPT]"+m["content"]+"[/SYSTEM_PROMPT]"
            elif m["role"]=="user": out += "[INST]"+m["content"]+"[/INST]"
            elif m["role"]=="assistant":
                out += m.get("content") or ""
                for call in m.get("tool_calls") or []: out += "[TOOL_CALLS]"+call["function"]["name"]+"[ARGS]"+call["function"]["arguments"]
                out += "<eos>"
            elif m["role"]=="tool": out += "[TOOL_RESULTS]"+m["content"]+"[/TOOL_RESULTS]"
        return [ord(x) for x in out] if tokenize else out
    def __call__(self,text,**kwargs): return {"input_ids":[ord(x) for x in text],"offset_mapping":[(i,i+1) for i in range(len(text))]}
    def decode(self,ids,**kwargs): return "".join(chr(x) for x in ids)


class GemmaCharTokenizer(CharTokenizer):
    chat_template="<|tool_call>"
    def apply_chat_template(self,messages,tools=None,tokenize=False,add_generation_prompt=False,return_tensors=None,**kwargs):
        assert all(tool.get("type")=="function" and "function" in tool for tool in tools or [])
        out="<bos>"
        for m in messages:
            if m["role"]=="assistant":
                for call in m.get("tool_calls") or []:
                    assert isinstance(call["function"]["arguments"],dict)
                    out += "<|tool_call>call:"+call["function"]["name"]+json.dumps(call["function"]["arguments"],sort_keys=True)+"<tool_call|>"
                out += m.get("content") or ""
            elif m["role"]=="tool": out += "<|tool_response>"+m["content"]+"<tool_response|>"
            else: out += m.get("content") or ""
        return [ord(x) for x in out] if tokenize else out


def record(registry):
    return {"schema_version":1,"record_type":"native_tool_use","id":"dev-1","capability_registry":{"version":registry["registry_version"],"fingerprint":registry["fingerprint"]},"available_tools":["system.whoami"],"messages":[
        {"role":"system","content":"Use only declared tools."},{"role":"user","content":"Development fixture."},
        {"role":"assistant","content":"","tool_calls":[{"id":"call-1","type":"function","function":{"name":"system.whoami","arguments":"{}"}}]},
        {"role":"tool","tool_call_id":"call-1","name":"system.whoami","authoritative":True,"content":"{\"identity\":\"dev-user\"}"},
        {"role":"assistant","content":"dev-user"}]}


class Phase37Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry=load_registry()
    def test_available_exposed_unavailable_hidden_and_canonical(self):
        self.assertEqual(len(visible_tools(self.registry,{"system.whoami"})),1); self.assertEqual(visible_tools(self.registry,set()),[])
        value=canonical_conversation(record(self.registry)["messages"],self.registry,{"system.whoami"}); self.assertEqual(value["serialization"],"ministral-native-v1")
    def test_valid_call_and_schema_rejections(self):
        call=record(self.registry)["messages"][2]["tool_calls"][0]; self.assertEqual(parse_tool_call(call,self.registry,{"system.whoami"})["function"]["arguments"],"{}")
        bad=copy.deepcopy(call); bad["function"]["arguments"]="{bad"
        with self.assertRaises(ToolContractError): parse_tool_call(bad,self.registry,{"system.whoami"})
        bad=copy.deepcopy(call); bad["function"]["arguments"]="{\"extra\":1}"
        with self.assertRaises(ToolContractError): parse_tool_call(bad,self.registry,{"system.whoami"})
    def test_native_record_order_and_authority(self):
        self.assertTrue(validate_native_tool_record(record(self.registry),self.registry)["valid"])
        bad=record(self.registry); bad["messages"][3]["tool_call_id"]="orphan"
        with self.assertRaises(NativeToolDataError): validate_native_tool_record(bad,self.registry)
        bad=record(self.registry); bad["messages"][3]["authoritative"]=False
        with self.assertRaises(NativeToolDataError): validate_native_tool_record(bad,self.registry)
        denied=record(self.registry); denied["messages"][3].update({"outcome":"denied","content":"{\"code\":\"APPROVAL_REQUIRED\",\"message\":\"approval required\"}"})
        self.assertTrue(validate_native_tool_record(denied,self.registry)["valid"])
    def test_native_loss_masks_calls_and_final_but_not_results(self):
        encoded=encode_masked_native_tool_record(record(self.registry),CharTokenizer(),self.registry)
        supervised="".join(chr(t) for t,l in zip(encoded["input_ids"],encoded["labels"]) if l!=IGNORE_INDEX)
        self.assertIn("[TOOL_CALLS]system.whoami[ARGS]{}",supervised); self.assertIn("dev-user",supervised)
        rendered="".join(chr(t) for t in encoded["input_ids"]); result_start=rendered.index("[TOOL_RESULTS]"); result_end=rendered.index("[/TOOL_RESULTS]")+len("[/TOOL_RESULTS]")
        self.assertTrue(all(x==IGNORE_INDEX for x in encoded["labels"][result_start:result_end])); self.assertTrue(encoded["tool_results_masked"])
    def test_gemma_native_template_uses_object_arguments_and_masks_results(self):
        encoded=encode_masked_native_tool_record(record(self.registry),GemmaCharTokenizer(),self.registry)
        supervised="".join(chr(t) for t,l in zip(encoded["input_ids"],encoded["labels"]) if l!=IGNORE_INDEX)
        self.assertIn("<|tool_call>call:system.whoami{}<tool_call|>",supervised); self.assertIn("dev-user",supervised)
        rendered="".join(chr(t) for t in encoded["input_ids"]); start=rendered.index("<|tool_response>"); end=rendered.index("<tool_response|>")+len("<tool_response|>")
        self.assertTrue(all(x==IGNORE_INDEX for x in encoded["labels"][start:end]))
    def test_validation_blocks_missing_native_masks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"capability-registry.json").write_text(json.dumps({k:v for k,v in self.registry.items() if k!="fingerprint"}),encoding="utf-8")
            (root/"native_tool_use.jsonl").write_text(json.dumps(record(self.registry))+"\n",encoding="utf-8")
            result=validate_native_dataset(root); self.assertEqual(result["count"],1); self.assertEqual(result["status"],"BLOCKED"); self.assertEqual(result["valid_loss_masks"],0)



if __name__=="__main__": unittest.main()
