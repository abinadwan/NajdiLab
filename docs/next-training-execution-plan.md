# Next training execution plan

**Current scope notice (2026-10-31):** training execution is retired. This historical guide does not authorize a trainer, WSL worker, model/GGUF release or installed update. Use the [dataset-first roadmap](roadmap.md) and [Chat/external handoff contract](chat-workspace.md). Existing data/exports remain unchanged.

Historical planning snapshot: 2026-10-09. This is not current authorization.

## Recorded state

Verdict: `PARTIALLY_READY`.

- `gold-v009-remediation-draft`: release gate `VALID`, zero confirmed blockers and 26 review warnings.
- `gold-v008-split-clean`: `BLOCKED` by two conflicting-target groups; do not modify the frozen version.
- The only model discovered during this sprint was historical rejected Ministral; excluded and unselectable. Later acquisition evidence is described separately in the dated corpus design inventory.

## Minimum path to Smoke

1. Select an alternative locally available base, or supply repository ID and revision.
2. If weights are missing, obtain separate download approval and use a new directory.
3. Register the model in the UI and pass live validation.
4. Select v009 provisionally or build a new candidate through the pipeline; preserve v008/v009.
5. Run fresh Preflight and Safe Dry Run; review VRAM and configuration.
6. Obtain explicit Smoke approval bound to the model, dataset fingerprint, `max_steps=2` and isolated output directory.
7. After successful Smoke and regression evaluation, obtain separate Full Training approval.

Migrations 005/006/007, downloading weights, Smoke, Full Training, merge, GGUF and Ollama remain distinct actions. This sprint performed none of them.
