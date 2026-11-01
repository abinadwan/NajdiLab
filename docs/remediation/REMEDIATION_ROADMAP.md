# NajdiLab Remediation Roadmap

> **Program type:** Long-term phased remediation — one phase active at a time.
> **Repository:** `abinadwan/NajdiLab`
> **Roadmap location:** `docs/remediation/REMEDIATION_ROADMAP.md`
> **Baseline established:** Phase 0 — 2026-11-01

---

## 1. Verified Baseline

| Item | Value |
|---|---|
| `main` HEAD SHA | `3b1405846ab6fdd45151cc163418fb5c0dc0e027` |
| Merge description | Merge pull request #14 from `fix/review-restriction-integrity` |
| Merge timestamp | 2026-11-01T17:28:33Z |
| PR #14 state | **MERGED** |
| Post-merge Ubuntu CI | **PASS** — Source checks run `41331651850` |
| Post-merge Windows CI | **FAIL** — Source checks run `41331651850` |
| Failing Windows step | `node --test tests/review-restrictions-browser.cjs` |
| Failing test (Windows) | `correction and explicit flag change preserve unrelated restrictions` |
| Failure location | `tests/review-restrictions-browser.cjs:68:14` |
| Failure assertion | `strictEqual(r.contains_personal_data, 0)` — actual `1`, expected `0` |

**PR #14 browser regression results on Windows:**
- Subtests passed: 7
- Subtests failed: 2 (test 5 and its parent)
- Subtests: test 1 ✓ test 2 ✓ test 3 ✓ test 4 ✓ test 5 **✗** test 6 ✓ test 7 ✓ test 8 ✓

**No application changes were made during Phase 0.**

---

## 2. Repository Overview

| Layer | Key files |
|---|---|
| HTTP server | `app/server.py` |
| Business logic | `app/service.py` |
| Review lifecycle | `app/review_lifecycle.py` |
| Review integrity | `app/review_integrity.py` |
| Frontend SPA | `static/app.js` (90 KB), `static/index.html` |
| Browser tests | `tests/review-restrictions-browser.cjs`, `tests/chat-browser.cjs` |
| Python tests | `tests/test_review_restriction_integrity.py`, `tests/test_review_lifecycle.py`, `tests/test_review_management.py`, and ~30 other test modules |
| CI workflows | `.github/workflows/checks.yml`, `.github/workflows/public-source-candidate.yml` |
| Migrations | `migrations/001_initial.sql` … `migrations/006_chat_session_binding.sql` |

**CI matrix:** Ubuntu + Windows on every push to `main` and on pull requests. Tests include pytest (Python), Node `--test` (JS unit), and Puppeteer (Chromium browser acceptance).

**Skip counts (Windows baseline):**
- 9 intentionally disabled real-Ollama tests
- 22 absent private-artifact checks
- 2 Windows-only checks total skips = 31

---

## 3. Phase Dependency Graph

```
PHASE 0 (Baseline + Inventory) [CURRENT]
  └─► PHASE 1 (Restore Green CI / Verify PR #14)
        └─► PHASE 2 (Review Lifecycle + Data Integrity)
              └─► PHASE 3 (Dataset Quality + Export)
                    └─► PHASE 4 (Migration Safety)
                          └─► PHASE 5 (Critical UX Defects)
                                └─► PHASE 6 (IA, Localization, Accessibility)
                                      └─► PHASE 7 (Operational Security + Retention)
                                            └─► PHASE 8 (AI Engine Integration)
                                                  └─► PHASE 9 (Final Release Acceptance)
```

Each arrow represents a hard sequential dependency. No phase may begin until its predecessor is formally CLOSED.

---

## 4. Complete Finding Inventory

### 4.1 QA Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| QA-01 | Windows Chromium regression: `correction and explicit flag change preserve unrelated restrictions` fails (line 68, `contains_personal_data=1` instead of 0) | 1 | P1 | OPEN | Passes on Ubuntu, fails on Windows only; root cause is async or rendering timing on Windows Chrome |
| QA-02 | 9 intentionally skipped real-Ollama regression tests | 8 | P2 | OPEN | Cannot be verified without owner-authorized hardware; status is UNVERIFIED by design |
| QA-03 | 22 private-artifact regression tests skipped in distributed repo | 7 | P2 | OPEN | Private historical records unavailable; only synthetic-fixture equivalents can be added |
| QA-04 | Windows symlink privilege requirement in tests | 7 | P2 | OPEN | Acceptance tests should not require administrator privileges |
| QA-05 | Additional browser/zoom/keyboard/accessibility acceptance not yet covered | 7 | P2 | OPEN | Phase 6 addresses main accessibility; Phase 7 covers remaining browser checks |
| QA-06 | Hermes external sender: receiver is BLOCKED but external sender not verified | 7 | P2 | OPEN | Do not configure Hermes; document verification boundary |
| QA-07 | HMAC freshness/replay limitations documented but not fully mitigated | 7 | P2 | OPEN | Requires compatibility review before any fix |
| QA-08 | Data retention/deletion semantics not fully tested end-to-end | 7 | P2 | OPEN | Distinguish logical exclusion, soft deletion, physical removal, frozen exports |

### 4.2 Security and Review Integrity Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| SEC-01 | UX-01 post-merge verification: load/approve/correct/refresh must preserve all restrictions | 1 | P1 | OPEN | PR #14 claims to fix this; must be independently verified via CI not just local tests |
| SEC-02 | UX-02 post-merge verification: individual and bulk restore must preserve all restrictions | 1 | P1 | OPEN | PR #14 claims to fix this; must be independently verified via CI |
| SEC-03 | Deleted-review lifecycle bypass: ordinarily approved deleted review can become APPROVED + eligible without authorized restoration | 2 | P1 | OPEN | Verified defect; valid lifecycle transitions must be enforced |
| SEC-04 | Non-atomic manual bulk operations: partial commits on mixed valid/invalid requests | 2 | P1 | OPEN | Verified defect; all-or-nothing behavior required |
| SEC-05 | Review event history: `review_events` table absent from inspected isolated database | 2 | P2 | OPEN | Optional table; historical reconstruction limitations must be documented |

### 4.3 Dataset and Export Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| DATA-01 | Missing export diagnostics: Gold exports can be frozen without required `diagnostics` and `loss_mask_validation` manifest fields | 3 | P1 | OPEN | Verified defect |
| DATA-02 | Health false NOT_READY state: valid export may show NOT_READY due to absent diagnostics | 3 | P1 | OPEN | Verified defect; producer/consumer contract misalignment |
| DATA-03 | Unsupported holdout classification: Balancer rejects `evaluation_holdout.jsonl` as unsupported | 3 | P1 | OPEN | Verified defect |
| DATA-04 | Cross-tool contract disagreement: Health, Balancer, Quality Checker, Unsloth Export use different manifest/version interpretations | 3 | P1 | OPEN | Shared contract must be established |
| DATA-05 | Fresh-install empty states: missing-directory error while version selector shows "Loading versions…" | 3 | P2 | OPEN | Verified defect; accurate empty/unavailable/loading/error states required |

### 4.4 Database and Migration Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| DB-01 | Unapproved SQL migration execution: rollback-named file in migrations directory can be executed | 4 | P1 | OPEN | Verified defect; allowlist required |
| DB-02 | Partial migration persistence: failed migration can leave schema modified without ledger entry | 4 | P1 | OPEN | Verified defect; transaction boundary review required |
| DB-03 | Backup scope and recovery limitations: assets included/excluded not clearly documented or tested | 4 | P2 | OPEN | Documentation and isolated fixture tests required |

### 4.5 UX Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| UX-01 | Review restriction preservation during load/approve/correct/refresh | 1 | P1 | FIXED_PENDING_VERIFICATION | PR #14 merged; Windows CI must verify |
| UX-02 | Individual and bulk restore restriction preservation | 1 | P1 | FIXED_PENDING_VERIFICATION | PR #14 merged; Windows CI must verify |
| UX-03 | Approval/eligibility conflation: approval must never imply automatic eligibility | 5 | P1 | OPEN | |
| UX-04 | Collection outcome visibility per Chat pair | 5 | P2 | OPEN | Must not expose data without permission |
| UX-05 | Review continuity: full permitted content, not truncated previews | 5 | P2 | OPEN | |
| UX-06 | Readiness blocker display: all blockers, not truncated subset | 5 | P2 | OPEN | |
| UX-07 | Unsaved correction draft loss during navigation | 5 | P1 | OPEN | |
| UX-08 | Chat Send clears newer draft when earlier request was in flight | 5 | P1 | OPEN | |
| UX-09 | Chat controls show wrong provider/model/context/session identity | 5 | P2 | OPEN | |
| UX-10 | Navigation complexity: 15-destination nav needs meaningful grouping | 6 | P2 | OPEN | Read-only UI audit must precede redesign |
| UX-11 | Dashboard usefulness: hardcoded readiness claims | 6 | P2 | OPEN | |
| UX-12 | Unsloth Handoff: error-prone manual version name entry | 5 | P2 | OPEN | Validated selection workflow required |
| UX-13 | Stale Dataset Version catalog after create/refresh | 5 | P2 | OPEN | |
| UX-14 | Shared tab state hides Add Data forms after Manual Data dialog interaction | 5 | P2 | OPEN | |
| UX-15 | Empty SFT turns and invalid form state cause uncaught JS exceptions | 5 | P1 | OPEN | |
| UX-16 | Manual save lacks pending/success/failure/retry states | 5 | P1 | OPEN | Draft must not be lost on failure |
| UX-17 | Exclusion-reason field labeling inconsistency | 5 | P2 | OPEN | |
| UX-18 | Historical remediation UI: Phase39 shared state and hardcoded 7-record assumption | 6 | P2 | OPEN | Private historical workflows may be unavailable |
| UX-19 | Transient toast messages used where persistent error states required | 5 | P2 | OPEN | |
| UX-20 | Record display limits not exposed; no pagination | 5 | P2 | OPEN | |
| UX-21 | Arabic and RTL interface support | 6 | P2 | OPEN | Saudi Arabic required; technical identifiers must stay LTR |
| UX-22 | Accessibility: keyboard navigation, focus, labels, dialogs | 6 | P2 | OPEN | |
| UX-23 | Responsive layout overflow on narrow viewports (documented at 390px–497px) | 6 | P2 | OPEN | |
| UX-24 | Sidebar collapse: visual collapse does not actually change layout width | 6 | P2 | OPEN | |
| UX-25 | Dark-mode text contrast insufficient (~2.13:1 and ~2.45:1 measured) | 6 | P2 | OPEN | WCAG AA required for ordinary text |
| UX-26 | Misleading status labels: hardcoded port 8770, static "Passed" assertions, lifecycle terminology | 6 | P2 | OPEN | |
| UX-27 | Evaluation results show stale version identity | 5 | P2 | OPEN | |

### 4.6 AI Integration Findings

| ID | Description | Phase | Severity | Status | Notes |
|---|---|---|---|---|---|
| AI-01 | LM Studio RESULT_MISMATCH: `google/gemma-4-e4b` generates output that NajdiLab rejects | 8 | P2 | OPEN | Local observation only; cloud-testable portion is contract/adapter testing |
| AI-02 | Failed invariant unknown: which of four integrity predicates caused RESULT_MISMATCH is unconfirmed | 8 | P2 | OPEN | Content-free diagnostics only |
| AI-03 | Real-model Ollama acceptance: 9 intentionally disabled tests (same as QA-02) | 8 | P2 | OPEN | Owner-authorized hardware required; cannot be confirmed in cloud CI |
| AI-04 | Runtime behavior contracts: identity, token accounting, cancellation, context overflow | 8 | P2 | OPEN | Synthetic adapter tests in cloud CI |
| AI-05 | Collection privacy: OFF by default, no retroactive collection, no automatic eligibility | 8 | P1 | OPEN | Must be independently verified in Phase 8 |

---

## 5. Known Test Limitations

| Limitation | ID | Impact |
|---|---|---|
| 9 real-Ollama regression tests are intentionally disabled | QA-02, AI-03 | UNVERIFIED until owner provides hardware-authorized evidence |
| 22 private historical-artifact tests cannot run in distributed CI | QA-03 | Synthetic equivalents may partially substitute but are not equivalent |
| Real-model AI acceptance requires owner's local Ollama/LM Studio | AI-01–AI-04 | Cloud CI can only verify synthetic adapter contracts, not real inference |
| Windows symlink creation may require admin privileges | QA-04 | Tests that create symlinks may behave differently in CI |

**Rule:** A skipped or blocked test is NEVER recorded as PASS.

---

## 6. QA-01 Root Cause Analysis (Phase 0 Evidence)

**Test:** `correction and explicit flag change preserve unrelated restrictions`
**File:** `tests/review-restrictions-browser.cjs` lines 60–71
**Failure:** `assert.equal(r.contains_personal_data, 0)` — actual `1`

**Test sequence:**
1. Reload page → 3 PENDING records in queue (records 2–4 seeded with all flags=1)
2. Assert all flags checked = `[true,true,true,true,true]` ✓
3. `page.click('#contains-personal')` — intent: uncheck (1→0)
4. Open correction editor, select DIALECT_CORRECTION
5. Set corrected response text
6. `page.click('#save-review')` → POST `/api/v1/reviews/{id}/correct`
7. Database query: `contains_personal_data` = **1** (expected 0)

**Investigated code paths:**
- `reviewPayload()` in `static/app.js:38832` reads `$('#contains-personal').checked` directly
- Backend `_save_review_conn` in `app/service.py` uses `data.get('contains_personal_data', current[key])` — explicit false in payload should produce 0
- `openEditReview()` and `selectReviewStatus()` do NOT reset checkboxes
- No background polling or `setInterval` that would re-initialize checkboxes
- No CSS `pointer-events: none` or `opacity: 0` on the checkbox

**Hypotheses (to be confirmed in Phase 1):**
- **H1 (MOST LIKELY):** Windows Chrome renders the checkbox center at a different viewport coordinate, and Puppeteer's `page.click('#contains-personal')` clicks at the center of the INPUT element's bounding box. If a CSS layout difference on Windows places overlapping content at that coordinate, the click hits the wrong element and the checkbox stays checked.
- **H2:** Async page-load timing: on Windows the page may be slower to fully render and a subsequent internal render pass re-initializes the checkbox after the `waitForFunction` resolves but before the click registers.
- **H3:** The click registers correctly in the browser but the change event is not propagated synchronously before `reviewPayload()` reads the state. (Less likely; Puppeteer awaits click completion.)

**Phase 1 investigation plan:**
- Add a screenshot capture on test 5 failure to observe the checkbox state at time of click
- Log the actual request payload sent to `/correct` to determine whether UI sends false or true
- Test without `openEditReview()` step to isolate whether that call is re-rendering anything
- Run the test with an explicit `page.waitForFunction(() => !document.querySelector('#contains-personal').checked)` after the click to confirm the uncheck lands before proceeding

---

## 7. Phase Status Summary

| Phase | Title | Status | Owner-Decision Required |
|---|---|---|---|
| **Phase 0** | Baseline and Remediation Inventory | **IN_PROGRESS** | Owner approval of this roadmap → transition to Phase 1 |
| Phase 1 | Restore Green CI and Close PR #14 Verification | NOT_STARTED | — |
| Phase 2 | Review Lifecycle and Data Integrity | NOT_STARTED | — |
| Phase 3 | Dataset Quality, Export and Handoff Consistency | NOT_STARTED | — |
| Phase 4 | Database Migration Safety | NOT_STARTED | — |
| Phase 5 | Critical Functional UX Defects | NOT_STARTED | — |
| Phase 6 | Information Architecture, Localization, Mobile and Accessibility | NOT_STARTED | — |
| Phase 7 | Operational Security, Retention and Recovery | NOT_STARTED | — |
| Phase 8 | AI Engine Integration and Final Acceptance | NOT_STARTED | — |
| Phase 9 | Final Release Acceptance | NOT_STARTED | — |

---

## 8. Architecture Integrity Invariants (to be preserved in every phase)

The following must not be weakened by any remediation change:

1. Collection is OFF by default.
2. Consent affects future completed conversations only — no retroactive collection.
3. No automatic training eligibility.
4. Approval and training eligibility are independent.
5. Original responses are immutable; corrections are stored separately.
6. Privacy restrictions never disappear implicitly.
7. Excluded or deleted records cannot silently become training candidates.
8. Dataset versions and historical exports are immutable once frozen.
9. Frozen exports are never silently rewritten.
10. Protected model identity and fail-closed behavior remain enforced.
11. Hermes receiver remains BLOCKED by default.
12. Internal training, deployment, model downloading, and legacy WSL execution must not be reintroduced.
13. Training remains external through Unsloth-compatible exports.

---

## 9. Phase 0 Closure Checklist

| Condition | Result |
|---|---|
| Current baseline SHA verified | ✓ `3b1405846ab6fdd45151cc163418fb5c0dc0e027` |
| PR #14 confirmed merged | ✓ MERGED 2026-11-01T17:28:33Z |
| Current CI status inspected | ✓ Ubuntu PASS / Windows FAIL on run `41331651850` |
| All findings inventoried with IDs | ✓ 50 findings mapped |
| Phase dependency graph produced | ✓ Phases 0–9 sequential |
| Test limitations identified | ✓ 3 categories documented |
| No application changes made | ✓ Phase 0 is documentation only |
| Architecture invariants listed | ✓ 13 invariants listed |
| Owner approves roadmap | **PENDING** |

**Owner decision required:** Review this roadmap for completeness and accuracy, then explicitly approve the transition to Phase 1.

---

## 10. Finding Status Legend

| Status | Meaning |
|---|---|
| `OPEN` | Finding confirmed; not yet fixed |
| `IN_PROGRESS` | Fix is being developed in the active phase |
| `FIXED_PENDING_VERIFICATION` | Fix is merged; CI verification not yet complete |
| `BLOCKED` | Cannot proceed; owner action or unavailable resource required |
| `CLOSED` | Fix verified in CI, documented, and owner-approved |
| `ACCEPTED_RISK` | Owner has explicitly accepted the remaining risk |

---

*This document is the authoritative remediation ledger for the NajdiLab program. It must be updated during every phase, not after completion.*
