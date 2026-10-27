# Public Core Phase 5 execution

Date: 2026-10-27. Authorized scope: B02–B06 candidate-only implementation and B07 evidence review. No production, original protected-source changes, training, license activation or publication.

## Goal 0 baseline and execution control

Base: `dc5c82e2e32f647ad7b5551dea7d0fdc7bf4422a`, branch `dev/public-core-release-scope`. Implementation branch: `dev/public-core-workflow-completion`, stacked against that analysis branch. Main is `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`; PR #2 remains open Draft at `d5e8c2d60a84822e4587a7fd47688ed65f29e491`; PR #3 remains open Draft at `555647fcfc6c2d73c792adfa0c02977d4b4cacdd`. Remote references fetched; repository Private; starting working tree clean.

All **270 tracked baseline paths** have private SHA256 evidence. Recalculation identifies **136 protected original files** under app/static/scripts/tests/config/migrations/plans. These originals, media, historical reports and original data remain untouched. Private datasets/weights/production state are absent and their hashes are NOT_VERIFIED. Candidate-specific sources under public_source and its tests/policy may change under this authorization.

The baseline maps **37 selected files + MANIFEST.json**, with a separate server/UI, generic core service/database/dataset libraries, opt-in fictional demo, offline setup and tests. It excludes original server, phase/training/runtime/platform-state implementations, model/data artifacts and Git. New analysis/report paths require explicit exclusion entries; no broad discovery or automatic unknown-file acceptance is permitted.

Confirmed defect: UI sends an incomplete correction body; protected service defaults omitted flags to false. Existing expected_updated_at is optional. Independent review corrected the initial second-resolution hypothesis: original utc_now emits microseconds, but does not itself guarantee a unique revision. Candidate-side transactions must require a token, merge unchanged flags and issue a strictly fresh revision without modifying the shared service. Reads, validation and writes must share the same SQLite write transaction. Restore must preserve restrictive flags and leave training ineligible.

Baseline Linux tests are recorded in [verification](public-core-phase5-verification.md). Earlier scope analysis retained the failing privacy probe. Execution sequence: reproduce and fix flags/concurrency; contextual browser review; read-only readiness/version/quality; constrained artifacts and backup; candidate docs/screenshots/architecture; deterministic exact-candidate and cross-platform acceptance; selected-content rights and independent final review. Milestones receive focused commits; their SHAs and evidence are appended here.

## Safety and rollback

No original protected modules or original tests are edited. No proposed SQL is moved into migrations. Model/historical routes remain unavailable, with no extension discovery. All tests/demos use independently fictional records and disposable candidate-local storage. Existing PRs/main/visibility remain unchanged. Roll back candidate changes with forward reverts of milestone commits and their reviewed policy pins; retain all user-created records and failed evidence. Restore backups only into a separate disposable location.

## Goal ledger

| Goal | Status | Evidence / commit |
|---|---|---|
| 0 Baseline | PASS | Reconciled refs; 270-path / 136 protected hashes; baseline tests below |
| 1 Privacy/staleness | PASS | fa2170b backend + Goal2 real browser closure |
| 2 Contextual review | PASS | 37 tests/31 subtests and real Chromium workflow |
| 3 Dataset inspection | PENDING | B03 read-only wrappers |
| 4 Artifacts/backup | PENDING | B04 containment and restore |
| 5 Docs/UI | PENDING | B05 actual candidate presentation |
| 6 Cross-platform | PENDING | B06 exact generated candidate |
| 7 Rights | PENDING | B07 selected manifest review; approvals remain separate |
| 8 End-to-end acceptance | PENDING | Real browser plus API/backup assertions |
| 9 Independent review | PENDING | Review affected behavior, not code changes alone |

## Goal 1 — atomic review safety boundary

- Candidate files: reviews.py, server.py, initial UI safety patch, review/support tests and explicit policy selections. No protected module edited. Mandatory expected_updated_at and BEGIN IMMEDIATE cover read/compare/merge/validation/write/revision/readback. Omitted flags/notes/tags/reviewer remain unchanged; strict types reject ambiguous booleans; restrictive flags force training ineligible. Revisions strictly advance beyond stored time.
- All direct mutation routes use the wrapper. Approve/generic save cannot discard a saved overlay. Exclude preserves corrected text and decision and sets exclusion; restore preserves restrictions and is PENDING/ineligible. A restored pending overlay must be explicitly resolved with exclusion selected before re-excluding; controlled400 has zero writes. Existing schemas only; unexpected review_events fails closed instead of activating it. Complete event history is not claimed.
- RED evidence: initial five failing cases plus four malformed subtests; three approval-bypass failures; four independent-review lifecycle/provenance failures; restored-overlay refusal test failed on prior code. Final exact candidate: **33 passed / 31 subtests**, zero skips. Independent reviewer exercised lifecycle, future-clock revision, no-discard and no-write rejection and found no remaining Critical/Important backend issue. Visual acceptance remains pending Goal2; initial UI already sends revision and changed fields only.
- Risks/rollback: current-state SQLite schema has no full audit sequence. Forward revert this candidate unit/pins together, preserve DB/overlay data. Original history/modules unaffected.

## Goal 2 — contextual review acceptance

- New read-only list/detail view (core_views), contextual candidate UI and browser/HTTP tests; original UI/assets remain unchanged. Conversation search/detail, user/context/original, saved correction/type/notes/reviewer/flags, filters, approve/correct/exclude/restore and explicit saved/unsaved state are operational.
- RED: three missing-view cases; new missing-database detail probe failed because writable shared connect created state; candidate mode=ro wrapper fixed it. Independent review exposed same-page draft-loss and in-flight overwrite hazards. Browser regression reproduced the dirty-loss exclusion, then confirmed same-page preservation, explicit discard reset and frozen editor/reload during delayed real HTTP writes. Serialized selection prevents out-of-order detail rendering.
- Exact candidate: **37 passed / 31 subtests**, zero skips. Real Chromium acceptance PASS: fresh offline install, conversations/context, Arabic and HTML-like inert text, correction/privacy persistence, concurrent stale conflict retains draft, safe reload, exclude, approve, restart and browser readback, 390px no-overflow, shutdown. Independent reviewer found no remaining Critical/Important issues in this boundary. Goals1–2 accepted.
- Retained intermediate browser failures: initial missing UI, selector visibility/row-load/list-refresh synchronization, and reusing a just-closed port during OS TIME_WAIT. Tests now await actual row/save readiness and restart with persisted storage on an explicitly chosen new free port. No port/authentication protection weakened. This does not claim immediate same-port reuse on every OS.
- Rollback: revert candidate UI/views/routes/tests/pins together; retain stored decisions and private artifacts. No schema change; no full event-history guarantee.
