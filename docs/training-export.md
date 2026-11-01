# Training export

**Current scope notice (2026-10-31):** training execution is retired. This historical guide does not authorize a trainer, WSL worker, model/GGUF release or installed update. Use the [dataset-first roadmap](roadmap.md) and [Chat/external handoff contract](chat-workspace.md). Existing data/exports remain unchanged.

## Eligibility

Training files accept only `training_eligible=true` records with `archived=false`, `evaluation_only=false` and `exclude_from_training=false`, subject to privacy and review-integrity gates. Demo records are excluded unless explicitly included. Non-archived, non-excluded evaluation-only samples go only to `evaluation_holdout.jsonl`, never SFT, direct language or preference files.

## SFT and multi-turn supervision

Each SFT record declares `target_message_index` (the final Gold assistant response), `train_on_last_assistant_only: true`, and a `message_loss_mask` that is zero for context and one for the final target. Earlier assistant responses remain context.

`scripts/train_najdi_sft.py` consumes these masks, sets context-token labels to `-100`, and retains labels only on the final Gold assistant response. It uses the tokenizer's actual chat template and refuses templates whose target boundary cannot be proved, rather than guessing. Model-specific native tool records follow the [tool runtime contract](tool-runtime-contract.md); authoritative tool outputs are masked.

## Training/evaluation separation

Conversation-level splitting uses seed `42`. No evaluation conversation enters training. Each evaluation conversation contributes at most 8 representative records; additional conversations are selected deterministically toward approximately 12% holdout (10–15%), preferring domain/review-status diversity. With at least three available conversations, export fails unless the holdout spans at least three.

## Multi-turn balancing

Gold export keeps at most 10 multi-turn records per `conversation_id`. When over limit, a deterministic seed-42 subset preserves review-status diversity where possible. This changes the export selection only, never database rows.

## Duplicates

The pre-export report uses SHA-256 of normalized targets (`casefold` and whitespace normalization) for exact duplicates and standard-library `SequenceMatcher` at 0.90 or above for near duplicates. Exact duplicates are removed only from Gold files, keeping priority `APPROVED`, `FULL_CORRECTION`, `DIALECT_CORRECTION`, `CONTENT_CORRECTION`, then stable insertion order. No database record is deleted. Near duplicates remain report-only and are never silently removed.

## Version layout

```text
exports/gold-v001/
  manifest.json
  sft.jsonl
  multi_turn.jsonl
  direct_language.jsonl
  preference_pairs.jsonl
  evaluation_holdout.jsonl
  full_archive.json
  dedup_report.json
```

`sft.jsonl` holds two-message records; `multi_turn.jsonl` holds longer context. Direct-language text and preference pairs do not mix with SFT. `full_archive.json` is an audit archive, not training input. Later native-tool-aware managed datasets can include additional contract files.

## Manifest and history

The manifest includes training/evaluation record and conversation counts, `split_seed`, `exact_duplicates_removed`, `near_duplicate_count`, `demo_records_included` and validation summaries. `sha256` maps data/archive/report files to hashes; it excludes the manifest itself to avoid a circular reference. Each export creates a new version, writes to a temporary directory and atomically renames it without changing an older version.

`manual_data_export_history` records manual items actually present in each version's JSONL files. Indexing a historical version reads JSONL only; it never rewrites old files or manifests. Dataset inclusion does not establish legal rights to publish or train on the underlying content.
