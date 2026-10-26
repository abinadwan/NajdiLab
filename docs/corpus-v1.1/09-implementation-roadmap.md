# 09 — Implementation Roadmap (dependency-ordered)

Status: **APPROVED ROADMAP (rev. 2, 2026-10-23). Phase 1 COMPLETE; Phase 1A NOT AUTHORIZED.** Each phase needs its own explicit approval. Nothing advances automatically. Phase 1 (this documentation set) was the only authorized phase.

```
Phase 1 (docs) ─► 1A-0 baseline (K12) ─► 1A-00 migration loader guard (PRQ-MIG-01) ─► 1A-1 security S1–S4 ─┐
                                    ├─► 1A-2 adapter reconciliation R2–R9
                                    └─► 1A-3 006 guarded runner + apply ─► Phase 2 (008 + lifecycle + identity)
                                                                              │
                     Phase 3 G2 detectors ◄───────────────────────────────────┤ (G2 can start after 1A-0)
                     Phase 4 generic candidate review ◄───────────────────────┤
                     Phase 5 Gold authoring fields ◄──────────────────────────┘
                                         └─► Phase 6 Silver generator + G1 ─► Phase 7 pilot ─► Phase 8 release + training
```

| Phase | Scope | Depends on | Acceptance criteria | Approval needed |
|---|---|---|---|---|
| **1** Specs and decisions | This folder; pointers in `docs/architecture.md` and `docs/master-execution-board.md` | — | Criteria C1–C8 in `17-phase1-approval-package.md` | Owner |
| **1A-0** Baseline | Review the 16 uncommitted or untracked items (K12); commit or park them; record HEAD | 1 | `git status` clean except intended docs; protected-hash inventory recorded | Owner (commits) |
| **1A-00** Migration loader guard | L1–L7 in `15-migration-loader-guard.md`; code only, no migration | 1A-0 | `15` §5 tests 1–5 | Owner (OA-05) |
| **1A-1** Security S1–S4 | Host allowlist, Origin check, JSON Content-Type, CSRF token; UI sends the token | 1A-0 | Tests in `05-…` §4 items 1–5 and 8 pass; Hermes ingest unaffected | Owner (code) |
| **1A-2** Adapter reconciliation | R2–R9 in `06-…` | 1A-0 | Deployed hash = HEAD blob hash = latest-check hash; status docs corrected | Owner per step (deploy separately) |
| **1A-3** Migration 006 | Guarded runner (preflight, backup, restore proof, rehearsal, token); apply 006 | 1A-00, 1A-1 | `07-…` §5 criteria; `review_integrity` reports history available for new decisions | Owner (separate, explicit) |
| **1A-4** (optional) 005 + REG-10 plan | Existing runbook | 1A-0 | Phase 1.3 runbook post-checks | Owner (REG-08/09) |
| **2** Lifecycle, identity, authorization | Migration 008 (runner, rehearsal); service changes; S6–S8; export and training gate codes | 1A-3 | `03-…` §10 items 1–8; `05-…` §4 items 6–7; all legacy rows byte-identical except the new `review_state` | Owner (008 execution separate) |
| **3** G2 detectors | G2-D and G2-H codes in `dataset_quality` (+ candidate scope) | 1A-0 (independent of 2) | `04-…` G2 acceptance table; zero false blocks on approved Gold and frozen training records | Owner (code) |
| **4** Generic candidate review | Generalize the Phase 3.8 queue; rubric; double annotation; κ report | 2 | Decisions are immutable events with a named actor; v009 review behavior unchanged (regression) | Owner (code) |
| **5** Gold authoring | Taxonomy and author fields in `/data/add`; submit flow | 2 | A native author's item reaches the review queue as `PENDING_REVIEW` | Owner (code) |
| **6** Silver generator + G1 | Generator module, typed lexicon, agreement engine, Generation page (preview → explicit run) | 3, 4, 5 | G1 pass; generated items are `PENDING_REVIEW` with lineage and `training_eligible=0`; G2 runs automatically | Owner (code) + per-batch run approval in the UI |
| **7** Pilot | P0 calibration → Gold 60 → Silver 180 (≥ 60 reviewed) → Bronze only if OA-04 | 6 | `04-…` G3 pilot thresholds; κ ≥ 0.6; G2-D precision and recall targets met on pilot data | Owner |
| **8** Release and training | derive → health → freeze → G4 → existing training and evaluation flow | 7 | Existing release validation VALID; G4 new checks pass; explicit human training authorization; human evaluation decision | Owner at each step |

## Decisions and prerequisites

Superseded by [`13-decision-register.md`](13-decision-register.md) (P1 / DF / OA categories, recommended defaults, impact). Phase 1 closing criteria: [`17-phase1-approval-package.md`](17-phase1-approval-package.md).
