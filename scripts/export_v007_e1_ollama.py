from __future__ import annotations

"""Export the locked gold-v007-balanced Epoch-1 adapter.

This script is deliberately conservative: it refuses to overwrite any existing
checkpoint/export, never touches the NajdiLab database or Gold datasets, and
stops before a later stage when an earlier validation fails.
"""

import argparse
import gc
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import torch
from safetensors.torch import save_file
from transformers import AutoModelForImageTextToText, AutoProcessor

# Unsloth must be imported before Transformers/PEFT for its patched model APIs.
from unsloth import FastModel


BASE = Path("/home/najdi/najdi-training/models/Ministral-3-3B-Instruct-2512-unsloth-bnb-4bit")
ADAPTER = Path("/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch1")
MERGED = Path("/home/najdi/najdi-training/merged/najdi-v007-e1-merged")
GGUF_DIR = Path("/home/najdi/najdi-training/gguf/v007-e1")
GGUF = GGUF_DIR / "najdi-v007-e1-Q4_K_M.gguf"
PROJECT = Path(__file__).resolve().parents[1]
OLLAMA_EXPORT = PROJECT / "exports/v007-e1-ollama"
OLLAMA_GGUF = OLLAMA_EXPORT / GGUF.name
REPORT_JSON = PROJECT / "reports/v007-e1-export-report.json"
REPORT_MD = PROJECT / "reports/v007-e1-export-report.md"
OLLAMA_EXE = Path(os.environ.get("NAJDILAB_OLLAMA_EXE") or shutil.which("ollama") or shutil.which("ollama.exe") or "ollama")
TAG = "aboadwan:najdi-v007-e1"
SEED = 42
MAX_NEW_TOKENS = 384
PROMPTS = [
    "ارحب",
    "لاهنت",
    "ابي افرمت جهازي ويندوز 11",
    "من انت؟",
    "وش الفرق بين RAM و SSD؟",
    "مرحبا",
    "كيف اغير DNS في ويندوز 11؟",
    "2+2 كم؟",
    "اكتب لي رد مختصر على شخص قال لاهنت",
    "وش عندك؟",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    files = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(p for p in path.rglob("*") if p.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        rel = str(item.relative_to(path if path.is_dir() else path.parent)).replace("\\", "/")
        file_hash = sha256(item)
        size = item.stat().st_size
        total += size
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(file_hash.encode())
        digest.update(b"\0")
    return {"exists": True, "path": str(path), "files": len(files), "bytes": total, "sha256": digest.hexdigest()}


def protected_fingerprints() -> dict[str, Any]:
    return {
        "db": tree_fingerprint(PROJECT / "data/najdilab.db"),
        "gold_v004": tree_fingerprint(PROJECT / "exports/gold-v004"),
        "gold_v005_clean": tree_fingerprint(PROJECT / "exports/gold-v005-clean"),
        "gold_v006_clean": tree_fingerprint(PROJECT / "exports/gold-v006-clean"),
        "gold_v007_balanced": tree_fingerprint(PROJECT / "exports/gold-v007-balanced"),
        "adapter_e1": tree_fingerprint(ADAPTER),
        "base": tree_fingerprint(BASE),
    }


def assert_unchanged(before: dict[str, Any]) -> dict[str, Any]:
    after = protected_fingerprints()
    changed = [key for key in before if before[key] != after.get(key)]
    if changed:
        raise RuntimeError(f"Protected paths changed: {changed}")
    return after


def ensure_source() -> None:
    if not (BASE / "config.json").is_file():
        raise RuntimeError(f"Base model missing: {BASE}")
    if not (ADAPTER / "adapter_model.safetensors").is_file():
        raise RuntimeError(f"E1 adapter missing: {ADAPTER}")
    cfg = json.loads((ADAPTER / "adapter_config.json").read_text(encoding="utf-8"))
    configured_base = cfg.get("base_model_name_or_path")
    if configured_base != str(BASE):
        raise RuntimeError(f"Adapter points to {configured_base!r}, expected {str(BASE)!r}")
    if MERGED.exists() or GGUF_DIR.exists() or OLLAMA_EXPORT.exists():
        raise RuntimeError("Refusing to overwrite a previous export destination")
    if not OLLAMA_EXE.is_file():
        raise RuntimeError(f"Ollama executable not found: {OLLAMA_EXE}")


def load_adapter(model_path: Path, adapter_path: Path | None, max_seq_length: int = 8192, load_in_4bit: bool = True):
    # Unsloth's merged exporter needs its own adapter-aware loader.  Loading a
    # base model and then wrapping it with PeftModel works for inference, but
    # intentionally fails the exporter safety check.
    source_path = adapter_path if adapter_path is not None else model_path
    model, processor_or_tokenizer = FastModel.from_pretrained(
        model_name=str(source_path),
        max_seq_length=max_seq_length,
        load_in_4bit=load_in_4bit,
        load_in_8bit=False,
        full_finetuning=False,
    )
    processor = processor_or_tokenizer
    tokenizer = getattr(processor_or_tokenizer, "tokenizer", processor_or_tokenizer)
    if getattr(tokenizer, "chat_template", None) is None:
        template = getattr(processor, "chat_template", None)
        if template is not None:
            tokenizer.chat_template = template
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()
    return model, processor, tokenizer


def generate_one(model: Any, processor: Any, tokenizer: Any, prompt: str) -> tuple[str, float, int]:
    renderer = processor if hasattr(processor, "apply_chat_template") else tokenizer
    messages = [{"role": "user", "content": prompt}]
    rendered = renderer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(rendered, return_tensors="pt", add_special_tokens=False, truncation=False)
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.perf_counter() - started
    generated_ids = output[0][prompt_tokens:].tolist()
    text = tokenizer.decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False).strip()
    if not text:
        raise RuntimeError(f"Empty output for prompt {prompt!r}")
    if not all(math.isfinite(float(x)) for x in output.detach().float().flatten()[: min(output.numel(), 1000)]):
        raise RuntimeError("Non-finite token output")
    return text, elapsed, len(generated_ids)


def merged_smoke() -> dict[str, Any]:
    model = AutoModelForImageTextToText.from_pretrained(
        str(MERGED), dtype=torch.bfloat16, device_map="cuda", low_cpu_mem_usage=True
    )
    processor = AutoProcessor.from_pretrained(str(MERGED))
    tokenizer = getattr(processor, "tokenizer", processor)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    results = []
    started = time.perf_counter()
    for prompt in PROMPTS[:5]:
        text, elapsed, generated = generate_one(model, processor, tokenizer, prompt)
        results.append({"prompt": prompt, "output": text, "seconds": round(elapsed, 3), "generated_tokens": generated})
    peak_alloc = round(torch.cuda.max_memory_allocated() / 1024**2, 1) if torch.cuda.is_available() else None
    peak_reserved = round(torch.cuda.max_memory_reserved() / 1024**2, 1) if torch.cuda.is_available() else None
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return {
        "passed": bool(results),
        "prompts": results,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "peak_vram_allocated_mib": peak_alloc,
        "peak_vram_reserved_mib": peak_reserved,
    }


def merge() -> dict[str, Any]:
    before = protected_fingerprints()
    ensure_source()
    MERGED.parent.mkdir(parents=True, exist_ok=True)
    MERGED.mkdir(parents=False, exist_ok=False)
    started = time.perf_counter()
    model, processor, tokenizer = load_adapter(BASE, ADAPTER)
    if not hasattr(model, "merge_and_unload"):
        raise RuntimeError("PEFT merge API is unavailable")
    # The source Base is NF4 and Transformers 5.5 currently cannot serialize
    # Unsloth's forced 4-bit merge (its reverse weight conversion raises
    # NotImplementedError).  Merge the LoRA layers first, dequantize in memory,
    # and write a standalone BF16 safetensors model.  This changes no source
    # files and avoids an unverified/partial export.
    model = model.merge_and_unload()
    model.dequantize()
    model.config.quantization_config = None
    state = {name: value.detach().cpu().contiguous() for name, value in model.state_dict().items()}
    save_file(state, str(MERGED / "model.safetensors"), metadata={"format": "pt", "source": "NajdiLab V007 E1 LoRA merged"})
    config_payload = json.loads(model.config.to_json_string())
    config_payload.pop("quantization_config", None)
    (MERGED / "config.json").write_text(json.dumps(config_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if hasattr(processor, "save_pretrained"):
        processor.save_pretrained(str(MERGED))
    elif hasattr(tokenizer, "save_pretrained"):
        tokenizer.save_pretrained(str(MERGED))
    for name in ("generation_config.json", "README.md"):
        source = BASE / name
        if source.is_file():
            shutil.copy2(source, MERGED / name)
    merge_method = "manual_bf16_safetensors_after_peft_merge"
    if not (MERGED / "config.json").is_file():
        raise RuntimeError("Merged output has no config.json")
    if not (MERGED / "tokenizer.json").is_file():
        raise RuntimeError("Merged output has no tokenizer.json")
    meta = {
        "base_model": str(BASE),
        "adapter": str(ADAPTER),
        "adapter_config": json.loads((ADAPTER / "adapter_config.json").read_text(encoding="utf-8")),
        "save_method": merge_method,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "output": str(MERGED),
    }
    (MERGED / "najdilab-export-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    assert_unchanged(before)
    smoke = merged_smoke()
    return {"merge": meta, "merged_smoke": smoke}


def export_gguf() -> dict[str, Any]:
    before = protected_fingerprints()
    ensure_source()
    if not MERGED.exists():
        raise RuntimeError("Merged output is missing; run merge first")
    GGUF_DIR.mkdir(parents=True, exist_ok=False)
    model, processor, tokenizer = load_adapter(MERGED, None, max_seq_length=8192, load_in_4bit=False)
    if not hasattr(model, "save_pretrained_gguf"):
        raise RuntimeError("Unsloth GGUF save API is unavailable")
    started = time.perf_counter()
    model.save_pretrained_gguf(str(GGUF_DIR), tokenizer=tokenizer, quantization_method="q4_k_m")
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    candidates = sorted(GGUF_DIR.glob("*.gguf"))
    if not candidates:
        raise RuntimeError("Unsloth did not create a GGUF file")
    if GGUF not in candidates:
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one GGUF output, found {candidates}")
        candidates[0].rename(GGUF)
    OLLAMA_EXPORT.mkdir(parents=True, exist_ok=False)
    shutil.copy2(GGUF, OLLAMA_GGUF)
    result = {
        "path": str(GGUF),
        "ollama_copy": str(OLLAMA_GGUF),
        "bytes": GGUF.stat().st_size,
        "sha256": sha256(GGUF),
        "quantization": "Q4_K_M",
        "duration_seconds": round(time.perf_counter() - started, 2),
    }
    (GGUF_DIR / "gguf-export.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    assert_unchanged(before)
    return result


def create_modelfile() -> Path:
    if not OLLAMA_GGUF.is_file():
        raise RuntimeError("Windows-accessible GGUF copy is missing")
    proc = subprocess.run([str(OLLAMA_EXE), "show", "aboadwan:base", "--modelfile"], check=True, capture_output=True, text=True, encoding="utf-8")
    source = proc.stdout
    if not source.strip().startswith("# Modelfile"):
        raise RuntimeError("Could not read the existing aboadwan:base Modelfile")
    lines = source.splitlines()
    replaced_from = False
    replaced_ctx = False
    out = []
    for line in lines:
        if line.startswith("FROM "):
            out.append(f"FROM {OLLAMA_GGUF}")
            replaced_from = True
        elif line.strip().lower().startswith("parameter num_ctx "):
            out.append("PARAMETER num_ctx 8192")
            replaced_ctx = True
        else:
            out.append(line)
    if not replaced_from:
        raise RuntimeError("Source Modelfile had no FROM")
    if not replaced_ctx:
        out.append("PARAMETER num_ctx 8192")
    path = OLLAMA_EXPORT / "Modelfile"
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return path


def ollama_run(prompt: str) -> tuple[str, float]:
    started = time.perf_counter()
    proc = subprocess.run([str(OLLAMA_EXE), "run", TAG, prompt], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stdout.strip(), time.perf_counter() - started


def ollama_test() -> dict[str, Any]:
    before = protected_fingerprints()
    modelfile = create_modelfile()
    create = subprocess.run([str(OLLAMA_EXE), "create", TAG, "-f", str(modelfile)], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    show = subprocess.run([str(OLLAMA_EXE), "show", TAG], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    results = []
    for prompt in PROMPTS:
        output, elapsed = ollama_run(prompt)
        results.append({"prompt": prompt, "output": output, "seconds": round(elapsed, 3)})
    assert_unchanged(before)
    return {
        "tag": TAG,
        "modelfile": str(modelfile),
        "context": 8192,
        "create_stdout": create.stdout[-2000:],
        "show_stdout": show.stdout[-4000:],
        "prompts": results,
    }


def write_report(payload: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> None:
    payload = {
        "source": {
            "base_model": str(BASE),
            "adapter": str(ADAPTER),
            "dataset": "gold-v007-balanced",
            "epochs": 1,
            "optimizer_steps": 33,
            "source_eval_score": "55/144",
            "source_verdict": "BEST_CURRENT_MODEL V007_E1",
        },
        "artifacts": {
            "merged": str(MERGED),
            "gguf": str(GGUF),
            "ollama_gguf_copy": str(OLLAMA_GGUF),
            "ollama_tag": TAG,
        },
        "protected_fingerprints_before": before,
        "protected_fingerprints_after": after,
        **payload,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# NajdiLab V007 E1 export", "", f"- Base: `{BASE}`", f"- Adapter: `{ADAPTER}`", f"- Merged: `{MERGED}`", f"- GGUF: `{GGUF}`", f"- Ollama tag: `{TAG}`", ""]
    for key in ("merged_smoke", "gguf", "ollama"):
        section = payload.get(key)
        if section is not None:
            lines += [f"## {key}", "", "```json", json.dumps(section, ensure_ascii=False, indent=2), "```", ""]
    lines += ["## Protected data", "", "All protected hashes unchanged." if before == after else "WARNING: protected hash changed.", ""]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["merge", "gguf", "ollama", "all"])
    args = parser.parse_args()
    before = protected_fingerprints()
    ensure_source()
    payload: dict[str, Any] = {}
    if args.stage in {"merge", "all"}:
        payload.update(merge())
    if args.stage in {"gguf", "all"}:
        payload["gguf"] = export_gguf()
    if args.stage in {"ollama", "all"}:
        payload["ollama"] = ollama_test()
    after = assert_unchanged(before)
    write_report(payload, before, after)
    print(json.dumps({"stage": args.stage, "report": str(REPORT_JSON), "artifacts": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
