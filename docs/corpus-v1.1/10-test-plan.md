# 10 — Test Plan

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23).** No tests were added or run in Phase 1. The existing suite (230 tests + 8 subtests per `docs/master-execution-board.md`) is the regression baseline.

## 0. Test-execution rules
- Run tests in an **isolated copy** of the repo (or with a temp-directory override), because the suite creates `.test-temp*` / `.pytest_*` folders in the project root (K8).
- Never point tests at `data/najdilab.db`, `exports/`, frozen `datasets/`, or `training/jobs/`. Use fixtures or restore-proof copies.
- Record the protected-hash inventory before and after every test campaign that touches DB-adjacent code.

## 1. Regression (every phase)
Full existing suite passes. Protected inventories (frozen datasets, exports, training evidence, Corpus v1.0 `ORIGINAL_FILES.sha256`) are byte-identical.

## 2. Phase 1A
| Area | Tests |
|---|---|
| Security S1–S4 | Cross-origin write → 403, no state change · `text/plain` write → 415 · bad `Host` → rejected (GET/POST) · Hermes-like request without Origin → accepted · missing or invalid CSRF token from the UI → 403 · every UI write path sends the token (UI contract test) |
| Adapter reconciliation | Plan-mismatch unit and regression tests and safe-deployment tests run against both candidate versions in isolation; deploy evidence test (destination hash = source hash, backup created) |
| Migration 006 runner | Preflight refuses without backup or token · rehearsal on a restore-proof copy: integrity ok, FK check empty, pre-existing tables' row counts and column checksums identical · re-run changes zero rows · UPDATE/DELETE on `review_events` aborts |

## 3. Phase 2
| Area | Tests |
|---|---|
| Migration 008 | All of the 006 runner tests · legacy rows: every column identical except the new `review_state='LEGACY'` · new insert with LEGACY refused · return to LEGACY refused |
| Lifecycle | Transition matrix (all allowed and forbidden pairs) · approval bound to version and hash; an edit resets it · self-approval → 403 · `ai_suggestion` approval → refused · direct SQL `UPDATE … SET training_eligible=1` on a non-approved item → ABORT |
| Gates | Export gate 409 `MANUAL_ITEM_UNAPPROVED` / `APPROVAL_HASH_MISMATCH` / `SELF_APPROVAL` · training quality gate rejects a dataset containing unapproved generated items |
| Identity S6–S8 | PIN hashing (PBKDF2, salt, iterations) · session expiry · role matrix enforced server-side for every route in `05-…` §3 · re-auth for freeze, authorize and generation run |

## 4. Phase 3 (G2)
| Area | Tests |
|---|---|
| G2-D per code | ≥ 20 seeded positives and ≥ 20 hard negatives per code · precision and recall computed and reported · stable finding IDs across runs |
| Corpus v1.0 fixtures | Read-only copies verified against `ORIGINAL_FILES.sha256` before use · per-code recall on the human-labelled deterministic subset |
| False blocks | Zero G2-D blockers on approved Gold and on existing frozen training records (read-only scan) |
| G2-H | Signals computed and never blocking (test that a G2-H-only item can still be approved) |
| Scope honesty | The report includes the not-covered dimensions list |

## 5. Phases 4–6
| Area | Tests |
|---|---|
| Candidate review | Queue filters · blind defaults · double-annotation assignment never gives both copies to one reviewer · κ computation against known fixtures · Phase 3.8 v009 review flow regression unchanged |
| Gold authoring | Taxonomy validation against the controlled vocabularies · submit → `PENDING_REVIEW` |
| Generator (G1) | Operator unit tests · typed-lexicon completeness · agreement engine per group type × layer · determinism (identical hashes for the same seed) · property tests: no stacked prepositions, slot value ≤ 2, no v1.0 skeleton reproduced · generated items always `training_eligible=0` and `PENDING_REVIEW` · the generator refuses to run without a recorded G1 pass |

## 6. Phases 7–8
Pilot measurements per `04-…` G3 table; G4 checks on the candidate release; existing release-validation, loss-mask and leakage tests; template-level leakage test (skeleton overlap train vs eval = 0 above the threshold).
