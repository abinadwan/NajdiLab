# 17 — Phase 1 Approval Package and Closure Record

Status: **PHASE 1 COMPLETE. Design approved by the owner on 2026-10-23; criteria C1–C8 verified the same day. Phase 1A is NOT AUTHORIZED.** All deferred decisions (DF) and separate-approval requirements (OA) are unchanged.

## 1. Decision table (final; details in `13-decision-register.md`)

| ID | Decision | Category | Outcome |
|---|---|---|---|
| P1-01 | Natural Riyadh Najdi without dialect quotas or stock phrases | Before Phase 1 approval | **Resolved + confirmed** |
| P1-02 | Model-agnostic design; Gemma 4 E2B IT initial model only; no other model authorized | Before Phase 1 approval | **Resolved + confirmed** |
| P1-03 | MSA user input | Before Phase 1 approval | **Resolved:** follow the user's language and register; MSA input receives clear, natural MSA unless the user requests otherwise; don't impose Najdi unnecessarily |
| P1-04 | Persona and addressing | Before Phase 1 approval | **Resolved:** masculine first-person persona; address users according to available context, adapting to feminine forms when indicated and using natural gender-neutral phrasing when appropriate |
| P1-05 | G2 scope (mechanical defects only; human-only semantics) | Before Phase 1 approval | **Confirmed** |
| P1-06 | Migrations 005/006/007/008 blocked; loader guard first | Before Phase 1 approval | **Confirmed** |
| P1-07 | K12 reconciliation plan (execution is OA-01) | Before Phase 1 approval | **Confirmed** |
| P1-08 | UI-first scope | Before Phase 1 approval | **Confirmed** |
| DF-01…DF-10 | See register | Deferred to its phase | **Unchanged (deferred)** |
| OA-01…OA-12 | See register | Separate owner approval | **Unchanged (none granted)** |

## 2. Final document index (`docs/corpus-v1.1/`)

`README.md` · `01` behavior spec · `02` component reuse map · `03` review lifecycle · `04` quality gates · `05` security prerequisites · `06` adapter drift K2 · `07` migration review 005–007 (+ 008 draft) · `08` risk register K1–K24 · `09` implementation roadmap · `10` test plan · `11` rollback plan · `12` traceability matrix · `13` decision register · `14` git working-tree inventory · `15` migration loader guard · `16` UI-first confirmation · `17` this record · `adr/ADR-001…ADR-011` (all Accepted). 29 files in total.

Outside the folder (additive only, versus HEAD `bcdf4a7`): `docs/architecture.md` (+3 lines), `docs/master-execution-board.md` (+42 lines: Corpus v1.1 track, outstanding prerequisites, top open risks).

## 3. Closure criteria: results

| # | Criterion | Result | Evidence |
|---|---|---|---|
| C1 | Owner closes P1-03 and P1-04 in writing | **PASS** | Owner message 2026-10-23; recorded verbatim in `13` and `01` §2 / §4.1 |
| C2 | Owner confirms P1-01, P1-02, P1-05…P1-08 | **PASS** | Same; register rows marked CONFIRMED |
| C3 | Every BR-xx maps to ≥ 1 R or S method, no gaps; non-claim present | **PASS** | Automated cross-check: 24 requirement IDs in `01`, 24 rows in `12`, none missing or extra, none without an R or S entry; non-claim sentence present |
| C4 | No document describes Arabic examples or word lists as validated | **PASS** | Provisional banner and §7 "PROVISIONAL, UNVALIDATED" present; the scan for validation claims found only two technical uses (code diff, service validation), neither about language |
| C5 | 005/006/007/008 recorded as BLOCKED, with the loader guard as a prerequisite | **PASS** | `07` status, `15` §2, `13` P1-06 / OA-05…OA-09, execution board; `migrations/` still contains only 001–004 |
| C6 | K12 inventory covers all 16 items; no write action taken | **PASS** | `14` lists 16 items; non-doc `git status` identical to the pre-Phase-1 snapshot; nothing staged |
| C7 | UI-first table covers generation, editing, review, approval, dataset management and training authorization | **PASS** | `16`: all six workflow rows present (plus evaluation, migration status, adapter deployment) |
| C8 | Phase 1 changed documentation only | **PASS** | See §5 |

## 4. Remaining prerequisites and risks (carried forward; also on the execution board)

| ID | Item | Blocks | Needs |
|---|---|---|---|
| PRQ-LANG-01 | Native validation of Arabic word lists and examples | Pilot, any release, blocking dialect detectors | OA-11, then sign-off |
| PRQ-BASE-01 | Reconcile the 16 uncommitted items without loss | Any Phase 1A code work | OA-01 |
| PRQ-MIG-01 | Migration loader guard | Any SQL entering `migrations/` | OA-05 |
| K2 | Adapter drift | New dry runs and training authorizations | OA-02 |
| K1, K4, K5, K6, K12, K14, K16, K22, K23 | Open risks | See `08` | See `08` |

## 5. Verification record (2026-10-23)

| Check | Result |
|---|---|
| SHA-256 of 86 protected NajdiLab files (`app/`, `migrations/`, `plans/`, `static/`, `scripts/` excluding caches, `training/models.json`, `training/runtimes.json`, `data/najdilab.db`) vs the pre-Phase-1 snapshot | 86/86 unchanged |
| `data/najdilab.db` hash; no `-wal`/`-shm` created | Unchanged |
| `git status` excluding Phase 1 docs vs the pre-Phase-1 snapshot | Identical (the same 11 modified + 5 untracked pre-existing items); index empty; HEAD `bcdf4a7` |
| `git diff --numstat docs/` | `architecture.md` +3/−0; `master-execution-board.md` +42/−0 |
| NajdiTrain adapter / `train_najdi_sft.py` | `c35e8832…` / `71d546e0…` (unchanged) |
| Corpus v1.0 `ORIGINAL_FILES.sha256` / `GOVERNANCE_FILES.sha256` | 34/34 / 7/7 OK |
| Migrations, generators, training, adapter deployment, Hermes / Ollama / WSL runtime changes | None performed |

## 6. Next step
None is authorized. Phase 1A needs a separate, explicit owner authorization, which would most likely start with OA-01 (W1 evidence archive) and OA-05 (loader guard).
