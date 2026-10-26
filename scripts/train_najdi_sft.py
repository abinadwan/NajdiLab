from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


IGNORE_INDEX = -100


class TrainingDataError(ValueError):
    pass


def _token_ids(value: Any) -> list[int]:
    if isinstance(value, Mapping):
        value = value.get("input_ids")
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or any(not isinstance(token, int) for token in value):
        raise TrainingDataError("tokenizer chat template did not return a flat input_ids list")
    return value


def _apply_chat_template(tokenizer: Any, messages: list[dict[str, str]], add_generation_prompt: bool) -> list[int]:
    if not hasattr(tokenizer, "apply_chat_template"):
        raise TrainingDataError("tokenizer must provide apply_chat_template")
    encoded = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=add_generation_prompt,
        return_tensors=None,
    )
    return _token_ids(encoded)


def _render_chat_template(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    if not hasattr(tokenizer, "apply_chat_template"):
        raise TrainingDataError("tokenizer must provide apply_chat_template")
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    if not isinstance(rendered, str):
        raise TrainingDataError("tokenizer chat template did not return rendered text")
    return rendered


def _flat_int_list(value: Any, name: str) -> list[int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or any(not isinstance(item, int) for item in value):
        raise TrainingDataError(f"tokenizer did not return a flat {name} list")
    return value


def _target_character_span(
    tokenizer: Any, messages: list[dict[str, str]], target_index: int
) -> tuple[str, int, int]:
    target_text = messages[target_index].get("content")
    if not isinstance(target_text, str) or not target_text:
        raise TrainingDataError("the final assistant target must contain non-empty text")

    marker_seed = json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
    marker = f"NAJDILAB_TARGET_{hashlib.sha256(marker_seed).hexdigest()}"
    while any(marker in str(message.get("content", "")) for message in messages):
        marker += "_X"

    marked_messages = copy.deepcopy(messages)
    marked_messages[target_index]["content"] = marker
    marked_rendered = _render_chat_template(tokenizer, marked_messages)
    if marked_rendered.count(marker) != 1:
        raise TrainingDataError("chat template did not preserve the target marker exactly once")
    prefix, suffix = marked_rendered.split(marker, 1)

    rendered = _render_chat_template(tokenizer, messages)
    expected_rendered = prefix + target_text + suffix
    if rendered != expected_rendered:
        raise TrainingDataError("chat template changed outside the final assistant content")
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
        raise TrainingDataError("tokenizer text encoding did not return a mapping")
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
        raise TrainingDataError("offset_mapping length does not match input_ids")
    offsets: list[tuple[int, int]] = []
    for offset in raw_offsets:
        if not isinstance(offset, (list, tuple)) or len(offset) != 2:
            raise TrainingDataError("tokenizer returned an invalid offset_mapping entry")
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
        raise TrainingDataError("official assistant mask did not return a mapping")
    mask_key = next(
        (key for key in ("assistant_masks", "assistant_tokens_mask") if key in encoded),
        None,
    )
    if mask_key is None:
        raise TrainingDataError("chat template declares generation blocks but returned no assistant mask")
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
        raise TrainingDataError("rendered-text tokenization differs from apply_chat_template tokenization")

    if offsets is not None:
        target_positions: list[int] = []
        for index, (start, end) in enumerate(offsets):
            if end <= start:
                continue
            if start < target_start < end or start < target_end < end:
                raise TrainingDataError("a token crosses the assistant content boundary")
            if start >= target_start and end <= target_end:
                target_positions.append(index)
        strategy = "rendered_template_offsets"
    else:
        prefix_ids, _ = _tokenize_text(tokenizer, rendered[:target_start])
        target_ids, _ = _tokenize_text(tokenizer, rendered[target_start:target_end])
        suffix_ids, _ = _tokenize_text(tokenizer, rendered[target_end:])
        if prefix_ids + target_ids + suffix_ids != input_ids:
            raise TrainingDataError(
                "tokenizer has no offsets and the exact rendered target is not token-boundary stable"
            )
        target_positions = list(range(len(prefix_ids), len(prefix_ids) + len(target_ids)))
        strategy = "rendered_template_exact_segments"
    if not target_positions:
        raise TrainingDataError("assistant target produced no trainable tokens")

    official = _official_assistant_mask(tokenizer, messages)
    if official is not None:
        official_ids, official_mask = official
        if official_ids != input_ids or len(official_mask) != len(input_ids):
            raise TrainingDataError("official assistant mask is not aligned with template tokens")
        if any(official_mask[index] != 1 for index in target_positions):
            raise TrainingDataError("official assistant mask omitted part of the final Gold response")
        target_positions = [index for index in target_positions if official_mask[index] == 1]
        strategy = "official_generation_mask+rendered_template_offsets"

    expected = messages[target_index]["content"]
    decoded = _decode_exact(tokenizer, [input_ids[index] for index in target_positions])
    if decoded != expected:
        raise TrainingDataError(
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
        raise TrainingDataError("SFT record must contain messages")
    if record.get("train_on_last_assistant_only") is not True:
        raise TrainingDataError("train_on_last_assistant_only must be true")
    if (
        not isinstance(message_mask, list)
        or len(message_mask) != len(messages)
        or any(value not in {0, 1} for value in message_mask)
        or sum(value == 1 for value in message_mask) != 1
    ):
        raise TrainingDataError("message_loss_mask must select exactly one message")
    masked_target_index = message_mask.index(1)
    if target_index != masked_target_index or target_index != len(messages) - 1:
        raise TrainingDataError("target_message_index must identify the final masked message")
    target = messages[target_index]
    if not isinstance(target, dict) or target.get("role") != "assistant":
        raise TrainingDataError("the trainable target must be the final assistant message")

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
        raise TrainingDataError("target response was fully truncated")
    trainable_ids = [token for token, label in zip(input_ids, labels) if label != IGNORE_INDEX]
    if _decode_exact(tokenizer, trainable_ids) != target["content"]:
        raise TrainingDataError("truncation removed part of the final Gold response")
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
                except (json.JSONDecodeError, TrainingDataError) as exc:
                    raise TrainingDataError(f"{filename}:{line_number}: {exc}") from exc
    return encoded


def encode_masked_native_tool_record(
    record: dict[str, Any], tokenizer: Any, registry: dict[str, Any], max_length: int | None = None
) -> dict[str, Any]:
    """Render native Ministral tool structures; supervise calls/final prose, never tool results."""
    try:
        from app.native_tool_data import validate_native_tool_record
        from app.tool_runtime import canonical_json, visible_tools
    except ImportError:
        from native_tool_data import validate_native_tool_record
        from tool_runtime import canonical_json, visible_tools

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
    if text_ids != input_ids or offsets is None: raise TrainingDataError("native tool masking requires exact offset mapping")
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
        if start<0: raise TrainingDataError(f"chat template did not preserve supervised {segment['kind']}")
        spans.append((start,start+len(needle),segment["kind"])); cursor=start+len(needle)
    labels=[IGNORE_INDEX]*len(input_ids); supervised_kinds=[]
    for start,end,kind in spans:
        positions=[]
        for index,(left,right) in enumerate(offsets):
            if right<=left: continue
            if left<start<right or left<end<right: raise TrainingDataError("token crosses native tool supervision boundary")
            if left>=start and right<=end: positions.append(index)
        if not positions: raise TrainingDataError(f"{kind} produced no supervised tokens")
        for index in positions: labels[index]=input_ids[index]
        supervised_kinds.append(kind)
    if max_length is not None and len(input_ids)>max_length:
        input_ids=input_ids[-max_length:]; labels=labels[-max_length:]
    if not any(x!=IGNORE_INDEX for x in labels): raise TrainingDataError("native tool targets were fully truncated")
    return {"input_ids":input_ids,"attention_mask":[1]*len(input_ids),"labels":labels,"record_id":record.get("id"),"mask_strategy":"native_tool_template_offsets","supervised_segments":supervised_kinds,"tool_results_masked":True}


def load_masked_training_records(export_dir: Path | str, tokenizer: Any, max_length: int | None = None, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    encoded=load_masked_sft_records(export_dir,tokenizer,max_length); path=Path(export_dir)/"native_tool_use.jsonl"
    if path.is_file():
        if registry is None: raise TrainingDataError("native tool records require a capability registry")
        for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: encoded.append(encode_masked_native_tool_record(json.loads(line),tokenizer,registry,max_length))
            except (json.JSONDecodeError,ValueError) as exc: raise TrainingDataError(f"native_tool_use.jsonl:{number}: {exc}") from exc
    return encoded


class MaskedSFTDataCollator:
    def __init__(self, tokenizer: Any):
        self.tokenizer = tokenizer

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("PyTorch is required to collate training batches") from exc
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            raise TrainingDataError("tokenizer must define pad_token_id")
        max_length = max(len(feature["input_ids"]) for feature in features)
        input_ids = []
        attention_masks = []
        labels = []
        for feature in features:
            padding = max_length - len(feature["input_ids"])
            input_ids.append(feature["input_ids"] + [pad_token_id] * padding)
            attention_masks.append(feature["attention_mask"] + [0] * padding)
            labels.append(feature["labels"] + [IGNORE_INDEX] * padding)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_masks, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def run_training(args: argparse.Namespace) -> None:
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        raise SystemExit("Install the training dependencies (transformers and torch) before using --train") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    records = load_masked_sft_records(args.export_dir, tokenizer, args.max_length)
    if not args.train:
        trainable_tokens = sum(sum(label != IGNORE_INDEX for label in record["labels"]) for record in records)
        print(json.dumps({"records": len(records), "trainable_tokens": trainable_tokens}, indent=2))
        return

    model = AutoModelForCausalLM.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)

    class RecordDataset:
        def __len__(self) -> int:
            return len(records)

        def __getitem__(self, index: int) -> dict[str, Any]:
            return records[index]

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        logging_steps=1,
        save_strategy="epoch",
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=RecordDataset(),
        data_collator=MaskedSFTDataCollator(tokenizer),
    )
    trainer.train()


def main() -> None:
    parser = argparse.ArgumentParser(description="NajdiLab completion-only SFT trainer")
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("training-output"))
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--train", action="store_true", help="Actually run training; omitted means validation only")
    run_training(parser.parse_args())


if __name__ == "__main__":
    main()
