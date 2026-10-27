# Training readiness sprint report

Date: 2026-10-09 (Asia/Riyadh). Historical results are preserved below; they are not fresh-clone verification or current training authorization.

## Outcome

The single-model software lock was removed. The platform gained a dynamic registry, explicit selection, fail-closed validation and exact model/revision propagation to the loader. Deterministic quality analysis, reproducible release checks, runtime/VRAM evidence, safe job records and an evaluation guard preventing silent Base fallback were added. At the time, the training interface used Arabic RTL with live states.

Overall readiness was `PARTIALLY_READY`: live checks were available and v009 passed release validation, but no alternative validated base was selected, and the newer quality checks blocked v008.

## Implementation matrix

| Work | Result | Status | Evidence |
|---|---|---|---|
| TRAIN-13/14 | Registry, discovery, selection, loader identity | DONE | training/runtime control and contract tests |
| QUAL-02–07 | Deterministic detectors and stable IDs | DONE | `dataset_quality.py`, API/tests |
| VER-02–08/12 | Release fingerprint, masks, fail-closed behavior | DONE | Release-validation API and repeatability tests |
| TRAIN-01–12 | Runtime, VRAM, configuration, jobs, dry run | DONE | Live WSL checks and runtime tests |
| EVAL-01–03 | Adapter validation and no silent fallback | DONE | `evaluation_guard.py` |
| EVAL-04–15 | Expanded evaluation and full linkage | PARTIAL | History preserved; expansion after authorized training |
| UX-12 | Central Arabic localization, RTL, real states | DONE | localization, tests and browser evidence |
| DB preparation | SQL 005/006/007, rollback and tests | DONE | `plans/` only; not applied to production |

## Model selection

Sources were local HF, repository ID and informational Ollama. Live discovery found only rejected historical Ministral (`EXCLUDED/HISTORICAL`), so no trainable model was selected. The setup screen passes `id/path/revision` to the loader without fallback. Later acquisition state belongs to the separate dated corpus inventory.

## Data readiness

- v008: 76 analyzed records, 2 blockers, 52 warnings; release `BLOCKED`.
- v009: 88 analyzed records, 0 blockers, 26 warnings; release `VALID`; fingerprint `f86e83620522f99bafb3102697a92bfaf5d1c478f968fe779db6e16f48da1488`.
- No automatic near-duplicate deletion or change to human corrections.

## Runtime and GPU

RTX 5070 had 12,227 MiB total and 11,358 MiB available at measurement. CUDA and package versions are recorded in the [preflight runbook](training-preflight-runbook.md). VRAM values identify live evidence or estimates; neither predicts all training memory behavior.

## Historical verification

Recorded run: `230 passed, 8 subtests passed in 12.10s`; JavaScript checks passed; final focused checks: `12 passed`. A real desktop browser verified RTL, registry setup, v008 blocking and the unconfigured-model state. A controlled restart returned a successful `/api/v1/health` response. The mobile visual matrix remained partial.

## Integrity

Protected v008/v009/Phase 3 hashes matched before and after. Phase 3 review stayed 24/24 with `REJECT`; model-release Phase 4 stayed `BLOCKED`. SQLite remained WAL, integrity `ok`, zero FK errors and applied migrations 001–004 only. The physical SQLite file hash changed after restart/checkpoint metadata: no byte-identical database claim is made. Schema migration state and review decisions did not change.

## Interface work

Central Arabic localization covered states, models, quality, preflight and jobs, with better focus/contrast/long identifiers and **Not configured** when no valid model existed. These statements describe the historical interface, before English-readiness work.

## Remaining gates and next action

Production migrations 005/006/007 need separate approval; new persistence remains filesystem-backed or inactive in SQLite. Alternative weights require download approval if absent. Smoke requires approval for two optimizer steps and isolated output. Full Training follows successful Smoke under a separate approval and does not include merge/GGUF/Ollama.

The precise proposed next action was to register an alternative base from Training Setup (local path or repository ID + revision), approve download only if needed, validate and run v009 preflight, then authorize the resulting Smoke job. Final sprint verdict: `PARTIALLY_READY`.
