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
| DATA-10 Future-version isolation | P0 | DATA-03–09 | release pipeline | Frozen releases byte-identical after review changes | TODO |

## Phase 3 — Data Quality & Duplicate Detection

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| QUAL-01 current logic audit | P0 | DATA-01 | cleaning/dedup/health | Capability and gap report | DONE |
| QUAL-02–07 detectors | P0 | QUAL-01 | validation modules | Deterministic, traceable fixtures; no silent deletion | TODO |
| QUAL-08–09 finding review queue/actions | P0 | QUAL-02–07, DATA-02 | API/UI | Retain/correct/exclude/intentional with audit | TODO |
| QUAL-10 regression summaries | P0 | QUAL-02–09 | tests/reports | Full quality matrix green | TODO |

## Phase 4 — Dataset Versioning & Release Pipeline

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| VER-01 process audit | P0 | DATA/QUAL audits | export/build modules | Reproducibility and gap report | DONE |
| VER-02–08 reproducible build/validation | P0 | DATA, QUAL | dataset platform | Deterministic isolated builds and lineage | TODO |
| VER-09–11 lifecycle/immutability/UI | P0 | VER-02–08 | registry/API/UI | Draft → Validated → Frozen; blockers visible | TODO |
| VER-12 reproducibility proof | P0 | VER-02–11 | fixtures | Two isolated builds byte-identical | TODO |

This platform phase does not authorize the blocked model-release Phase 4.

## Phase 5 — Runtime, Dependencies & Training Control

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| TRAIN-01–02 environment audit/constraints | P1 | Catalog/release contracts | runtime/config/docs | Versions and ownership evidenced | TODO |
| TRAIN-03–07 recreation/runtime/config checks | P1 | TRAIN-01–02 | isolated env/runtime | Reproducible validation; live VRAM | TODO |
| TRAIN-08–12 profiles, dry-run, recovery, registry, UI | P1 | TRAIN-03–07 | training platform/API/UI | Validation explains READY/BLOCKED; no implicit run | TODO |

Training, adapter merge, GGUF export, and Ollama model creation remain prohibited without separate approval.

## Phase 6 — Evaluation & Human Acceptance

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| EVAL-01–03 pipeline/fallback/config audit | P1 | TRAIN contracts | evaluation modules | Adapter failure cannot fall back silently | TODO |
| EVAL-04–12 human/quality/capability gates | P1 | EVAL-01–03 | reports/API/UI | Blind, repeatable, severity/confidence-aware | TODO |
| EVAL-13–15 lineage/run selector/blocking | P1 | Registry + training | experiment registry/UI | Job→Attempt→Benchmark→Review→Decision | TODO |

## Phase 7 — Platform UX & Operational Quality

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| UX-01–03 theme/accessibility/responsive | P1 | Stable pages | UI/E2E | Light/dark/system±, RTL, focus, mobile | TODO |
| UX-04–09 dynamic state/navigation/diagnostics | P1 | Registries/APIs | UI/API | No stale IDs/counters; robust states | TODO |
| UX-10–11 browser/keyboard/mobile proof | P1 | UX-01–09 | E2E/screenshots | Real browser matrix with evidence | TODO |

## Phase 8 — Regression, Documentation & Release Readiness

| IDs | Priority | Dependencies | Components | Acceptance / tests | Status |
|---|---|---|---|---|---|
| QA-01–06 test matrix/recovery/hashes/status | P1 | Phases 1.3–7 | tests/reports | All critical suites and protected hashes | TODO |
| QA-07–09 documentation/recovery/release notes | P1 | Implemented contracts | docs | Operationally reproducible guidance | TODO |
| QA-10 final acceptance | P1 | QA-01–09 | entire platform | Remaining blockers explicitly listed | TODO |

## Current protected baseline

- Production database has no `dataset_registry_%` tables.
- Phase 3 historical decision remains `REJECT`; Phase 4 remains `BLOCKED`.
- Frozen datasets, original conversations, historical decisions, rejected adapters, and model assets are outside the write scope of this plan.

