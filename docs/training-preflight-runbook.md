# Training preflight runbook

**Current scope notice (2026-10-31):** training execution is retired. This historical guide does not authorize a trainer, WSL worker, model/GGUF release or installed update. Use the [dataset-first roadmap](roadmap.md) and [Chat/external handoff contract](chat-workspace.md). Existing data/exports remain unchanged.

Preflight proves that the selected model, dataset, configuration and environment agree before READY. It performs no optimizer steps.

## Sequence

1. Select a registered, validated, non-excluded model.
2. Select a dataset passing quality and release validation.
3. Configure LoRA/QLoRA, rank, alpha, target modules, learning rate, batch size, accumulation, epochs/steps, sequence length, precision, checkpointing and seed.
4. Run a live environment check. Measurements must identify `LIVE`, `CACHED`, `ESTIMATE` or `UNAVAILABLE`.
5. Review VRAM. An estimate does not guarantee fit.
6. Create DRAFT and run Safe Dry Run to generate the execution manifest only.

## Stop conditions

- Unvalidated, excluded or changed model fingerprint.
- `BLOCKED` dataset quality or stale dataset fingerprint.
- Failed CUDA, tokenizer, Transformers, Unsloth, PEFT, TRL or bitsandbytes checks required by the selected runtime.
- Missing required live measurements or insufficient VRAM.
- Staging, runtime or worker no longer matches the job snapshot.

## Historical live measurement — 2026-10-09

NVIDIA GeForce RTX 5070: 12,227 MiB total, 586 MiB used and 11,358 MiB available at observation. Python 3.13.15; PyTorch 2.12.1+cu132; CUDA 13.2; Transformers 5.5.0; Unsloth 2026.9.12; PEFT 0.21.1; TRL 0.24.0; bitsandbytes 0.50.2. These are recorded observations, not a portable installation lockfile or fresh evidence.

## Approval boundaries

Safe Dry Run and environment checks do not authorize optimizer work. Smoke needs explicit approval. Full Training requires separate approval after successful Smoke, and grants no merge, GGUF or Ollama authorization. Existing historical approvals do not apply to a new environment or changed fingerprints.
