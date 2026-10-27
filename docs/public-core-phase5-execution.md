# Public Core Phase 5 execution

Date: 2026-10-27. Authorized scope: B02–B06 candidate-only implementation and B07 evidence review. No production, original protected-source changes, training, license activation or publication.

## Goal 0 baseline and execution control

Base: `dc5c82e2e32f647ad7b5551dea7d0fdc7bf4422a`, branch `dev/public-core-release-scope`. Implementation branch: `dev/public-core-workflow-completion`, stacked against that analysis branch. Main is `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`; PR #2 remains open Draft at `d5e8c2d60a84822e4587a7fd47688ed65f29e491`; PR #3 remains open Draft at `555647fcfc6c2d73c792adfa0c02977d4b4cacdd`. Remote references fetched; repository Private; starting working tree clean.

All **270 tracked baseline paths** have private SHA256 evidence. Recalculation identifies **136 protected original files** under app/static/scripts/tests/config/migrations/plans. These originals, media, historical reports and original data remain untouched. Private datasets/weights/production state are absent and their hashes are NOT_VERIFIED. Candidate-specific sources under public_source and its tests/policy may change under this authorization.

The baseline maps **37 selected files + MANIFEST.json**, with a separate server/UI, generic core service/database/dataset libraries, opt-in fictional demo, offline setup and tests. It excludes original server, phase/training/runtime/platform-state implementations, model/data artifacts and Git. New analysis/report paths require explicit exclusion entries; no broad discovery or automatic unknown-file acceptance is permitted.

Confirmed defect: UI sends an incomplete correction body; protected service defaults omitted flags to false. Existing expected_updated_at is optional and second-resolution writes can reuse a value. Candidate-side transactions must require a token, merge unchanged flags and issue a strictly fresh revision without modifying the shared service. Reads, validation and writes must share the same SQLite write transaction. Restore must preserve restrictive flags and leave training ineligible.

Baseline Linux tests are recorded in [verification](public-core-phase5-verification.md). Earlier scope analysis retained the failing privacy probe. Execution sequence: reproduce and fix flags/concurrency; contextual browser review; read-only readiness/version/quality; constrained artifacts and backup; candidate docs/screenshots/architecture; deterministic exact-candidate and cross-platform acceptance; selected-content rights and independent final review. Milestones receive focused commits; their SHAs and evidence are appended here.

## Safety and rollback

No original protected modules or original tests are edited. No proposed SQL is moved into migrations. Model/historical routes remain unavailable, with no extension discovery. All tests/demos use independently fictional records and disposable candidate-local storage. Existing PRs/main/visibility remain unchanged. Roll back candidate changes with forward reverts of milestone commits and their reviewed policy pins; retain all user-created records and failed evidence. Restore backups only into a separate disposable location.

## Goal ledger

| Goal | Status | Evidence / commit |
|---|---|---|
| 0 Baseline | PASS | Reconciled refs; 270-path / 136 protected hashes; baseline tests below |
| 1 Privacy/staleness | IN_PROGRESS | Regression reproduction next; issue P5-01/P5-02 |
| 2 Contextual review | PENDING | B02 candidate-only UI |
| 3 Dataset inspection | PENDING | B03 read-only wrappers |
| 4 Artifacts/backup | PENDING | B04 containment and restore |
| 5 Docs/UI | PENDING | B05 actual candidate presentation |
| 6 Cross-platform | PENDING | B06 exact generated candidate |
| 7 Rights | PENDING | B07 selected manifest review; approvals remain separate |
| 8 End-to-end acceptance | PENDING | Real browser plus API/backup assertions |
| 9 Independent review | PENDING | Review affected behavior, not code changes alone |
