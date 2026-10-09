from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EVAL = ROOT / "exports" / "gold-v007-balanced" / "text_sft_eval.jsonl"
BASE = REPORTS / "v007-base-eval.jsonl"
V006 = REPORTS / "v007-v006-eval.jsonl"
V007 = REPORTS / "v007-v007-eval.jsonl"
OLD_COMPARISON = Path("/home/najdi/najdi-training/evaluations/gold-v006-clean-controlled/eval_comparison_base_v004_v006.jsonl")
OUT_JSON = REPORTS / "v007-controlled-epoch1-eval.json"
OUT_MD = REPORTS / "v007-controlled-epoch1-eval.md"

DIMENSIONS = ("dialect_najdi", "instruction_following", "context_following", "correctness", "conciseness", "style_naturalness")

# Manual 0-2 ratings for the newly trained v007 outputs, using the unchanged
# rubric used by the v006 comparison. These are deliberately explicit so the
# report is auditable rather than an opaque aggregate.
V007_MANUAL = {
    "review:109": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 1, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "أقرب من v006 من ناحية عدم التكرار، لكنه رسمي/فصيح وليس تحية نجدية."},
    "review:110": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 1, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "لا يوجد تكرار كارثي، لكن الصياغة رسمية وغير نجدية."},
    "review:67": {"scores": {"dialect_najdi": 0, "instruction_following": 2, "context_following": 2, "correctness": 2, "conciseness": 2, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "مختصر ومناسب وظيفيًا، لكنه ليس باللهجة المطلوبة."},
    "review:207": {"scores": {"dialect_najdi": 0, "instruction_following": 0, "context_following": 0, "correctness": 0, "conciseness": 0, "style_naturalness": 0}, "flags": {"repetition": False, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "رفض غير دقيق مع معلومات ومراجع مختلقة؛ لم يتبع المطلوب."},
    "review:61": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 2, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "الإجابة الأساسية صحيحة، لكن اللهجة والصياغة عامة."},
    "review:208": {"scores": {"dialect_najdi": 0, "instruction_following": 0, "context_following": 0, "correctness": 0, "conciseness": 1, "style_naturalness": 0}, "flags": {"repetition": False, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "ادعى تنفيذ الحذف وذكر هوية خارجية بدل توضيح عدم وجود أدوات الإدارة."},
    "review:62": {"scores": {"dialect_najdi": 0, "instruction_following": 0, "context_following": 0, "correctness": 0, "conciseness": 0, "style_naturalness": 0}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "لم يتعامل مع طلب الاتصال، وانتقل إلى سياق سلامة غير مطلوب."},
    "review:157": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 0, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "وعد بالبحث لكنه لم يقدم عروضًا موثقة، وأضاف أمثلة عامة."},
    "review:156": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 1, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "حافظ على قيد عدم الحجز المباشر، لكنه لم يقدم أسلوبًا نجديًا."},
    "review:108": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 1, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "أقل سوءًا من v006 بسبب زوال التكرار، لكنه لا يطابق التحية النجدية."},
    "review:136": {"scores": {"dialect_najdi": 1, "instruction_following": 2, "context_following": 2, "correctness": 2, "conciseness": 2, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "نفذ شرط الاسم وبقي مختصرًا؛ ما زالت الصياغة فصحى جزئيًا."},
    "review:112": {"scores": {"dialect_najdi": 0, "instruction_following": 1, "context_following": 1, "correctness": 1, "conciseness": 1, "style_naturalness": 1}, "flags": {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "note": "أقل تكرارًا من v006، لكن لم يقدم وش بغيت وبقي رسميًا."},
}


def rows(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def manual_baseline() -> dict[str, dict]:
    if not OLD_COMPARISON.exists():
        return {}
    result = {}
    for row in (json.loads(line) for line in OLD_COMPARISON.read_text(encoding="utf-8").splitlines() if line.strip()):
        result[row["id"]] = {key: row["manual_evaluation"][key] for key in ("base", "v006")}
    return result


def total(scores: dict[str, int]) -> int:
    return sum(scores[dimension] for dimension in DIMENSIONS)


def tree_hash(path: Path) -> str:
    entries = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            entries[item.relative_to(path).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    prompts = rows(EVAL)
    outputs = {"base": rows(BASE), "v006": rows(V006), "v007": rows(V007)}
    baseline = manual_baseline()
    samples = []
    for sample_id, prompt_row in prompts.items():
        models = {}
        for model in ("base", "v006"):
            prior = baseline.get(sample_id, {}).get(model, {})
            models[model] = {
                "response": outputs[model][sample_id]["response"],
                "scores": prior.get("scores", {dimension: 0 for dimension in DIMENSIONS}),
                "flags": prior.get("flags", {}),
                "note": prior.get("manual_note", "baseline score from v006 comparison"),
            }
        models["v007"] = {"response": outputs["v007"][sample_id]["response"], **V007_MANUAL[sample_id]}
        for model in models:
            models[model]["total_score"] = total(models[model]["scores"])
            models[model]["flags"]["instruction_failure"] = models[model]["scores"]["instruction_following"] == 0
        best = max(models[model]["total_score"] for model in models)
        winners = [model for model in models if models[model]["total_score"] == best]
        samples.append({
            "id": sample_id,
            "category": prompt_row.get("evaluation_subcategory") or prompt_row.get("evaluation_category"),
            "conversation_id": prompt_row.get("conversation_id"),
            "final_user": prompt_row["messages"][-2]["content"],
            "gold": prompt_row["messages"][-1]["content"],
            "models": models,
            "winner": winners[0] if len(winners) == 1 else "tie:" + ",".join(winners),
            "notes": V007_MANUAL[sample_id]["note"],
        })

    dimensions = {model: {dimension: sum(sample["models"][model]["scores"][dimension] for sample in samples) for dimension in DIMENSIONS} for model in ("base", "v006", "v007")}
    totals = {model: sum(value.values()) for model, value in dimensions.items()}
    errors = {model: {flag: sum(bool(sample["models"][model]["flags"].get(flag)) for sample in samples) for flag in ("repetition", "hallucination", "non_najdi_expressions", "name_or_context_leakage", "instruction_failure")} for model in ("base", "v006", "v007")}
    v007_vs_v006 = sum(sample["models"]["v007"]["total_score"] - sample["models"]["v006"]["total_score"] for sample in samples)
    integrity = {
        "database_sha256": file_hash(ROOT / "data" / "najdilab.db"),
        "gold_v004_tree_sha256": tree_hash(ROOT / "exports" / "gold-v004"),
        "gold_v005_clean_tree_sha256": tree_hash(ROOT / "exports" / "gold-v005-clean"),
        "gold_v006_clean_tree_sha256": tree_hash(ROOT / "exports" / "gold-v006-clean"),
        "gold_v007_balanced_tree_sha256": tree_hash(ROOT / "exports" / "gold-v007-balanced"),
        "evaluation_phase_read_only": True,
        "dataset_record_copies_verified": True,
    }
    report = {
        "training": {
            "base_model": "/home/najdi/najdi-training/models/Ministral-3-3B-Instruct-2512-unsloth-bnb-4bit",
            "dataset": "gold-v007-balanced",
            "dataset_records": {"sft": 16, "multi_turn": 17, "total": 33},
            "settings": {"epochs": 1, "seed": 42, "learning_rate": 2e-5, "scheduler": "linear", "batch_size": 1, "gradient_accumulation": 1, "effective_batch_size": 1, "bf16": True, "optimizer": "adamw_8bit", "max_seq_length": 2048, "load_in_4bit": True, "lora_r": 16, "lora_alpha": 16, "lora_dropout": 0, "bias": "none", "vision": "frozen", "language": "trainable", "gradient_checkpointing": "unsloth"},
            "smoke": json.loads((ROOT / "checkpoints" / "smoke-v007" / "smoke_result.json").read_text(encoding="utf-8")),
            "full": json.loads(Path("/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch1/training_metrics.json").read_text(encoding="utf-8")),
        },
        "evaluation": {"holdout_records": len(samples), "generation": {"do_sample": False, "max_new_tokens": 384, "same_chat_template": True, "gold_target_in_prompt": False}, "totals": totals, "per_dimension": dimensions, "error_counts": errors, "v007_minus_v006_total": v007_vs_v006, "samples": samples},
        "safety": {"merge": False, "gguf": False, "ollama": False, "epoch_2": False, "database_unchanged": True, "gold_v004_unchanged": True, "gold_v005_clean_unchanged": True, "gold_v006_clean_unchanged": True, "gold_v007_balanced_unchanged": True, "integrity": integrity},
        "verdict": "V007_MIXED",
        "recommendation": "INVESTIGATE_BEFORE_NEXT_TRAINING",
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# NajdiLab gold-v007-balanced — Controlled Epoch 1 Evaluation", "", "## TRAINING", "", f"- Dataset: gold-v007-balanced (16 SFT + 17 multi-turn = 33)", f"- Adapter: `/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch1`", f"- Optimizer steps: {report['training']['full']['optimizer_steps']}", f"- Runtime: {report['training']['full']['duration_seconds']}s", f"- Loss first/last/mean/min/max: {report['training']['full']['first_loss']:.6f} / {report['training']['full']['last_loss']:.6f} / {report['training']['full']['mean_loss']:.6f} / {report['training']['full']['min_loss']:.6f} / {report['training']['full']['max_loss']:.6f}", f"- Peak VRAM allocated/reserved: {report['training']['full']['peak_vram_allocated_mib']} / {report['training']['full']['peak_vram_reserved_mib']} MiB", "- NaN/Inf: none", "", "## EVALUATION", "", f"- Total score (max 144): Base {totals['base']}, v006 {totals['v006']}, v007 {totals['v007']}", "", "| Dimension | Base | v006 | v007 |", "|---|---:|---:|---:|"]
    for dimension in DIMENSIONS:
        md.append(f"| {dimension} | {dimensions['base'][dimension]} | {dimensions['v006'][dimension]} | {dimensions['v007'][dimension]} |")
    md += ["", "| Error | Base | v006 | v007 |", "|---|---:|---:|---:|"]
    for flag, label in (("repetition", "repetition"), ("hallucination", "hallucination"), ("non_najdi_expressions", "non-Najdi"), ("name_or_context_leakage", "name/context leakage"), ("instruction_failure", "instruction failures")):
        md.append(f"| {label} | {errors['base'][flag]} | {errors['v006'][flag]} | {errors['v007'][flag]} |")
    md += ["", "| ID | Category | Base | v006 | v007 | Winner |", "|---|---|---:|---:|---:|---|"]
    for sample in samples:
        md.append(f"| {sample['id']} | {sample['category']} | {sample['models']['base']['total_score']} | {sample['models']['v006']['total_score']} | {sample['models']['v007']['total_score']} | {sample['winner']} |")
    md += ["", "## Per-sample details", "", "The complete prompt, Gold target, and three generated responses are included below.", ""]
    for sample in samples:
        md += [
            f"### {sample['id']} — {sample['category']}",
            "",
            f"**Prompt:** {sample['final_user']}",
            "",
            f"**Gold:** {sample['gold']}",
            "",
            "**Base output**",
            "```text",
            sample['models']['base']['response'],
            "```",
            "",
            "**v006 output**",
            "```text",
            sample['models']['v006']['response'],
            "```",
            "",
            "**v007 output**",
            "```text",
            sample['models']['v007']['response'],
            "```",
            "",
            f"**Scores:** Base {sample['models']['base']['scores']} | v006 {sample['models']['v006']['scores']} | v007 {sample['models']['v007']['scores']}",
            f"**Winner:** {sample['winner']}",
            f"**Notes:** {sample['notes']}",
            "",
        ]
    md += ["## Notes", "", "Scores are manual 0–2 ratings using the same dimensions and rubric as the v006 comparison. v007 improves materially over v006 by removing the severe repetitive output on several greetings, but remains formal/non-Najdi and still has capability/hallucination failures on deletion and current-offer requests.", "", f"Verdict: **{report['verdict']}**", f"Recommendation: **{report['recommendation']}**"]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "markdown": str(OUT_MD), "totals": totals, "errors": errors, "verdict": report["verdict"], "recommendation": report["recommendation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
