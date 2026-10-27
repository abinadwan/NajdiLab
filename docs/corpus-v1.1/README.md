# Najdi Corpus v1.1 / Najdi Assistant SFT — Phase 1 Design Set

Status: **Phase 1 COMPLETE: design approved by the owner on 2026-10-23 (rev. 2). Documentation only; nothing in this folder has been implemented. Phase 1A is NOT authorized.** Arabic examples and word lists are provisional until native validation (PRQ-LANG-01). No code, schema, data, dataset, model, adapter, Hermes, Ollama or WSL runtime change was made. Phase 1A and Phase 2 need separate, explicit approval.

Date: 2026-10-23 · Design baseline approved by the owner: NajdiLab-first architecture (NajdiLab is the authoritative platform and UI; NajdiTrain is its training runtime).

## Reading order

| # | Document | Purpose |
|---|---|---|
| 01 | [Behavior specification](01-behavior-spec.md) | SFT objective, the Najdi assistant voice, Riyadh Najdi definition, register matrix, task taxonomy |
| 02 | [Component reuse map](02-component-reuse-map.md) | Gold/Silver/Bronze and G1–G4 mapped onto existing modules, tables, APIs and pages |
| 03 | [Review lifecycle](03-review-lifecycle.md) | Manual-item lifecycle; no generated record becomes trainable without human approval |
| 04 | [Quality gates](04-quality-gates.md) | G1–G4; revised G2 (deterministic vs heuristic vs human-only) |
| 05 | [Security prerequisites](05-security-prerequisites.md) | CSRF/Origin/Host, server-side authorization, reviewer identity |
| 06 | [Adapter drift K2](06-adapter-drift-k2.md) | Hash evidence and verification-based reconciliation plan |
| 07 | [Migration review 005–007 + 008 proposal](07-migration-review-005-007.md) | Dependencies, hazards, draft 008 (not a file, not applied) |
| 08 | [Risk register](08-risk-register.md) | K1–K24 |
| 09 | [Implementation roadmap](09-implementation-roadmap.md) | Dependency-ordered phases (incl. 1A-00 loader guard) and acceptance criteria |
| 10 | [Test plan](10-test-plan.md) | Tests per phase and execution rules |
| 11 | [Rollback plan](11-rollback-plan.md) | Rollback per change type |
| 12 | [Traceability matrix](12-traceability-matrix.md) | Every behavior requirement → deterministic / advisory / structural / human / process validation |
| 13 | [Decision register](13-decision-register.md) | P1 (before Phase 1 approval) / DF (deferred) / OA (separate owner approval), with defaults and impact |
| 14 | [Git working-tree inventory](14-git-working-tree-inventory.md) | The 16 pre-existing uncommitted items and a non-destructive reconciliation plan |
| 15 | [Migration loader guard](15-migration-loader-guard.md) | Why all migrations stay blocked; required guard properties |
| 16 | [UI-first confirmation](16-ui-first-confirmation.md) | Every routine workflow through NajdiLab with human control points |
| 17 | [Phase 1 approval package](17-phase1-approval-package.md) | Decision table, blockers, closing criteria C1–C8 |
| ADR | [adr/](adr/) | ADR-001 … ADR-011 (all Accepted, 2026-10-23) |

## Related evidence outside NajdiLab
- Corpus v1.0 (frozen, NO-GO): `<corpus-archive-root>/governance/v1.0/STATUS.json` and `PHASE0_REPORT.md` (WSL distro `NajdiTrain`).

## Pointers added to existing docs (additive only)
- `docs/architecture.md`: a short "Corpus v1.1 track (design only)" section.
- `docs/master-execution-board.md`: a "Corpus v1.1 Track" table with design-only statuses.
