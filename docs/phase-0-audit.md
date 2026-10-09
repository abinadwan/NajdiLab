# Phase 0 — Current-state audit

Date: 2026-10-05. Scope: source, frontend, backend, SQLite schema, routes, tests, export, training and evaluation utilities. The audit did not modify `data/`, `exports/`, `reports/`, checkpoints, or historical Gold versions.

## Baseline

- Runtime: Python 3.11+ standard library only; local `ThreadingHTTPServer` on `127.0.0.1:8770`.
- UI: framework-free HTML, CSS, and JavaScript; Arabic RTL.
- Persistence: SQLite with foreign keys, WAL, busy timeout, and ordered SQL migrations.
- Tests: 55 tests passed before Phase 1 changes.

## Implemented and reusable

- Conversation ingestion, Hermes idempotency, secret redaction, and pseudonymous continuity.
- Immutable source messages with review overlays and auditable approve/correct/ignore/delete lifecycle.
- Manual SFT, direct-language, and preference records with version and export history.
- Training eligibility, evaluation-only, privacy, archival, and exclusion gates.
- Deterministic holdout, exact duplicate removal by priority, near-duplicate reporting, multi-turn balancing, JSONL validation, manifests, and SHA-256 checksums.
- Loss-mask validation and deterministic v007 window selection exist as reusable Python modules.

## Gap map

| Area | Current state | Next safe increment |
|---|---|---|
| Dashboard | Added in first Phase 1 slice | Health trends and actionable warnings |
| Inbox / Review Lab | Functional | Pagination and richer detail navigation |
| Gold Library | Export list exists | Manifest detail and freeze metadata |
| Health / Balancer | Core algorithms exist | Read-only reports and explicit build flow |
| Eval Sets | Export holdout exists | First-class immutable registry |
| Base models | Not implemented | Additive registry and benchmarks |
| Training | Scripts exist outside UI | Presets, preflight, worker contract, monitor |
| Evaluation / Compare | Partial schema/reports | Registry and explicit jobs |
| Model Registry | Not implemented | Artifacts and approval records |
| Export / Deploy | Gold export exists | Explicit model export plans |
| Knowledge / Routing | Not implemented | Foundation after lifecycle stability |

## Risks and phase gates

`service.py` mixes several domains and should be split only behind compatible boundaries. Production data is colocated with the app, so every migration needs snapshot verification. Training scripts have optional ML dependencies and local model paths that are not web-app requirements. Every phase must keep the full test suite green, use additive migrations, preserve source messages and historical exports, require explicit action for compute-heavy operations, update the README, and include browser-based visual review.
