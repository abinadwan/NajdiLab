# Dataset versions and external Unsloth export

The supported flow is Chat → human review/correction → quality and deduplication → immutable dataset version → external Unsloth handoff. NajdiLab never starts a trainer, loads weights for export, or manages an external training environment.

## Eligibility and privacy

Selection requires explicit human eligibility and excludes archived, excluded, evaluation-only and privacy-restricted records. Demo data requires explicit inclusion. Every message in a contextual window is checked: a restricted earlier message blocks the whole window, rather than being trimmed. A new Unsloth handoff requires a freshly built version attested with `privacy_policy=no_flagged_or_excluded_context_v1`; old versions are preserved, not relabeled.

Original messages and responses remain immutable; corrections are separate overlays. Editing or restoring a record does not establish consent, rights or linguistic quality. Current schema does not provide complete named-reviewer identity or append-only manual-item approval history; see [review limitations](review-and-quality.md).

## Dataset contract

SFT and multi-turn records retain `target_message_index`, `train_on_last_assistant_only=true` and `message_loss_mask`: earlier messages are context, only the final approved assistant target is supervised. `app/dataset_masks.py` and `app/dataset_validation.py` own shared validation; `app/dataset_tools.py` retains pure tool-schema/canonicalization helpers without a controller. `scripts/validate_dataset_masks.py` accepts an explicitly selected local tokenizer path with `trust_remote_code=False`; it does not fetch weights or run optimization.

Conversation-level splitting uses seed 42, targets about 12% holdout (10–15%), caps each evaluation conversation at eight representative records and requires at least three holdout conversations when enough source conversations exist. Gold selection caps multi-turn examples at ten per conversation using a deterministic subset. Selection changes files, never database originals.

Exact target duplicates use casefold/whitespace-normalized SHA256 and priority APPROVED, FULL_CORRECTION, DIALECT_CORRECTION, CONTENT_CORRECTION, then stable insertion order. Near duplicates use SequenceMatcher at 0.90 and remain advisory. Context/target conflicts, invalid masks and train/holdout leakage block where confirmed; no automatic source deletion occurs.

Each new `exports/gold-vNNN/` contains `manifest.json`, the diagnostics `loss-mask-validation.json` and `balancing_report.json` (generated before the version is published, bound to its training files; older versions are diagnosed read-only), `sft.jsonl`, `multi_turn.jsonl`, `direct_language.jsonl`, `preference_pairs.jsonl`, `evaluation_holdout.jsonl`, private `full_archive.json` and `dedup_report.json`. Direct-language and preference assets remain separate from conversational SFT. Managed versions may retain structured native-tool evidence; this does not enable tool execution or make those records supported by the text-only Unsloth handoff.

Manifests record counts, split seed, selection/exclusion and duplicate facts, privacy policy, validation and file hashes. The manifest's own hash is excluded from its hash map. Builds stage in a new temporary directory and publish a new version; existing versions are never rewritten. `manual_data_export_history` records actual included manual items; indexing older JSONL does not mutate old files.

## Unsloth handoff

`POST /api/v1/unsloth-exports` takes `{version, profile}` and publishes immutable `dataset.jsonl`, `provenance.jsonl` and `manifest.json`. It verifies and snapshots every quality/holdout input, rechecks source evidence and keeps each record's sole approved answer as its only training target. Downloads use `/api/v1/unsloth-exports/{hex-id}/{file}` and verify the declared bytes.

Choose the profile for the tool you train with; the files are not interchangeable:

| Profile | Layout | Use with |
|---|---|---|
| `studio_chat` — Unsloth Studio SFT (chat), default | `messages` with exactly one assistant message, the approved answer; earlier turns of a multi-turn record become a transcript inside the user turn | Unsloth Studio with “Train on completions” on and packing off |
| `studio_alpaca` — Unsloth Studio SFT (Alpaca) | `instruction`, `input` (earlier turns), `output` (approved answer) | Unsloth Studio; the Alpaca prompt differs from the model's chat template at inference |
| `trl_prompt_completion` — Unsloth/TRL in Python | conversational `prompt` and `completion` | programmatic TRL/Unsloth with `completion_only_loss=True` and `packing=False`; **not** Unsloth Studio, which also trains the assistant turns inside `prompt` |

Refuse overlength records instead of truncating them, and never merge holdout data or upload the recovery archive. To check which tokens your trainer will supervise, run `scripts/verify_unsloth_studio.py <handoff folder> --model <training model>` with the Python inside your Unsloth Studio install: it runs Studio's own formatting and masking for every record with the model's tokenizer and requires the trained text to be exactly the approved answer. Results, limits and the real-data check: [training correctness](development/TRAINING_CORRECTNESS.md). This is an interoperability contract, not an included trainer; a passing mask check says nothing about model quality. Unsloth package/extras and data/model rights require separate verification; [rights](dependency-licensing-matrix.md).

File hashes and quality PASS establish neither consent nor redistribution rights. Keep raw archives, Chat history, databases and backups private. Privacy changes require a new reviewed version; erasure of existing versions/backups is a separate retention decision.

## Collected Chat context

[The consent/context audit](chat-dataset-context-audit.md) documents complete multi-turn prefixes, single-turn rows, final-only masks and incomplete-prefix quarantine. Enabling collection never imports older roles or approves training. A 60% multi-turn / 40% single-turn mixture is only an experimental idea for later evaluation, never an ingestion quota. Existing frozen files are not rewritten. No schema change is required.
