# NajdiLab Master Execution Board

Last updated: 2026-10-09 (Asia/Riyadh). Status values are evidence-based; `DONE` is used only after acceptance verification.

## Phase 1.3 — Production Dataset Registry

| ID | Priority | Dependencies | Components | Acceptance / automated evidence | Status |
|---|---|---|---|---|---|
| REG-01 Recheck Phase 1.2 | P0 | None | Phase 1.2 report/SQL/rollback | Report and artifacts reviewed; risks carried forward | DONE |
| REG-02 Production schema/WAL | P0 | REG-01 | `data/najdilab.db` read-only | WAL; migrations 001–004; integrity ok; FK errors 0 | DONE |
| REG-03 Nine-version verification | P0 | REG-02 | `exports/`, `datasets/`, legacy registry | 13 source records → 9 versions/9 locations; conflicts 0 | DONE |
| REG-04 Backup/restore proof | P0 | REG-02 | `backups/phase13-*` | SQLite Backup API; isolated restore integrity ok | DONE |
| REG-05 Transactional Migration 005 | P0 | REG-03 | `plans/phase13`, registry module/runner | Atomic DDL+backfill; second application changes 0 | DONE |
| REG-06 Conflict/rollback tests | P0 | REG-05 | `tests/test_dataset_registry.py` | Duplicate/path/hash/invalid/missing/FK/transaction rollback: 7 passed | DONE |
| REG-07 Execution/recovery procedure | P0 | REG-04–06 | Phase 1.3 runbook | Guarded commands and exact recovery documented | DONE |
| REG-08 Explicit approval request | P0 | REG-01–07 | User gate | Preparation delivered; explicit separate approval still required | BLOCKED_PENDING_APPROVAL |
| REG-09 Production migration | P0 | REG-08 | Production SQLite | Guard rejects missing approval token; production untouched | BLOCKED_PENDING_APPROVAL |
| REG-10 Canonical API/UI | P0 | REG-09 | API and UI | Requires migrated canonical source and cross-check | BLOCKED_BY_REG-09 |

## Phase 2 — Sample Management & Human Review

| ID | Priority | Dependencies | Components | Acceptance / automated tests | Status |
|---|---|---|---|---|---|
| DATA-01 Relationship audit | P0 | Registry preparation | schema, service, review UI | Trace conversation → message → review → correction/export | DONE |
| DATA-02 Authoritative lifecycle | P0 | DATA-01 | domain/service | Policy and isolated tests prepared; integration requires event migration | BLOCKED_PENDING_DB_APPROVAL |
| DATA-03 Review UI actions | P0 | DATA-02 | API/UI | Approve/correct/exclude/restore verified through service, HTTP, and UI contracts | DONE |
| DATA-04 Original/correction separation | P0 | DATA-01 | SQLite/service | Original remains immutable; prior correction retained across exclude/restore | DONE |
| DATA-05 Immutable audit history | P0 | DATA-02 | SQLite/service | Additive immutable schema/module prepared; production migration not approved | BLOCKED_PENDING_DB_APPROVAL |
| DATA-06 Reviewer metadata/tags | P0 | DATA-05 | SQLite/API/UI | Safe code/fixtures verified; immutable cross-decision metadata requires unapproved event migration | BLOCKED_PENDING_DB_APPROVAL |
| DATA-07 Stale review detection | P0 | DATA-02 | validation/UI | Structured confirmed/ambiguous findings; isolated pending/conflict/stale/history fixtures | DONE |
| DATA-08 Export blocking | P0 | DATA-07 | export gate/API/UI | Fail-closed before filesystem writes; HTTP 409 reasons; frozen-release hash preserved | DONE |
| DATA-09 Search/bulk review | P0 | DATA-02–08 | API/UI | Search plus atomic approve/correct/exclude/restore; complete rollback fixtures | DONE |
| DATA-10 Future-version isolation | P0 | DATA-03–09 | release pipeline | Candidate-only validation; protected releases byte-identical in sprint hash comparison | DONE |

## Phase 3 — Data Quality & Duplicate Detection

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| QUAL-01 current logic audit | P0 | DATA-01 | cleaning/dedup/health | Capability and gap report | DONE |
| QUAL-02–07 detectors | P0 | QUAL-01 | `app/dataset_quality.py` | Stable IDs; duplicates/conflicts/leakage/structure/provenance; no silent deletion | DONE |
| QUAL-08–09 finding review queue/actions | P0 | QUAL-02–07, DATA-02 | API/UI | Read-only findings API/UI complete; decision persistence awaits event migration | PARTIAL |
| QUAL-10 regression summaries | P0 | QUAL-02–09 | tests/reports | 230 tests + 8 subtests green; live v008/v009 results recorded | DONE |

## Phase 4 — Dataset Versioning & Release Pipeline

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| VER-01 process audit | P0 | DATA/QUAL audits | export/build modules | Reproducibility and gap report | DONE |
| VER-02–08 reproducible build/validation | P0 | DATA, QUAL | dataset platform | Deterministic manifest fingerprint, masks and fail-closed quality validation | DONE |
| VER-09–11 lifecycle/immutability/UI | P0 | VER-02–08 | registry/API/UI | Validation/blockers visible; production registry activation awaits Migration 005 | PARTIAL |
| VER-12 reproducibility proof | P0 | VER-02–11 | fixtures | Repeated isolated validation produces identical release fingerprint | DONE |

This platform phase does not authorize the blocked model-release Phase 4.

## Phase 5 — Runtime, Dependencies & Training Control

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| TRAIN-01–02 environment audit/constraints | P1 | Catalog/release contracts | runtime/config/docs | Live RTX 5070/VRAM and Python/CUDA/package versions evidenced | DONE |
| TRAIN-03–07 recreation/runtime/config checks | P1 | TRAIN-01–02 | isolated env/runtime | Live probe, model-aware configuration and conservative estimate | DONE |
| TRAIN-08–12 profiles, dry-run, recovery, registry, UI | P1 | TRAIN-03–07 | training platform/API/UI | Draft→READY guards, manifests and no implicit run; smoke awaits approval | DONE |
| TRAIN-13–14 dynamic Base model selection | P0 | TRAIN-01–12 | registry/API/UI/loader | Exact model ID/path/revision reaches loader; historical Ministral excluded | DONE |

Training, adapter merge, GGUF export, and Ollama model creation remain prohibited without separate approval.

## Phase 6 — Evaluation & Human Acceptance

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| EVAL-01–03 pipeline/fallback/config audit | P1 | TRAIN contracts | `app/evaluation_guard.py` | Explicit Base/Adapter; path/revision mismatch and silent fallback fail closed | DONE |
| EVAL-04–12 human/quality/capability gates | P1 | EVAL-01–03 | reports/API/UI | Existing blind review preserved; expanded scoring workflow remains future work | PARTIAL |
| EVAL-13–15 lineage/run selector/blocking | P1 | Registry + training | experiment registry/UI | Job→Attempt→Benchmark→Review→Decision | TODO |

## Phase 7 — Platform UX & Operational Quality

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| UX-01–03 theme/accessibility/responsive | P1 | Stable pages | UI/E2E | RTL, focus, contrast, long IDs and light/dark/system contracts | DONE |
| UX-04–09 dynamic state/navigation/diagnostics | P1 | Registries/APIs | UI/API | Arabic states, dynamic registry and blocked-quality rendering | DONE |
| UX-10–11 browser/keyboard/mobile proof | P1 | UX-01–09 | E2E/screenshots | Real browser desktop verification done; mobile visual matrix pending | PARTIAL |

## Phase 8 — Regression, Documentation & Release Readiness

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| QA-01–06 test matrix/recovery/hashes/status | P1 | Phases 1.3–7 | tests/reports | 230 tests + 8 subtests; protected datasets/model evidence unchanged | DONE |
| QA-07–09 documentation/recovery/release notes | P1 | Implemented contracts | docs | Selection guide, preflight runbook, next plan and sprint report | DONE |
| QA-10 final acceptance | P1 | QA-01–09 | entire platform | PARTIALLY_READY: no eligible selected Base model; approvals separated | PARTIAL |

## Current protected baseline

- Production database has no `dataset_registry_%` tables.
- Phase 3 historical decision remains `REJECT`; Phase 4 remains `BLOCKED`.
- Frozen datasets, original conversations, historical decisions, rejected adapters, and model assets are outside the write scope of this plan.


## Corpus v1.1 Track — Phase 1 COMPLETE (design approved 2026-10-23)

Design set: [`docs/corpus-v1.1/`](corpus-v1.1/README.md). Phase 1 (documentation only) is **COMPLETE**; criteria C1–C8 are verified in [`17-phase1-approval-package.md`](corpus-v1.1/17-phase1-approval-package.md). **Phase 1A is NOT AUTHORIZED.** Nothing in this track is implemented.

| ID | Priority | Dependencies | Components | Acceptance | Status |
|---|---|---|---|---|---|
| CV11-01 Behavior spec | P0 | — | `corpus-v1.1/01` | Owner approval; P1-03/P1-04 resolved | DESIGN_APPROVED (language content provisional: PRQ-LANG-01) |
| CV11-02 Reuse map | P0 | — | `corpus-v1.1/02` | Owner approval | DESIGN_APPROVED |
| CV11-03 Manual-item review lifecycle | P0 | 006, 008 | `corpus-v1.1/03` | `03` §10 criteria (Phase 2) | DESIGN_APPROVED; NOT IMPLEMENTED |
| CV11-04 G1–G4 / revised G2 | P0 | CV11-01 | `corpus-v1.1/04` | `04` acceptance tables | DESIGN_APPROVED; NOT IMPLEMENTED |
| CV11-05 Security S1–S8 | P0 | 1A-0 | `corpus-v1.1/05` | `05` §4 tests | DESIGN_APPROVED; NOT IMPLEMENTED |
| CV11-06 Adapter drift K2 | P0 | 1A-0 | `corpus-v1.1/06` | R1–R9 | DOCUMENTED; reconciliation BLOCKED_PENDING_APPROVAL (OA-02) |
| CV11-07 Migration review 005–007, 008 draft | P0 | PRQ-MIG-01 | `corpus-v1.1/07` | `07` §5 | REVIEWED; 005/006/007/008 BLOCKED |
| CV11-08 Traceability matrix | P0 | CV11-01 | `corpus-v1.1/12` | No unmapped requirement | DESIGN_APPROVED |
| CV11-09 Decision register | P0 | — | `corpus-v1.1/13` | All P1 resolved or confirmed | P1 CLOSED; DF-01…DF-10 DEFERRED; OA-01…OA-12 PENDING SEPARATE APPROVAL |
| CV11-10 K12 working-tree inventory | P0 | — | `corpus-v1.1/14` | Plan W1–W7 (execution OA-01) | PLAN_APPROVED; execution BLOCKED_PENDING_APPROVAL; 16 items preserved untouched |
| CV11-11 Migration loader guard (PRQ-MIG-01) | P0 | 1A-0 | `corpus-v1.1/15` | `15` §5 tests | DESIGN_APPROVED; NOT IMPLEMENTED (OA-05) |
| CV11-12 UI-first confirmation | P0 | — | `corpus-v1.1/16` | Owner confirmation | CONFIRMED |

### Outstanding prerequisites (visible until closed)

| ID | Prerequisite | Blocks | Status |
|---|---|---|---|
| PRQ-LANG-01 | Native Riyadh Najdi validation of all Arabic word lists and examples | Pilot, any release, blocking dialect detectors | OPEN (needs OA-11: appoint ≥ 2 native reviewers and a linguistic lead) |
| PRQ-BASE-01 | Clean Phase 1A baseline: the 16 uncommitted items reconciled without loss | Any Phase 1A code work | OPEN (OA-01) |
| PRQ-MIG-01 | Migration loader guard implemented and tested | Any SQL entering `migrations/` | OPEN (OA-05) |
| K2 | Adapter drift (WSL `c35e88…` ≠ repo `b14c7c…` ≠ HEAD `6885fe…`; `bb2c52…` unrecoverable) | New training dry runs and authorizations | OPEN (OA-02) |

### Top open risks (full register: `corpus-v1.1/08-risk-register.md`, K1–K24)

| ID | Risk | Status |
|---|---|---|
| K1 | Review audit table (006) not live | OPEN; blocked by PRQ-MIG-01 |
| K4 | Manual items can be inserted trainable without review | OPEN; fixed by lifecycle (Phase 2) |
| K5 | CSRF / DNS rebinding on the local API | OPEN; S1–S4 (Phase 1A, not authorized) |
| K6 | No reviewer identity or roles | OPEN; S6–S8 (Phase 2) |
| K12 | Uncommitted live code; HEAD ≠ running system | OPEN; OA-01 |
| K14 | Migrations auto-apply on server start | OPEN; PRQ-MIG-01 |
| K16 | 007 would create a competing training registry | OPEN; 007 ON HOLD (OA-09) |
| K22 | Unvalidated Arabic content treated as ground truth | OPEN; PRQ-LANG-01 |
| K23 | Repo adapter fractional-epoch rounding (O-1) | OPEN; DF-10 |
