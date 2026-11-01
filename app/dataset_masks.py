"""Pure tokenizer-based checks of exported dataset supervision boundaries.

These helpers accept an already constructed tokenizer and never load a model,
start a runtime, or construct training batches. Persisted mask keys retain the
export schema used by external dataset consumers.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

IGNORE_INDEX = -100


class DatasetMaskError(ValueError):
    """An exported record cannot be masked without supervising context."""


def _token_ids(value: Any) -> list[int]:
    if isinstance(value, Mapping):
        value = value.get("input_ids")
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or any(not isinstance(token, int) for token in value):
        raise DatasetMaskError("tokenizer chat template did not return a flat input_ids list")
    return value


def _apply_chat_template(tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool) -> list[int]:
    if not hasattr(tokenizer, "apply_chat_template"):
        raise DatasetMaskError("tokenizer must provide apply_chat_template")
    encoded = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=add_generation_prompt,
        return_tensors=None,
    )
    return _token_ids(encoded)


def _render_chat_template(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    if not hasattr(tokenizer, "apply_chat_template"):
        raise DatasetMaskError("tokenizer must provide apply_chat_template")
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    if not isinstance(rendered, str):
        raise DatasetMaskError("tokenizer chat template did not return rendered text")
    return rendered


def _flat_int_list(value: Any, name: str) -> list[int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or any(not isinstance(item, int) for item in value):
        raise DatasetMaskError(f"tokenizer did not return a flat {name} list")
    return value


def _target_character_span(
    tokenizer: Any, messages: list[dict[str, str]], target_index: int
) -> tuple[str, int, int]:
    target_text = messages[target_index].get("content")
    if not isinstance(target_text, str) or not target_text:
        raise DatasetMaskError("the final assistant target must contain non-empty text")

    marker_seed = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
    marker = f"NAJDILAB_TARGET_{hashlib.sha256(marker_seed).hexdigest()}"
    while any(marker in str(message.get("content", "")) for message in messages):
        marker += "_X"

    marked_messages = copy.deepcopy(messages)
    marked_messages[target_index]["content"] = marker
    marked_rendered = _render_chat_template(tokenizer, marked_messages)
    if marked_rendered.count(marker) != 1:
        raise DatasetMaskError("chat template did not preserve the target marker exactly once")
    prefix, suffix = marked_rendered.split(marker, 1)

    rendered = _render_chat_template(tokenizer, messages)
    expected_rendered = prefix + target_text + suffix
    if rendered != expected_rendered:
        raise DatasetMaskError("chat template changed outside the final assistant content")
    return rendered, len(prefix), len(prefix) + len(target_text)


def _tokenize_text(tokenizer: Any, text: str, *, offsets: bool = False) -> tuple[list[int], list[tuple[int, int]] | None]:
    kwargs = {
        "add_special_tokens": False,
        "return_attention_mask": False,
    }
    if offsets:
        kwargs["return_offsets_mapping"] = True
    encoded = tokenizer(text, **kwargs)
    if not isinstance(encoded, Mapping):
        raise DatasetMaskError("tokenizer text encoding did not return a mapping")
    input_ids = _token_ids(encoded)
    if not offsets or "offset_mapping" not in encoded:
        return input_ids, None
    raw_offsets = encoded["offset_mapping"]
    if hasattr(raw_offsets, "tolist"):
        raw_offsets = raw_offsets.tolist()
    if isinstance(raw_offsets, list) and raw_offsets and isinstance(raw_offsets[0], list) \
            and raw_offsets[0] and isinstance(raw_offsets[0][0], list):
        raw_offsets = raw_offsets[0]
    if not isinstance(raw_offsets, list) or len(raw_offsets) != len(input_ids):
        raise DatasetMaskError("offset_mapping length does not match input_ids")
    offsets: list[tuple[int, int]] = []
    for offset in raw_offsets:
        if not isinstance(offset, (list, tuple)) or len(offset) != 2:
            raise DatasetMaskError("tokenizer returned an invalid offset_mapping entry")
        offsets.append((int(offset[0]), int(offset[1])))
    return input_ids, offsets


def _official_assistant_mask(tokenizer: Any, messages: list[dict[str, str]]) -> tuple[list[int], list[int]] | None:
    template = getattr(tokenizer, "chat_template", None)
    if not isinstance(template, str) or "{% generation" not in template:
        return None
    encoded = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,
        return_tensors=None,
        return_dict=True,
        return_assistant_tokens_mask=True,
    )
    if not isinstance(encoded, Mapping):
        raise DatasetMaskError("official assistant mask did not return a mapping")
    mask_key = next(
        (key for key in ("assistant_masks", "assistant_tokens_mask") if key in encoded),
        None,
    )
    if mask_key is None:
        raise DatasetMaskError("chat template declares generation blocks but returned no assistant mask")
    return _token_ids(encoded), _flat_int_list(encoded[mask_key], mask_key)


def _decode_exact(tokenizer: Any, token_ids: list[int]) -> str:
    return tokenizer.decode(
        token_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )


def _exact_target_token_positions(
    tokenizer: Any,
    messages: list[dict[str, str]],
    target_index: int,
) -> tuple[list[int], list[int], str]:
    rendered, target_start, target_end = _target_character_span(tokenizer, messages, target_index)
    input_ids, offsets = _tokenize_text(tokenizer, rendered, offsets=True)
    template_ids = _apply_chat_template(tokenizer, messages, add_generation_prompt=False)
    if input_ids != template_ids:
        raise DatasetMaskError("rendered-text tokenization differs from apply_chat_template tokenization")

    if offsets is not None:
        target_positions: list[int] = []
        for index, (start, end) in enumerate(offsets):
            if end <= start:
                continue
            if start < target_start < end or start < target_end < end:
                raise DatasetMaskError("a token crosses the assistant content boundary")
            if start >= target_start and end <= target_end:
                target_positions.append(index)
        strategy = "rendered_template_offsets"
    else:
        prefix_ids, _ = _tokenize_text(tokenizer, rendered[:target_start])
        target_ids, _ = _tokenize_text(tokenizer, rendered[target_start:target_end])
        suffix_ids, _ = _tokenize_text(tokenizer, rendered[target_end:])
        if prefix_ids + target_ids + suffix_ids != input_ids:
            raise DatasetMaskError(
                "tokenizer has no offsets and the exact rendered target is not token-boundary stable"
            )
        target_positions = list(range(len(prefix_ids), len(prefix_ids) + len(target_ids)))
        strategy = "rendered_template_exact_segments"
    if not target_positions:
        raise DatasetMaskError("assistant target produced no trainable tokens")

    official = _official_assistant_mask(tokenizer, messages)
    if official is not None:
        official_ids, official_mask = official
        if official_ids != input_ids or len(official_mask) != len(input_ids):
            raise DatasetMaskError("official assistant mask is not aligned with template tokens")
        if any(official_mask[index] != 1 for index in target_positions):
            raise DatasetMaskError("official assistant mask omitted part of the final Gold response")
        target_positions = [index for index in target_positions if official_mask[index] == 1]
        strategy = "official_generation_mask+rendered_template_offsets"

    expected = messages[target_index]["content"]
    decoded = _decode_exact(tokenizer, [input_ids[index] for index in target_positions])
    if decoded != expected:
        raise DatasetMaskError(
            f"decoded trainable content does not exactly match target: {decoded!r} != {expected!r}"
        )
    return input_ids, target_positions, strategy


def encode_masked_sft_record(
    record: dict[str, Any], tokenizer: Any, max_length: int | None = None
) -> dict[str, Any]:
    messages = record.get("messages")
    message_mask = record.get("message_loss_mask")
    target_index = record.get("target_message_index")
    if not isinstance(messages, list) or not messages:
        raise DatasetMaskError("SFT record must contain messages")
    if record.get("train_on_last_assistant_only") is not True:
        raise DatasetMaskError("train_on_last_assistant_only must be true")
    if (
        not isinstance(message_mask, list)
        or len(message_mask) != len(messages)
        or any(value not in {0, 1} for value in message_mask)
        or sum(value == 1 for value in message_mask) != 1
    ):
        raise DatasetMaskError("message_loss_mask must select exactly one message")
    masked_target_index = message_mask.index(1)
    if target_index != masked_target_index or target_index != len(messages) - 1:
        raise DatasetMaskError("target_message_index must identify the final masked message")
    target = messages[target_index]
    if not isinstance(target, dict) or target.get("role") != "assistant":
        raise DatasetMaskError("the trainable target must be the final assistant message")

    input_ids, target_positions, mask_strategy = _exact_target_token_positions(
        tokenizer, messages, target_index
    )
    labels = [IGNORE_INDEX] * len(input_ids)
    for index in target_positions:
        labels[index] = input_ids[index]
    if max_length is not None and len(input_ids) > max_length:
        input_ids = input_ids[-max_length:]
        labels = labels[-max_length:]
    if not any(label != IGNORE_INDEX for label in labels):
        raise DatasetMaskError("target response was fully truncated")
    trainable_ids = [token for token, label in zip(input_ids, labels) if label != IGNORE_INDEX]
    if _decode_exact(tokenizer, trainable_ids) != target["content"]:
        raise DatasetMaskError("truncation removed part of the final Gold response")
    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": labels,
        "record_id": record.get("id"),
        "target_token_start": labels.index(next(label for label in labels if label != IGNORE_INDEX)),
        "target_token_end": max(index for index, label in enumerate(labels) if label != IGNORE_INDEX) + 1,
        "mask_strategy": mask_strategy,
    }


def load_masked_sft_records(
    export_dir: Path | str, tokenizer: Any, max_length: int | None = None
) -> list[dict[str, Any]]:
    export_dir = Path(export_dir)
    encoded = []
    for filename in ("sft.jsonl", "multi_turn.jsonl"):
        path = export_dir / filename
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    encoded.append(encode_masked_sft_record(record, tokenizer, max_length))
                except (json.JSONDecodeError, DatasetMaskError) as exc:
                    raise DatasetMaskError(f"{filename}:{line_number}: {exc}") from exc
    return encoded


def encode_masked_native_tool_record(
    record: dict[str, Any], tokenizer: Any, registry: dict[str, Any], max_length: int | None = None
) -> dict[str, Any]:
    """Render native Ministral tool structures; supervise calls/final prose, never tool results."""
    from .native_tool_data import validate_native_tool_record
    from .dataset_tools import canonical_json, visible_tools

    validation = validate_native_tool_record(record, registry)
    messages = copy.deepcopy(record["messages"])
    gemma_native = "<|tool_call>" in str(getattr(tokenizer, "chat_template", ""))
    for message in messages:
        for call in message.get("tool_calls") or []:
            arguments = call["function"]["arguments"]
            if gemma_native and isinstance(arguments, str): arguments = json.loads(arguments)
            elif not gemma_native and not isinstance(arguments, str): arguments = canonical_json(arguments)
            call["function"]["arguments"] = arguments
    tools = visible_tools(registry, set(record["available_tools"]))
    rendered = tokenizer.apply_chat_template(messages, tools=tools, tokenize=False, add_generation_prompt=False)
    encoded = tokenizer.apply_chat_template(messages, tools=tools, tokenize=True, add_generation_prompt=False, return_tensors=None)
    input_ids = _token_ids(encoded)
    text_ids, offsets = _tokenize_text(tokenizer, rendered, offsets=True)
    if text_ids != input_ids or offsets is None: raise DatasetMaskError("native tool masking requires exact offset mapping")
    spans=[]; cursor=0
    for segment in validation["supervised_segments"]:
        message=messages[segment["message_index"]]
        if segment["kind"]=="tool_call":
            call=next(x for x in message["tool_calls"] if x["id"]==segment["call_id"])
            if gemma_native:
                needle="<|tool_call>call:"+call["function"]["name"]
                start=rendered.find(needle,cursor); close=rendered.find("<tool_call|>",start)
                if start>=0 and close>=0: needle=rendered[start:close+len("<tool_call|>")]
            else:
                needle="[TOOL_CALLS]"+call["function"]["name"]+"[ARGS]"+call["function"]["arguments"]
                start=rendered.find(needle,cursor)
        else:
            needle=message["content"]; start=rendered.rfind(needle)
        if start<0: raise DatasetMaskError(f"chat template did not preserve supervised {segment['kind']}")
        spans.append((start,start+len(needle),segment["kind"])); cursor=start+len(needle)
    labels=[IGNORE_INDEX]*len(input_ids); supervised_kinds=[]
    for start,end,kind in spans:
        positions=[]
        for index,(left,right) in enumerate(offsets):
            if right<=left: continue
            if left<start<right or left<end<right: raise DatasetMaskError("token crosses native tool supervision boundary")
            if left>=start and right<=end: positions.append(index)
        if not positions: raise DatasetMaskError(f"{kind} produced no supervised tokens")
        for index in positions: labels[index]=input_ids[index]
        supervised_kinds.append(kind)
    if max_length is not None and len(input_ids)>max_length:
        input_ids=input_ids[-max_length:]; labels=labels[-max_length:]
    if not any(x!=IGNORE_INDEX for x in labels): raise DatasetMaskError("native tool targets were fully truncated")
    return {"input_ids":input_ids,"attention_mask":[1]*len(input_ids),"labels":labels,"record_id":record.get("id"),"mask_strategy":"native_tool_template_offsets","supervised_segments":supervised_kinds,"tool_results_masked":True}


def load_masked_dataset_records(export_dir: Path | str, tokenizer: Any, max_length: int | None = None, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    encoded=load_masked_sft_records(export_dir,tokenizer,max_length); path=Path(export_dir)/"native_tool_use.jsonl"
    if path.is_file():
        if registry is None: raise DatasetMaskError("native tool records require a capability registry")
        for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: encoded.append(encode_masked_native_tool_record(json.loads(line),tokenizer,registry,max_length))
            except (json.JSONDecodeError,ValueError) as exc: raise DatasetMaskError(f"native_tool_use.jsonl:{number}: {exc}") from exc
    return encoded
