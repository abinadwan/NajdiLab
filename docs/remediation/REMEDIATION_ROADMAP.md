# NajdiLab Remediation Roadmap

> **Program type:** Long-term phased remediation — one phase active at a time.
> **Repository:** `abinadwan/NajdiLab`
> **Roadmap location:** `docs/remediation/REMEDIATION_ROADMAP.md`
> **Baseline established:** Phase 0 — 2026-11-01
> **File and line references:** valid at baseline `3b1405846ab6fdd45151cc163418fb5c0dc0e027`.

---

## 1. Verified Baseline

| Item | Value |
|---|---|
| `main` HEAD SHA | `3b1405846ab6fdd45151cc163418fb5c0dc0e027` (unchanged since program initialization) |
| Merge description | Merge pull request #14 from `fix/review-restriction-integrity` |
| Merge timestamp | 2026-11-01T17:28:33Z |
| PR #14 state | **MERGED** |
| Post-merge `tests (ubuntu-latest)` | **PASS** — Source checks run `41331651850` |
| Post-merge `tests (windows-latest)` | **FAIL** — Source checks run `41331651850` |
| Failing Windows step | `node --test tests/review-restrictions-browser.cjs` |
| Failing test | Subtest 5, `correction and explicit flag change preserve unrelated restrictions` |
| Failure location | `tests/review-restrictions-browser.cjs:68:14` |
| Failure assertion | `assert.equal(r.contains_personal_data, 0)` in strict mode — actual `1`, expected `0` |
| Browser result | 9 tests: 7 passed, 2 failed (subtest 5 and its parent); subtests 1–4 and 6–8 passed |

**The application is not green at this baseline.** `main` has a failing required check. QA-01 stays open until Phase 1 closes it.

**No application changes were made during Phase 0.**

---

## 2. Repository Overview

| Layer | Key files |
|---|---|
| HTTP server | `app/server.py` |
| Business logic | `app/service.py` |
| Review lifecycle | `app/review_lifecycle.py` |
| Review integrity | `app/review_integrity.py` |
| Frontend SPA | `static/app.js`, `static/chat.js`, `static/index.html` |
| Browser tests | `tests/review-restrictions-browser.cjs`, `tests/chat-browser.cjs` |
| Python tests | `tests/test_review_restriction_integrity.py`, `tests/test_review_lifecycle.py`, `tests/test_review_management.py`, and the other modules under `tests/` |
| CI workflows | `.github/workflows/checks.yml` (push to `main`, pull requests), `.github/workflows/public-source-candidate.yml` (pull requests only) |
| Migrations | `migrations/001_initial.sql` … `migrations/007_review_events.sql` |

### 2.1 Skipped tests

**Windows application skip inventory: 32** (`docs/cleanup-results.md:40`).

| Category | Count | Finding | Source |
|---|---|---|---|
| Real-Ollama opt-in checks | 9 | QA-02 | `tests/test_chat_ollama_real.py`; requires `NAJDILAB_DISPOSABLE_OLLAMA=1` |
| Private historical-artifact checks | 22 | QA-03 | `tests/test_dataset_balancer.py`, `tests/test_dataset_platform.py`, `tests/test_phase310_gates.py`, `tests/test_phase38_dataset.py`, `tests/test_phase38_ui.py`, `tests/test_phase39_api.py`, `tests/test_phase39_edits.py`, `tests/test_phase39_mt06_repair.py` |
| Symlink-capability check | 1 | QA-04 | `tests/test_integrations.py:201`; skips at `:207` when the Windows account cannot create symlinks |
| **Total** | **32** | | |

**Exact hosted CI counts.** The symlink skip is conditional and did not fire on hosted Windows, so hosted runs report 31 (`docs/verification-evidence.md:42`). This means hosted CI does not exercise the symlink-unavailable path that QA-04 covers.

| Run | Windows | Ubuntu |
|---|---|---|
| `41331651850` (`main`) | 448 passed, 31 skipped, 59 subtests passed | 446 passed, 33 skipped, 59 subtests passed |
| `41334507091` (PR #16, `126d520`) | 448 passed, 31 skipped, 59 subtests passed | 446 passed, 33 skipped, 59 subtests passed |

Ubuntu's 33 are the same 9 + 22 plus two Windows-only checks: the PowerShell launcher check and the drive-type boundary at `tests/test_integrations.py:333`.

**Rule:** A skipped or blocked test is NEVER recorded as PASS.

---

## 3. Phase Dependency Graph

```
PHASE 0 (Baseline + Inventory) [CLOSED]
  └─► PHASE 1 (Restore Green CI / Verify PR #14) [CLOSED]
        └─► PHASE A (Security, Dataset Quality, Migration Safety) [IN_PROGRESS]
              └─► PHASE B (UX, Bilingual Support, Operational Security)
                    └─► PHASE C (AI Integration + Final Release Acceptance)
```

Each arrow represents a hard sequential dependency. No phase may begin until its predecessor is formally CLOSED.

**Consolidated PR delivery:** one feature branch → all findings in that phase → one PR → one owner merge approval. No intermediate PRs.

### 3.1 Legacy phase mapping

| Consolidated Phase | Legacy Phases | Finding IDs |
|---|---|---|
| Phase A | Phases 2 + 3 + 4 | SEC-03, SEC-04, SEC-05, DATA-01–05, DB-01–03 (11 findings) |
| Phase B | Phases 5 + 6 + 7 | UX-03–UX-27, QA-03–08 (mandatory full bilingual Arabic RTL + English LTR, persistent language selector, complete localization, accessibility, operational security) |
| Phase C | Phases 8 + 9 | QA-02, AI-01–05 (six original findings; preparatory source-only work in stacked Draft PR #20, real-model acceptance still blocked) |

---

## 4. Complete Finding Inventory

### 4.0 Totals

**53 unique finding IDs**, the exact set listed in the program's audit-ID coverage requirements. No IDs were added or removed.

| Family | Count |
|---|---|
| QA-01 – QA-08 | 8 |
| SEC-01 – SEC-05 | 5 |
| DATA-01 – DATA-05 | 5 |
| DB-01 – DB-03 | 3 |
| UX-01 – UX-27 | 27 |
| AI-01 – AI-05 | 5 |
| **Total** | **53** |

| Phase | Findings | IDs |
|---|---|---|
| 0 | 0 | — |
| 1 | 5 | QA-01, SEC-01, SEC-02, UX-01, UX-02 |
| **A** | **11** | **SEC-03, SEC-04, SEC-05, DATA-01–05, DB-01–03** |
| B | 31 | UX-03–UX-27 (25), QA-03–QA-08 (6) |
| C | 6 | QA-02, AI-01–AI-05 |
| **Total** | **53** | Each ID appears in exactly one phase |

> **Note:** All 53 finding IDs are preserved exactly. Legacy phase numbers (2–9) are superseded by consolidated Phase A/B/C. The legacy-to-consolidated mapping is in Section 3.1.

### 4.1 Verification classification

| Classification | Meaning | Count | IDs |
|---|---|---|---|
| **VERIFIED** (verified defect) | Observed in CI, or stated as verified, reproduced, or measured in the audit | 11 | QA-01, SEC-03, SEC-04, DATA-01, DATA-02, DATA-03, DATA-05, DB-01, DB-02, UX-23, UX-25 |
| **PARTIALLY VERIFIED** | Some evidence exists, but it does not cover the full finding | 5 | SEC-01, SEC-02, UX-01, UX-02, AI-01 |
| **SOURCE-SUPPORTED** (source-supported risk) | Phase 0 located code or documentation consistent with the finding; the behavior was not run | 20 | QA-07, SEC-05, DATA-04, UX-04, UX-06, UX-07, UX-08, UX-10, UX-11, UX-12, UX-14, UX-15, UX-16, UX-17, UX-18, UX-19, UX-20, UX-21, UX-24, UX-26 |
| **NOT TESTED** (untested requirement) | No acceptance evidence exists yet, and Phase 0 found nothing decisive in source | 17 | QA-02, QA-03, QA-04, QA-05, QA-06, QA-08, DB-03, UX-03, UX-05, UX-09, UX-13, UX-22, UX-27, AI-02, AI-03, AI-04, AI-05 |
| **Total** | | **53** | |

**Limits of these labels:**
- "Audit" below means the finding's own text in the remediation program. Phase 0 did not re-run those reproductions. `main` is unchanged since the audit baseline, so nothing has been fixed since then.
- SOURCE-SUPPORTED is not a confirmed defect. Each phase must reproduce the finding before fixing it.
- Severity values are proposed by this roadmap for owner review. The audit did not assign P1/P2 per finding.
- As of Phase 0, none of the 53 has a related GitHub Issue, and only UX-01 and UX-02 have a fix PR (#14). Remaining-risk and closure fields are completed in each finding's phase.

### 4.2 QA Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| QA-01 | Windows Chromium regression: `contains_personal_data` stays `1` after explicit uncheck | 1 | P1 | **FIXED** | VERIFIED | Root cause confirmed H2. Fix in `static/app.js:init()`. PR #17 merged to `main` as SHA `812f28f`. Post-merge CI run `41346905426`: Windows PASS, Ubuntu PASS. |
| QA-02 | 9 real-Ollama regression tests intentionally skipped | 8 | P2 | **BLOCKED** | NOT TESTED | `tests/test_chat_ollama_real.py`; unverified until genuine acceptance evidence exists. Phase C: acceptance plan prepared (disposable `ollama` on a private port, synthetic tiny model, 9 passed / 0 skipped required) — **not executed**; needs Phase B closure and owner authorization. See PHASE_C_IMPLEMENTATION.md Increment 5. |
| QA-03 | 22 regression tests need private historical artifacts | 7 | P2 | **BLOCKED** | NOT TESTED | Inventory re-measured 2026-11-02 from `pytest -rs`: exactly 22 skips declare private, undistributed prerequisites (v009 remediation draft, v007/v008 exports, Phase 3.8/3.9 reports, fresh holdout). They cannot run in cloud CI and must not be recreated synthetically. Unblock: an authorized maintainer restores verified private copies to the ignored paths and runs the suite locally. Other skips are separate: 9 need a disposable real Ollama (`NAJDILAB_DISPOSABLE_OLLAMA=1`), 2 are Windows-only, and 4 need the `lmstudio` package (installed in CI, absent in this container). |
| QA-04 | Safe behavior when symlink creation is unavailable | 7 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Real-link tests skip where accounts cannot create symlinks, leaving the refusal unproven there. `tests/test_qa04_symlink_unavailable.py` (12) simulates link metadata so the refusal runs on every platform: symlinked marker, symlinked parent, Windows junction (reparse point — previously unreachable on Linux), file marker, unreadable metadata, network/unknown filesystem, discovery result, and the source-candidate builder refusing symlinked sources and output parents. Mutation check: removing the junction check fails the test. No product code changed. |
| QA-05 | Additional browser, zoom, keyboard and accessibility acceptance | 7 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | PARTIALLY VERIFIED | Chromium acceptance added: keyboard and accessibility checks (see UX-22), reflow without page-level horizontal scrolling at 640 px (200% zoom) and 320 px (400% zoom) in English and Arabic — 320 px first failed on Analytics, Reviewed and Settings and was fixed (panel-scrolled data table, `min()` card grid, stacked settings cards); 390 px mobile in both directions (`i18n-browser.cjs`). Additional browsers are **BLOCKED** in this environment (only Chromium installed); screen-reader output **NOT VERIFIED**. |
| QA-06 | Hermes receiver is BLOCKED, but external sender disconnect is unproven | 7 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** (evidence only) | NOT VERIFIED | Still not provable from NajdiLab: the external sender is outside it and is not inspected or changed. Added local evidence: `GET /api/v1/hermes-hook/refusals` counts refused deliveries to the blocked hook since process start (count, last time; nothing from the request stored; refusal still before reading the body); not shown in Settings, which no longer lists Hermes. Tests: `tests/test_qa06_hermes_refusals.py` (3). Owner verification procedure in `docs/hermes-integration.md`. External disconnect itself remains **NOT VERIFIED** until the owner runs that procedure on their machine. |
| QA-07 | HMAC freshness and replay limitations | 7 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Body-only HMAC and bearer tokens allowed indefinite replay (duplicate turns when no `source_message_id`). Added an opt-in timestamped signature (`X-NajdiLab-Timestamp`, signature over `timestamp.body`): ±300 s window, replay of an accepted signature → 409 `INGEST_REPLAY`, only valid signatures recorded. Existing senders unchanged; `NAJDILAB_REQUIRE_FRESH_SIGNATURE=1` makes it mandatory. Tests: `tests/test_qa07_signed_freshness.py` (19 incl. HTTP replay never reaching ingestion); existing ingest/security tests unchanged. Limits: replay record is in memory (window still bounds it after restart); clock sync required; bearer mode cannot be made fresh. |
| QA-08 | Retention and deletion semantics | 7 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** (logical retention scope approved; erasure deferred) | VERIFIED | `tests/test_qa08_retention.py` (3) proves end to end: exclusion, restoration and soft deletion change training selection and new training files only; text, audit events, earlier exports, backups and the **full archive of every new export** keep the content; hard deletion of an audited review is refused. Documented in `docs/data-retention.md`. Owner decision 2026-11-02: Phase B retains logical delete/exclude/archive and audit preservation; physical erasure is **out of Phase B scope** and requires a separately authorized future feature covering frozen exports and backups. The existing semantics remain pending hosted acceptance; no final PASS is claimed. |

### 4.3 Security and Review Integrity Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| SEC-01 | Verify UX-01: load, approve, correct, refresh, concurrency and failed requests preserve restrictions; explicit edits still work | 1 | P1 | **FIXED** | PARTIALLY VERIFIED | 31 Python tests pass; 10/10 browser subtests pass. PR #17 merged SHA `812f28f`. Post-merge CI run `41346905426`: Windows PASS, Ubuntu PASS. |
| SEC-02 | Verify UX-02: individual and bulk restore preserve restrictions | 1 | P1 | **FIXED** | PARTIALLY VERIFIED | Python tests + browser subtests 7–8 pass. PR #17 merged SHA `812f28f`. Post-merge CI run `41346905426`: Windows PASS, Ubuntu PASS. |
| SEC-03 | Deleted review can reach APPROVED and eligible without restoration | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | `_save_review_conn` calls `validate_transition` before the UPDATE, independent of `review_events`. Review corrections: proved on the original no-event-table path; decision self-transitions (re-saving with edited text or restriction flags) are now allowed and audited — without this, 007 would have blocked marking an approved review as personal data. IGNORED/DELETED still require restoration. Tests: `test_sec03_*` in `tests/test_phase_a_regressions.py`; candidate review suite 78/78. |
| SEC-04 | Non-atomic manual bulk operations can partially commit | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Whole request validated before the transaction (non-dict item, unknown type, invalid id are rejected — not skipped); more than 500 items is rejected, not truncated; all updates and `manual_data_versions` rows share one transaction. Tests: `test_sec04_*` (intermediate-failure rollback of records and versions, malformed items, 501-item batch). |
| SEC-05 | `review_events` may be absent; historical reconstruction is limited | A | P2 | **FIXED_PENDING_VERIFICATION** | VERIFIED | `migrations/007_review_events.sql` creates immutable `review_events` and a one-row immutable `review_event_baseline` (highest pre-upgrade `reviews.id`; ids are AUTOINCREMENT). No events are fabricated. Legacy reviews without events → `REVIEW_HISTORY_UNVERIFIABLE` (warning); post-upgrade reviews without events → `REVIEW_EVENT_MISSING` (blocking); event conflicts block; missing baseline fails closed. Tests cover a 001–006 database upgraded to 007 with legacy approved/deleted/pending reviews, restoration, soft deletion, `ON DELETE RESTRICT`. Residual: pre-007 transition history remains unverifiable; the Core profile (001–004) does not ship 007. |

### 4.4 Dataset and Export Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| DATA-01 | Gold exports can freeze without `diagnostics` and `loss_mask_validation` | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Re-checked against the original finding: freeze already enforced diagnostics and loss-mask metadata, but zero training records satisfied every comparison; now refused. End-to-end through derive → freeze: the Frozen manifest carries matching diagnostics (artifact hashes, fingerprint) and loss-mask totals; freeze is refused, and the version stays Draft, when either is missing or stale; regeneration makes freeze possible. Tests: `test_data01_*` in `tests/test_phase_a_dataset_acceptance.py`. |
| DATA-02 | Valid export may show NOT_READY because diagnostics are absent | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | A valid derived Draft reports READY with valid diagnostics; a Draft without diagnostics stays NOT_READY (intentional, fail-closed) with an actionable “not been generated (run Regenerate Diagnostics first)” reason distinct from “stale”; state-less legacy versions are not downgraded. Tests: `test_data02_*`. |
| DATA-03 | Balancer reports `evaluation_holdout.jsonl` as unsupported | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Balancer evaluation files come from `dataset_platform.EVAL_FILES`; a version containing `evaluation_holdout.jsonl` produces no `UNSUPPORTED_RECORDS`. Tests: `test_data03_*`, `test_data04_holdout_and_native_files_are_supported_by_balancer_and_quality`. |
| DATA-04 | Health, Balancer, Quality Checker and Unsloth Export lack one shared contract | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Quality and Unsloth export already imported the platform constants; Balancer was the divergent module. It now also supports `native_tool_use.jsonl` (Health counts it as training; Balancer previously raised an error-level `UNSUPPORTED_RECORDS`). Tests assert identity of the shared constants across all four consumers and that genuinely unknown files are still reported. |
| DATA-05 | Missing-directory error alongside "Loading versions…" | A | P2 | **FIXED_PENDING_VERIFICATION** | VERIFIED | `_exports_root` creates a missing exports directory. On a fresh installation `GET /api/v1/dataset-versions` returns 200 `{"items": []}`, and the UI's existing empty branch shows “No dataset versions are available to check.” Tests: `test_data05_*` (HTTP-level). The browser rendering of the empty state is source-asserted, not browser-executed. |

### 4.5 Database and Migration Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| DB-01 | Rollback-named SQL file can be executed by the migration loader | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Explicit approval registry: only migrations listed in `migrations/registry.json`, with matching normalized SHA-256, ever run; unregistered files (including validly named ones such as `099_add_labels.sql`) are never read. A changed, missing or malformed registered entry stops startup before the database is touched; tampering with an already-applied file is detected. The Core candidate ships its own 001–004 registry. Tests: `test_db01_*` (unregistered files, tampering, missing file, invalid registry, CRLF checkout, registry ↔ inventory hashes). |
| DB-02 | Failed migration can leave schema changed with no ledger entry | A | P1 | **FIXED_PENDING_VERIFICATION** | VERIFIED | Second review reproduced an inline-`COMMIT` bypass of the line-based parser. Replaced with statement splitting via `sqlite3.complete_statement` (strings, comments and trigger bodies are respected). Any transaction-control statement other than one leading `BEGIN` and one final `COMMIT` — plus `ATTACH`, `DETACH`, `VACUUM`, body `PRAGMA`s — is refused before any pending migration runs. The loader executes each statement inside its own `BEGIN IMMEDIATE` and writes the ledger row as a parameter before `COMMIT`. Tests: exact review reproduction, 19 rejected forms, runtime/constraint/syntax failures roll back schema, data and ledger, retry, incremental application of 001–007. |
| DB-03 | Backup scope and recovery boundary | A | P2 | **FIXED_PENDING_VERIFICATION** | VERIFIED | `backup_db()` is now the single snapshot implementation used by `scripts/backup.py` (read-only source, `integrity_check`, never overwrites, never creates a missing source). Tests prove the project ZIP contains review events, baseline and frozen exports, and that restoring a verified backup recovers audit history. Docs: pre-upgrade backup is the only rollback for 007; dropping `review_events` is explicitly prohibited. |

### 4.6 UX Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| UX-01 | Review restriction preservation | 1 | P1 | **FIXED** | VERIFIED | PR #17 merged (SHA `812f28f`). Post-merge CI `41346905426` green. |
| UX-02 | Individual and bulk restoration restriction preservation | 1 | P1 | **FIXED** | VERIFIED | PR #17 merged (SHA `812f28f`). Post-merge CI `41346905426` green. |
| UX-03 | Distinguish approval from training eligibility | 5 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** | NOT TESTED | Review UI now explicitly explains that human approval differs from separate dataset eligibility; checkbox is described to assistive technology and existing backend restrictions remain authoritative. Existing browser test asserts approved restricted data stays training-ineligible, plus UI explanation test. Full a11y/localization acceptance pending. |
| UX-04 | Collection outcome per completed Chat pair | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Chat replies now render their own collected/not-collected outcome using the server's per-turn collected flag; completed pairs remain subject to human review. Node and hosted-browser acceptance added; final CI pending. |
| UX-05 | Continuity and complete permitted content | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | No written definition beyond the title was found, so the requirement was taken from it and checked in code. Continuity already held: `_message_context` returns every message from the first turn through the reviewed response, in order, unbounded, and the review screen renders it in full — now proven by test. Gap fixed: Reviewed cards (original and saved correction, cut at 220 characters) and Dataset records (cut at 180) had no way to show the rest; a shared `fullText()` keeps the preview and adds a native "Show full text" disclosure with the exact stored text. Dataset records also show origin/language labels and isolate domain/model identifiers. Also fixed: reviewer-identity menu widened the page at 320 px. Test: UX-05 subtest in `tests/a11y-browser.cjs` (4-turn conversation, ~600-character reply: context complete and ordered via API and on screen; full text identical in Reviewed and Dataset records; disclosure opens from the keyboard). |
| UX-06 | All readiness blockers shown | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Export readiness now displays all blocking findings in a persistent numbered list with escaped user-derived text, not top three; hosted browser fixture with five blockers added; final CI pending. |
| UX-07 | Unsaved correction draft loss during navigation | 5 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Review UI now snapshots correction text, notes, reviewer identity, restriction flags, tags and exclusion reason; navigation, queue refresh and unload guard unsaved edits. Chromium cancel/discard regression added. Its first version always failed in CI (wrong restored-value assumption, unhandled `beforeunload`/`confirm` guards); corrected 2026-11-02 to assert the restored server value and each guard prompt — 11/11 locally on Linux, hosted Windows/Ubuntu run pending. |
| UX-08 | Completed Send clears a newer draft | 5 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Only the exact submitted draft is cleared on a COMPLETED reply; later typing is preserved. Unit and delayed synthetic browser regression added; final CI pending. |
| UX-09 | Chat controls reflect correct provider, model, context and session | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | NOT TESTED | Chat distinguishes new-session selectors from a pinned saved session, shows immutable provider/model/context/ID/status, and disables Send if the original runtime/model is not connected/selected. Synthetic browser coverage added; final acceptance pending. |
| UX-10 | 15-destination navigation needs grouping | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Read-only audit first found: one "Dataset" group held 9 of 15 items; group labels were plain spans with no semantics; icons were read as names; no `aria-current`; in the collapsed sidebar 10 items kept visible text while 5 lost their accessible name (`display:none`). Now: all 15 destinations unchanged (same `data-view` routes) in 7 workflow-ordered groups (Overview, Chat, Review, Data entry, Datasets, Export, Administration), each a labelled `role=group`; icons `aria-hidden`; uniform labels with tooltips; `aria-current="page"`; collapsed names visually hidden but still announced; distinct sidebar/navigation landmark names. Tests: `tests/test_ux10_navigation.py` (5); existing collapse width check in `chat-browser.cjs`; Arabic labels covered by `i18n-browser.cjs`. Keyboard walk and screen-reader output pending UX-22/QA-05. |
| UX-11 | Dashboard hardcoded readiness claims | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Dashboard now labels API-returned pending and dataset-record counts as snapshots, explicitly defers export readiness to Export center and removes unsupported status claims; browser/UI inspection pending. |
| UX-12 | Manual version-name entry in Unsloth Handoff | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Unsloth handoff now uses a select populated from readable Frozen dataset versions; disabled without a valid choice. Browser acceptance incomplete; final CI pending. |
| UX-13 | Stale Dataset Version catalog | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | NOT TESTED | On entering Dataset Versions, UI requests a fresh /dataset-versions catalog and chooses only a readable version still present; stale selections no longer open nonexistent records. Synthetic Node test added; pending hosted CI/browser acceptance. |
| UX-14 | Shared tab state hides Add Data forms | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Add Data tab events are scoped to #view-add-data and no longer bind dialog tab controls. Browser fixture regression added; final CI pending. |
| UX-15 | Empty SFT turns cause uncaught exceptions | 5 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Empty/blank SFT turns are rejected with a visible error and no null .value dereference. Browser regression added; final CI pending. |
| UX-16 | Manual save lacks pending, failure and retry states | 5 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Manual edit now shows pending save, persistent failure and retry while preserving the draft; subsequent list refresh errors distinguish committed save. Browser failure/retry proof still needed; final CI pending. |
| UX-17 | Exclusion-reason labeling and validation | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Exclusion reason label now says required, matching the existing nonempty-reason validation. Accessibility/localization coverage pending. |
| UX-18 | Phase39 shared state and seven-record assumption | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Post-edit Phase39 UI no longer assumes a 7-item result; it reads server returned records, renders empty queue, preserves each record's decision, and retains retry state on write failure. Backend's historical private 7-item workflow remains intentionally unchanged. Synthetic Node acceptance, private workflow still untested. |
| UX-19 | Transient toasts where persistent errors are needed | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Actionable error toasts now persist until dismissed or replaced (role=alert / aria-live=assertive), with a keyboard-focusable dismiss button; successes retain timed status. Synthetic Chromium acceptance checks persistence beyond prior 2.8s. 2026-11-02: dismiss glyph moved out of the alert text (`aria-hidden`) so screen readers announce only the message. Broader in-context errors remain under QA review. |
| UX-20 | Record limits not exposed; no pagination | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Conversations (previously unbounded), reviewed (500), manual data (500) and saved chat sessions (200) are now server-paged: `limit` 1–500 (default 100), `offset`, and `page` metadata with total/has_more; out-of-range values return 400 instead of being clamped. Id tie-breakers keep pages free of repeats and gaps. UI shows "Showing a–b of N" with Previous/Next, corrects a page left empty by deletions, and saved sessions show "N of M loaded" with Load more. Core `list_reviewed`/`list_conversations` contracts unchanged. Tests: `tests/test_ux20_pagination.py` (23), `tests/pagination-ui.test.cjs` (5), Chromium pager assertion in `review-restrictions-browser.cjs`. Hosted Windows/Ubuntu run pending; Arabic labels pending UX-21. |
| UX-21 | Arabic and RTL interface support | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Full Arabic RTL / English LTR interface: runtime localizer (`static/localization.js`) translates rendered UI text, attributes, dynamic messages and errors from `static/i18n-ar.js`; language selector in the top bar and Settings, saved in the browser and restored on reload; immediate switching without reload, so drafts survive; RTL shell, sidebar, mobile menu; dates via `<time datetime>`. User content, identifiers and model names are never translated (`dir=auto`/`bdi`/`translate=no`); unknown server messages are labelled and isolated. Tests: `tests/i18n-catalog.test.cjs` (static coverage through the real translator), `tests/i18n-browser.cjs` (9 Chromium subtests: every view and data state free of untranslated English, verbatim user messages, RTL layout at desktop and 390px, mobile menu side, switching back, blocked storage). Not verified: real screen readers, other browsers, second-speaker review of translations; Core candidate remains English. |
| UX-22 | Keyboard, focus, labels and dialog accessibility | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Chromium accessibility-tree audit found 9 unnamed filter/sort menus (named now, plus search fields), no skip link (added), and single-key review shortcuts that fired behind an open dialog and could approve a review on a stray "4" (WCAG 2.1.4): now off by default, opt-in in Settings, never active behind a dialog or in a field/button/link, and documented. Focus indicators and image alternatives already passed. Tests: `tests/a11y-browser.cjs` (names and focus indicator in all 15 views ×2 languages, skip link, keyboard navigation, `aria-current`, collapsed names, modal focus trap/Escape/focus return, shortcut safety). Not verified: real screen readers, Firefox/WebKit. Details: `docs/accessibility.md`. |
| UX-23 | Horizontal overflow at 390px viewport | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Responsive 390px CSS constrains Add Data subtabs, review panels, filters and action buttons, leaving wide manual tables scrollable within their own panel. Chromium viewport layout assertions added; pending run. |
| UX-24 | Sidebar collapse does not change layout width | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Expanded .shell CSS previously overrode collapsed layout; explicit .shell.sidebar-collapsed desktop grid restores 76px sidebar while preserving mobile breakpoint. Chromium width regression added; final acceptance pending. |
| UX-25 | Insufficient dark-mode text contrast | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | VERIFIED | Dark mode overrides previously light-only Phase 3.8 backgrounds, metadata and label colors with high-contrast theme tokens. Chromium computed foreground/background contrast assertions added; additional visual audit pending. |
| UX-26 | Hardcoded port and static status labels | 6 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | SOURCE-SUPPORTED | Sidebar origin is rendered from current browser location.host, not hardcoded port. Settings checks the live /api/v1/health endpoint and explicitly says it does not verify database integrity/backups; browser acceptance added. |
| UX-27 | Evaluation results versus selected dataset identity | 5 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | NOT TESTED | Evaluation UI names the exact requested version, clears stale responses when the selection changes during a request, and displays failure without misleading readiness. Synthetic concurrent-response test added; pending CI. |

### 4.7 AI Integration Findings

| ID | Finding | Phase | Severity | Status | Classification | Evidence |
|---|---|---|---|---|---|---|
| AI-01 | LM Studio `RESULT_MISMATCH` for `google/gemma-4-e4b` | 8 | P2 | **OPEN — BLOCKED on owner reproduction** | PARTIALLY VERIFIED | Prior local observation only; not reproduced; nothing fixed. Phase C: pinned SDK 1.5.0 source shows `STRUCTURED_OUTPUT`/`STREAM_CONTENT` unreachable in normal operation, leaving `INSTANCE_REFERENCE`/`PROMPT_TOKEN_COUNT`; end-to-end synthetic tests (real SDK + helper + workspace) prove a named, content-free refusal that saves nothing; hypotheses and owner retest steps documented. See PHASE_C_IMPLEMENTATION.md Increment 2. |
| AI-02 | Which of four integrity predicates failed | 8 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** | NOT TESTED | Phase C `c2e642f`: four post-generation checks carry fixed, content-free identifiers over the SDK helper boundary while preserving external RESULT_MISMATCH and fail-closed behavior. Local verification found and fixed two defects: the protected-file hash pins for `app/chat_engine.py`/`app/chat_engine_worker.py` were not updated (guard test failed; re-pinned after review), and engine refusals incl. the new diagnostics lacked Arabic text (24 catalog entries + Node coverage check). Diagnostics also proven end to end through the real SDK (AI-01 tests). No real LM Studio model verification or hosted CI yet. See PHASE_C_IMPLEMENTATION.md. |
| AI-03 | Real-model Ollama acceptance | 8 | P2 | **BLOCKED** | NOT TESTED | Requires owner-authorized evidence on the owner's model and machine. Phase C: step-by-step acceptance plan with evidence and pass rules prepared — **not executed**; no model or runtime was started. See PHASE_C_IMPLEMENTATION.md Increment 5. |
| AI-04 | Runtime contracts: identity, token accounting, cancellation, context overflow | 8 | P2 | **IMPLEMENTED_PENDING_VERIFICATION** (evidence only) | NOT TESTED | Phase C: real pinned SDK + helper subprocess against a synthetic engine: identity/context/template drift refused with zero generations; full templated count + reserve admission (equal admitted, one over rolls over); `maxPredictedTokens`/`stopAtLimit` sent; non-EOS stop reasons never saved; Stop sends an SDK channel `cancel` and saves nothing. Two mutation checks fail as expected. No product code changed. Real-model behavior **NOT VERIFIED** (AI-03/QA-02). |
| AI-05 | Collection privacy | 8 | P1 | **IMPLEMENTED_PENDING_VERIFICATION** (evidence only) | NOT TESTED | Phase C: independent suite `tests/test_ai05_collection_privacy.py` (13) written from the documented contract: OFF by default and uncollected text in no review/export/archive; explicit boolean consent, never retrospective; pending pairs block exports; every restriction and archive keeps pairs out of training; planted native LM Studio/Ollama chat stores never opened (audit hook). No defect found; no product code changed. Hosted CI and owner review pending. |

---

## 5. QA-01 Evidence and Unconfirmed Hypotheses

> **Phase 1 update:** Root cause confirmed as H2. Fix applied in `static/app.js`. See below for evidence.

### 5.1 Observed evidence

| Run | Code | Windows browser step | Ubuntu browser step |
|---|---|---|---|
| `41331651850` (`main` push) | `3b14058` | **FAIL** — 7 passed, 2 failed | PASS — 9 of 9 |
| `41334507091` (PR #16) | `126d520`: `3b14058` plus one documentation file | PASS — 9 of 9 | PASS — 9 of 9 |

- **The failure is intermittent on hosted Windows.** The same application and test code both failed and passed there.
- "Fails only on Windows" is not established. Ubuntu has not failed in these runs, but the sample is too small to exclude it.
- The only recorded symptom is the persisted value. The request payload was never captured, so frontend and backend are not yet separated.

### 5.2 Test sequence

From `tests/review-restrictions-browser.cjs:60-72`:

1. Reload and wait until `#queue-position` contains `of 3` (line 61). All five fixture records were seeded with every flag set to `1`.
2. Assert all five flags are checked (line 62).
3. `page.click('#contains-personal')` to uncheck (line 63).
4. Open the editor and select `DIALECT_CORRECTION` (line 64).
5. Set the corrected text (line 65), then save and wait for `of 2` (line 66).
6. Read the saved record (line 67) and assert `contains_personal_data` is `0` (line 68). **Observed: `1`.**

### 5.3 Code paths inspected

Source facts only. None of these was observed at runtime.

- `reviewPayload()` at `static/app.js:211-213` reads `.checked` directly.
- `_save_review_conn()` at `app/service.py:496` uses `data.get(key, current[key])` at line 522, so an explicit `false` should produce `0`.
- `selectReviewStatus()` (`static/app.js:202`) and `openEditReview()` (`static/app.js:240`) do not touch the checkboxes.
- `renderReview()` resets every checkbox from fetched data (`static/app.js:197`) and sets `#queue-position` (`static/app.js:199`).
- `init()` awaits `loadQueue()`, then `switchView()` runs `loadView()`, which calls `loadQueue()` again without awaiting it (`static/app.js:453,81,87`). On `/review`, the queue therefore renders twice during page load.
- `static/app.js` contains no `setInterval`.

### 5.4 Root cause (confirmed Phase 1)

**H2 confirmed.** The double `loadQueue()` during `init()` was the cause.

**Mechanism:** `init()` at `static/app.js:453` called `await loadQueue()` unconditionally before calling `switchView()`. When the initial path is `/review`, `switchView('review-queue')` then calls `loadView('review-queue')` without `await`, which starts a second `loadQueue()`. If the test (or user) clicked a checkbox after the first `loadQueue()` completed but before the second one did, `renderReview()` in the second call re-read all flags from the fetched queue data (still `1`) and reset the checkbox, clobbering the explicit uncheck.

**Why intermittent:** The race window is the time between the two `loadQueue()` network round-trips. On fast runs, both finish before the click. On slower runs, the first finishes, the click lands, then the second finishes and resets the state.

**Fix** (`static/app.js`): `init()` now determines the initial view before conditionally calling `loadQueue()`. When `initial === 'review-queue'`, the upfront `loadQueue()` is skipped; the single call inside `loadView('review-queue')` is authoritative. All other views retain the existing behavior.

**Evidence:**
- 10/10 browser subtests pass on 5 consecutive in-container test runs prior to CI submission. Subtest 9 uses a fetch-interception request-count assertion: on the patched code, exactly 1 `/api/v1/review-queue` fetch is made during `/review` init; the pre-fix code path produces 2. The assertion is deterministic — see Section 5.5 for why.
- All four GitHub Actions checks passed on commit `cc0edc5` (runs `41345407604` and `41345407573`). `node --test tests/review-restrictions-browser.cjs` passed on both Windows and Ubuntu.
- H1 and H3 are effectively ruled out: H1 because the same test passed/failed at the same viewport across runs; H3 because the backend correctly saves an explicit `false` as `0` (31 Python tests verify this).
- The root cause was confirmed by code inspection and test evidence. The exact timing of the original Windows failure was not captured at runtime; no request payload was intercepted. The mechanism is inferred from source analysis and is consistent with the observed symptom and intermittency.

### 5.5 Phase 1 diagnostics (completed)

Chain confirmed through code inspection and 5-run test evidence: first `loadQueue()` render → user click → second `loadQueue()` render resets → save sends `1`. Fix eliminates second render.

The request-count assertion in subtest 9 is deterministic because `init()` resumes as a microtask after the first fetch resolves — meaning any second `loadQueue()` dispatch runs synchronously in the same microtask continuation, before any I/O callback (including Puppeteer's `waitForFunction` notification). By the time `await page.evaluate(() => window.__rqDone)` reads the chained promise, all init-time fetches have already been dispatched and are tracked. No arbitrary delays are needed.

---

## 6. Phase 0 Baseline CI Exception

> **Status: PROPOSED. Takes effect only when the owner explicitly approves it.**

### 6.1 Why it is needed

Phase closure normally requires passing Windows and Ubuntu CI, including on `main` after merge. `main` already failed QA-01 before Phase 0 began, and Phase 0 may not change application code. Without this exception, Phase 0 could not be guaranteed to close, and Phase 1 could not begin.

### 6.2 What it covers

Only this failure: the `Run node --test tests/review-restrictions-browser.cjs` step of `tests (windows-latest)`, where the failures are exactly subtest 5 and its parent, at line 68, with expected `0` and actual `1`.

| Check | PR #16 head | Post-merge `main` |
|---|---|---|
| `candidate (ubuntu-latest)` | Must pass | Does not run on push |
| `candidate (windows-latest)` | Must pass | Does not run on push |
| `tests (ubuntu-latest)` | Must pass | Must pass |
| `tests (windows-latest)`, all other steps | Must pass | Must pass |
| `tests (windows-latest)`, browser step above | Covered failure allowed | Covered failure allowed |

### 6.3 What it does not cover

- Any other failed step, subtest, assertion, or expected or actual value. Any of these keeps Phase 0 open.
- It does not make the application green, and it does not record QA-01 as PASS.
- A passing run does not close QA-01, because the failure is intermittent.
- It waives nothing in Phase 1, including the requirement for Windows PASS, Ubuntu PASS and post-merge `main` PASS.
- **It ends when Phase 0 closes.** Phase 1 and every later phase require successful post-merge Windows and Ubuntu CI.

### 6.4 Recorded risk

Until QA-01 is resolved, `main` keeps an intermittent failing check, and SEC-01's requirement that explicit edits persist remains unproven. The observed failure retained the restriction (`1`, not `0`), but the cause is unconfirmed, so no general safety conclusion follows from that.

---

## 7. Phase Status Summary

| Phase | Title | Status | Owner decision required |
|---|---|---|---|
| **Phase 0** | Baseline and Remediation Inventory | **CLOSED** | Owner approved 2026-11-01 (PR #16 merged, SHA `0a14550adab7b9ef9c1ed7dd660b784686c4b9f8`, Section 6.2 exception accepted) |
| **Phase 1** | Restore Green CI and Close PR #14 Verification | **CLOSED** | PR #17 merged SHA `812f28f`. Post-merge CI `41346905426` green. |
| **Phase A** | Data Integrity and Security (legacy phases 2, 3 and 4) — 11 findings | **CLOSED** | PR #18 merged as `5de14f9`; post-merge Source checks run `41390294489` passed on Windows and Ubuntu. No local deployment or database migration claimed. |
| Phase B | UX, Bilingual Support and Operational Security (legacy phases 5, 6 and 7) — 31 findings | **IN_PROGRESS** | Owner authorized 2026-11-02. Single branch `phase-b/ux-bilingual-operations`, draft PR #19. 30 IMPLEMENTED_PENDING_VERIFICATION, 1 BLOCKED (QA-03); none PASS. Awaiting a hosted Windows/Ubuntu run on the final HEAD and owner review. See `PHASE_B_IMPLEMENTATION.md`. |
| Phase C | AI Engine Integration and Final Release Acceptance (legacy phases 8 and 9) — 6 findings | **PREPARATORY_IN_PROGRESS** | Stacked Draft PR #20 targets Phase B PR #19 (which is still Draft). AI-02, AI-04 and AI-05 are IMPLEMENTED_PENDING_VERIFICATION (AI-04/05 synthetic evidence only); AI-01 remains OPEN, pending real LM Studio reproduction; AI-03 and QA-02 are BLOCKED pending authorized real-Ollama tests. None PASS. Phase C cannot merge or deploy before Phase B closes, and final hosted Windows/Ubuntu acceptance remains pending. See `PHASE_C_IMPLEMENTATION.md`. |

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

## 9. Pull Request Policy

Group findings that share a root cause, component, or transactional workflow into one focused PR. Split a phase into sequential PRs only when safe review, independent testing, or rollback needs it.

- Only one active implementation PR at a time.
- Every PR lists the finding IDs it addresses.
- Each PR requires relevant regression tests, documentation, and green CI.
- Owner approval is required before merging.
- After merging, verify `main` CI before opening the next implementation PR.
- Do not start another phase until all findings in the current phase meet their closure criteria.
- Avoid oversized PRs and unnecessary micro-PRs.

---

## 10. Phase 0 Closure Checklist

| Condition | Result |
|---|---|
| Baseline SHA verified | ✓ `3b1405846ab6fdd45151cc163418fb5c0dc0e027` |
| PR #14 confirmed merged | ✓ MERGED 2026-11-01T17:28:33Z |
| Windows and Ubuntu CI inspected | ✓ Section 1 and Section 5.1 |
| All findings inventoried, classified and mapped | ✓ 53 of 53, Section 4 |
| Phase dependency graph produced | ✓ Section 3 |
| Test limitations identified | ✓ Section 2.1 |
| Invariants listed | ✓ 13, Section 8 |
| QA-01 cause recorded as unconfirmed | ✓ Section 5 |
| New documentation classified for the source builder | ✓ Excluded in `public_source/policy.json` |
| No application changes | ✓ Documentation and source policy only |
| PR-level CI on the final head | See Section 11 |
| Baseline exception approved | **PENDING OWNER** |
| Roadmap approved after human review | **PENDING OWNER** |
| PR merged with owner approval | **PENDING OWNER** |
| Post-merge `main` CI meets Section 6.2 | **PENDING** |
| Owner approves closure and the transition to Phase 1 | **PENDING OWNER** |

---

## 11. Phase 0 Verification Evidence

CI results for this corrective commit are recorded once its runs complete.

---

## 12. Finding Status Legend

| Status | Meaning |
|---|---|
| `OPEN` | Finding recorded; not yet resolved |
| `IN_PROGRESS` | Fix is being developed in the active phase |
| `FIXED_PENDING_VERIFICATION` | Fix is merged; verification not yet complete |
| `BLOCKED` | Cannot proceed; owner action or unavailable resource required |
| `CLOSED` | Fix verified in CI, documented, and owner-approved |
| `ACCEPTED_RISK` | Owner has explicitly accepted the remaining risk |

---

*This document is the authoritative remediation ledger for the NajdiLab program. It must be updated during every phase, not after completion.*
