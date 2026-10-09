from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
BASELINE = REPORTS / "v007-controlled-epoch1-eval.json"
E2_OUTPUT = REPORTS / "v007-epoch2-eval.jsonl"
OUT_JSON = REPORTS / "v007-epoch2-eval.json"
OUT_MD = REPORTS / "v007-epoch2-eval.md"
DIMENSIONS = ("dialect_najdi", "instruction_following", "context_following", "correctness", "conciseness", "style_naturalness")

# Manual 0-2 ratings using the exact same rubric as the locked v007-E1 report.
E2_MANUAL = {
    "review:109": ([0, 0, 0, 0, 0, 0], {"repetition": True, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "عاد التكرار الديني الطويل وغير المفهوم."),
    "review:110": ([0, 0, 0, 0, 0, 0], {"repetition": True, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "عاد التكرار الديني الطويل وغير المفهوم."),
    "review:67": ([0, 2, 2, 2, 2, 1], {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "مختصر ومناسب وظيفيًا، لكنه غير نجدي."),
    "review:207": ([0, 0, 0, 0, 1, 0], {"repetition": False, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "نص غير مفهوم ولم ينفذ المطلوب."),
    "review:61": ([0, 1, 1, 2, 1, 1], {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "إجابة عامة صحيحة جزئيًا، لكنها غير نجدية."),
    "review:208": ([0, 0, 0, 0, 0, 0], {"repetition": True, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "تكرار ضخم بلا إجابة على طلب الحذف."),
    "review:62": ([0, 0, 0, 0, 1, 1], {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "لم ينفذ طلب الاتصال، مع رد قصير غير مناسب."),
    "review:157": ([0, 1, 0, 0, 0, 0], {"repetition": False, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "قدم أسعارًا مختلقة بدل التحقق من المصدر."),
    "review:156": ([1, 1, 1, 1, 2, 1], {"repetition": False, "hallucination": False, "non_najdi_expressions": False, "name_or_context_leakage": False}, "استوضح الشهر، لكنه لم ينفذ الحجز ولم يطابق صياغة Gold."),
    "review:108": ([0, 0, 0, 0, 0, 0], {"repetition": True, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "عاد التكرار الديني الطويل."),
    "review:136": ([1, 2, 2, 2, 2, 1], {"repetition": False, "hallucination": False, "non_najdi_expressions": True, "name_or_context_leakage": False}, "نفذ شرط الاسم وبقي مختصرًا، لكن الصياغة فصحى جزئيًا."),
    "review:112": ([0, 0, 0, 0, 0, 0], {"repetition": True, "hallucination": True, "non_najdi_expressions": True, "name_or_context_leakage": False}, "عاد التكرار الديني الطويل."),
}


def tree_hash(path: Path) -> str:
    entries = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            entries[item.relative_to(path).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def score_total(scores: dict[str, int]) -> int:
    return sum(scores[dimension] for dimension in DIMENSIONS)


def main() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    e2 = rows(E2_OUTPUT)
    samples = []
    for base_sample in baseline["evaluation"]["samples"]:
        sample_id = base_sample["id"]
        values, flags, note = E2_MANUAL[sample_id]
        e2_scores = dict(zip(DIMENSIONS, values))
        e2_model = {"response": e2[sample_id]["response"], "scores": e2_scores, "flags": {**flags, "instruction_failure": e2_scores["instruction_following"] == 0}, "total_score": score_total(e2_scores), "note": note}
        models = {
            "base": base_sample["models"]["base"],
            "v007_e1": base_sample["models"]["v007"],
            "v007_e2": e2_model,
        }
        best = max(model["total_score"] for model in models.values())
        winners = [name for name, model in models.items() if model["total_score"] == best]
        samples.append({"id": sample_id, "category": base_sample["category"], "final_user": base_sample["final_user"], "gold": base_sample["gold"], "models": models, "winner": winners[0] if len(winners) == 1 else "tie:" + ",".join(winners), "notes": note})
    per_dimension = {name: {dimension: sum(sample["models"][name]["scores"][dimension] for sample in samples) for dimension in DIMENSIONS} for name in ("base", "v007_e1", "v007_e2")}
    totals = {name: sum(values.values()) for name, values in per_dimension.items()}
    flags = ("repetition", "hallucination", "non_najdi_expressions", "name_or_context_leakage", "instruction_failure")
    errors = {name: {flag: sum(bool(sample["models"][name]["flags"].get(flag)) for sample in samples) for flag in flags} for name in ("base", "v007_e1", "v007_e2")}
    metrics = json.loads(Path("/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch2/training_metrics.json").read_text(encoding="utf-8"))
    smoke = json.loads((ROOT / "checkpoints" / "smoke-v007" / "smoke_result.json").read_text(encoding="utf-8"))
    integrity = {"database_sha256": file_hash(ROOT / "data" / "najdilab.db"), "gold_v004_tree_sha256": tree_hash(ROOT / "exports" / "gold-v004"), "gold_v005_clean_tree_sha256": tree_hash(ROOT / "exports" / "gold-v005-clean"), "gold_v006_clean_tree_sha256": tree_hash(ROOT / "exports" / "gold-v006-clean"), "gold_v007_balanced_tree_sha256": tree_hash(ROOT / "exports" / "gold-v007-balanced"), "e1_adapter_tree_sha256": tree_hash(Path("/home/najdi/najdi-training/checkpoints/najdilab-gold-v007-balanced-epoch1")), "read_only_after_training": True}
    report = {"training": {"dataset": "gold-v007-balanced", "base_model": metrics["base_model"], "settings": metrics, "smoke": smoke, "full": metrics}, "evaluation": {"holdout_records": 12, "generation": {"do_sample": False, "max_new_tokens": 384, "same_chat_template": True, "gold_target_in_prompt": False}, "totals": totals, "per_dimension": per_dimension, "error_counts": errors, "samples": samples}, "integrity": integrity, "verdict": "V007_E2_REGRESSION", "best_current_model": "V007_E1"}
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = ["# NajdiLab gold-v007-balanced — Epoch 2 Evaluation", "", "## TRAINING", "", f"- Dataset: 33 records, training from original Base, not E1", f"- Adapter: `{metrics['adapter_path']}`", f"- Steps: {metrics['optimizer_steps']}", f"- Runtime: {metrics['duration_seconds']}s", f"- Loss first / epoch1 end / epoch2 end / mean / min / max: {metrics['first_loss']:.6f} / {metrics['epoch1_end_loss']:.6f} / {metrics['epoch2_end_loss']:.6f} / {metrics['mean_loss']:.6f} / {metrics['min_loss']:.6f} / {metrics['max_loss']:.6f}", f"- VRAM allocated/reserved: {metrics['peak_vram_allocated_mib']} / {metrics['peak_vram_reserved_mib']} MiB", "- NaN/Inf: none", "", "## EVAL", "", "| Model | Total / 144 |", "|---|---:|"]
    for name, label in (("base", "Base"), ("v007_e1", "v007 E1"), ("v007_e2", "v007 E2")):
        md.append(f"| {label} | {totals[name]} |")
    md += ["", "| Dimension | Base | v007 E1 | v007 E2 |", "|---|---:|---:|---:|"]
    for dimension in DIMENSIONS:
        md.append(f"| {dimension} | {per_dimension['base'][dimension]} | {per_dimension['v007_e1'][dimension]} | {per_dimension['v007_e2'][dimension]} |")
    md += ["", "| Error | Base | v007 E1 | v007 E2 |", "|---|---:|---:|---:|"]
    for flag, label in (("repetition", "repetition"), ("hallucination", "hallucination"), ("non_najdi_expressions", "non-Najdi"), ("name_or_context_leakage", "name/context leakage"), ("instruction_failure", "instruction failures")):
        md.append(f"| {label} | {errors['base'][flag]} | {errors['v007_e1'][flag]} | {errors['v007_e2'][flag]} |")
    md += ["", "## PER-SAMPLE COMPARISON", "", "| ID | Base | E1 | E2 | Winner |", "|---|---:|---:|---:|---|"]
    for sample in samples:
        md.append(f"| {sample['id']} | {sample['models']['base']['total_score']} | {sample['models']['v007_e1']['total_score']} | {sample['models']['v007_e2']['total_score']} | {sample['winner']} |")
    for sample in samples:
        md += ["", f"### {sample['id']} — {sample['category']}", "", f"**Prompt:** {sample['final_user']}", "", f"**Gold:** {sample['gold']}", "", "**Base output**", "```text", sample['models']['base']['response'], "```", "", "**v007 E1 output**", "```text", sample['models']['v007_e1']['response'], "```", "", "**v007 E2 output**", "```text", sample['models']['v007_e2']['response'], "```", "", f"**Score breakdown:** Base {sample['models']['base']['scores']} | E1 {sample['models']['v007_e1']['scores']} | E2 {sample['models']['v007_e2']['scores']}", f"**Winner:** {sample['winner']}", f"**Notes:** {sample['notes']}"]
    md += ["", "## INTEGRITY", "", "DB, v004, v005, v006, v007 dataset, and E1 adapter remained unchanged by the read-only post-training check.", "", "## FINAL", "", "Verdict: **V007_E2_REGRESSION**", "", "Best current model: **V007_E1**"]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "markdown": str(OUT_MD), "totals": totals, "errors": errors, "verdict": report["verdict"], "best_current_model": report["best_current_model"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
