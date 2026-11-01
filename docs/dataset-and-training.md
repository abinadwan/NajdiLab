# Dataset lifecycle and optional training

**Current scope notice (2026-10-31):** training execution is retired. This historical guide does not authorize a trainer, WSL worker, model/GGUF release or installed update. Use the [dataset-first roadmap](roadmap.md) and [Chat/external handoff contract](chat-workspace.md). Existing data/exports remain unchanged.

Clients send completed turns through authenticated Ingest. Human review overlays approve/correct/exclude/restore decisions without replacing originals. Manual SFT/direct/preference items carry provenance/privacy/version metadata; Corpus v1.1's pending-review lifecycle is a future gate, not universally implemented. Inspect current eligibility flags.

Export blocks evaluation-only, sensitive/personal, ignored/archived/excluded data. Corrections substitute only in export copies. Deterministic cleaning, exact/near-duplicate checks, holdout/conversation separation, quality/balance and masks gate a new version. Catalog covers immutable exports and managed datasets; duplicate IDs fail. Derived candidates preserve parents; freeze/release validates files/manifests. Arabic training/evaluation strings are never translated for interface localization.

See [export](training-export.md), [native tool contract](tool-runtime-contract.md) and [status](../PROJECT_STATUS.md). Missing evidence is unknown/blocked. A '-draft' name can now identify a frozen version; trust the validated manifest. Corpus Gold/Silver generation remains planned, separately authorized work.

## Controlled runtime sequence

1. Select an authorized base/revision/path and review model/data terms. Missing weights never start onboarding downloads.
2. Register isolated runtime/model. Validate tokenizer, native-tool serialization/masks, dependencies/CUDA and live VRAM evidence.
3. Select a quality-validated immutable dataset and review LoRA/QLoRA rank/alpha/modules, precision, context length, batch/accumulation, seed, epochs/max_steps and output path.
4. Preflight checks contracts. Dry Run builds/verifies manifests/staging with **zero optimizer steps**. READY grants no training permission.
5. Smoke is a small approved optimizer workload. Full Training needs distinct authorization bound to unchanged fingerprints; CSRF is additional to execution authorizations.
6. Monitor only the intended attempt/checkpoints/logs. Adapter validation and recovery/resume require matching evidence and approval.
7. Evaluate locked holdout without fallback/leakage, preserving Base/Adapter identity. Human final decision controls promotion; similarity is diagnostic.

Historical Phase 3 ended REJECT. Round 2 was a 66-record Dry Run, no retraining. Merge/GGUF/Ollama remain blocked. Do not reconcile WSL/repository adapter drift, run corpus builders or reuse historical READY as approval. See [preflight](training-preflight-runbook.md), [model selection](model-selection-guide.md) and [next snapshot](next-training-execution-plan.md).

Preserve original/review state, dataset/holdout hashes, runtime/job/model registries, attempts/adapters/checkpoints and evaluation in private backup. Built-in backup covers SQLite+exports only; [full recovery scope](backup-and-restore.md) is broader. Restore/revalidate in isolation, obtain fresh authorizations; never upload private fixtures for CI.
