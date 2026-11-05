# Najdi Lab V2.2.0 — development candidate

**Status:** development candidate on `update-project`, Draft PR #23. V2.2.0 is the product version identifier of this batch; it is **not** a public release, a production approval or a merge to `main`.

**Why V2.2.0 (SemVer minor):** new user-facing capabilities (Unsloth Studio export profiles, training-model manager, language metadata, Native-first chat) with no incompatible API or data change for existing records. Migration 010 adds columns and keeps every existing value; the database is copied automatically before it runs. Everything in [V2.1.0](RELEASE_NOTES_V2.1.0.md) is included.

| Area | Change | Record |
|---|---|---|
| Unsloth export (P0) | Unsloth Studio SFT (chat or Alpaca) exports in which each record's only training target is its approved answer; TRL prompt/completion kept for programmatic use and warned against for Studio. Token-level check with Studio's own code: the original export trained earlier answers in 8 of 10 real records; the new profiles train exactly the approved answers | [Training correctness](TRAINING_CORRECTNESS.md) |
| Diagnostics and readiness (P0) | Diagnostics stored when a version is created (no derived copy needed); older frozen versions diagnosed read-only; structural / training-compatibility / evaluation readiness reported separately | [Training correctness §4–5](TRAINING_CORRECTNESS.md#4-diagnostics-lifecycle) |
| Dataset quality | Independent sources, corrections by kind, duplicates, shared contexts, metadata distributions, lengths, split, and a stage (smoke test / exploratory / measurable) that is guidance only; cross-split shared-context and near-duplicate detection | `dataset_health.statistics` |
| Language metadata (P0) | Language, dialect / variety, style and domain as separate optional fields with custom values; Arabic dialects only for Arabic; legacy layers kept and mapped only where certain; migration 010 with an automatic pre-migration backup | [Language metadata](LANGUAGE_METADATA.md) |
| Manual data | SFT, Direct Language and DPO tested end to end; each reaches its own export file; only SFT enters the Unsloth handoff | `tests/test_dataset_quality_v22.py` |
| Chat | NajdiLab Native first in the model menu (existing LM Studio / Ollama conversations stay readable; opt-in in Settings); memory checked before a running model is stopped | [Chat composer](CHAT_COMPOSER.md) |
| Runtime and models | Runtime downloads resume after a dropped connection; Model library → Training models checks and downloads Safetensors checkpoints with approval and lists the Hugging Face cache read-only | [Managed runtime §3](MANAGED_RUNTIME.md#3-safety-rules) |
| Usability | Export Center step guide and readiness summary before export; optional data-entry presets | — |
| Public readiness | Security review, personal paths removed from documentation | [Public readiness](PUBLIC_READINESS.md) |

## Open acceptance gates

- GitHub Actions on the final commit (not triggered, as instructed).
- An actual Unsloth Studio training run on a `studio_chat` export, and an evaluation set for measuring quality.
- A clean installation on a second machine or a fresh Windows account.
- Owner decisions listed in [Public readiness](PUBLIC_READINESS.md) (license, history, publication).
- Owner review of PR #23.

## Rollback

Restore the database copy written before migration 010 (`data/backups/najdilab-before-010_language_metadata-*.db`), then check out the previous version: see [Language metadata §4](LANGUAGE_METADATA.md#4-backup-before-any-schema-change-and-recovery).
