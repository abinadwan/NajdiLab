# Changelog

## Unreleased — Phase 1: Review integrity and QA-01 fix

- Fixed QA-01: resolved an intermittent Chromium regression where `contains_personal_data` was not saved as `0` after an explicit uncheck during a correction. Root cause: `init()` in `static/app.js` called `loadQueue()` unconditionally before `switchView()`, then `switchView()` called `loadQueue()` a second time without awaiting. If the user interacted with a restriction checkbox between the first and second render, `renderReview()` in the second call reset the checkbox to the persisted value (`1`), clobbering the explicit change. Fix: `init()` now skips the upfront `loadQueue()` call when the initial view is `review-queue`, preventing the double render. The single `loadQueue()` called inside `loadView('review-queue')` from `switchView()` is authoritative for that view. All other views retain the existing behavior. Closes QA-01. Addresses SEC-01 and UX-01 (explicit flag change path).
- Added regression subtest 9 to `tests/review-restrictions-browser.cjs`: "init race regression: exactly one queue fetch on /review init" — uses `page.evaluateOnNewDocument` to intercept `fetch` before navigation and count `/api/v1/review-queue` requests; chains a `Promise.allSettled` fence (`window.__rqDone`) so the assertion awaits all init-time fetches before reading the count. Post-fix: count === 1. Pre-fix: count === 2. The assertion is deterministic because the `init()` microtask dispatches any second fetch synchronously before Puppeteer's `waitForFunction` notification reaches the test. Also asserts checkbox stability after the single render cycle.
- Verified: 10/10 browser subtests pass on 5 consecutive runs. 31/31 restriction-integrity Python tests pass. 11/11 review lifecycle and management Python tests pass.
- Phase 0 is formally CLOSED (Section 6.2 exception approved by owner per 2026-11-01 authorization). Phase 1 is IN_PROGRESS.

## Unreleased — PR #14 Windows browser stability

- Set the review restriction Chromium test to an explicit 1440 x 1000 desktop viewport before navigation, preserving all assertions and integrity checks. This stabilizes the Windows desktop test; responsive UI defects and mobile acceptance remain outside its scope. Reproduction, per-run verification, limitations and source-only rollback are in the [review restriction evidence](docs/review-restriction-integrity.md#pr-14-windows-browser-viewport-follow-up-2026-11-01).

## Unreleased — dataset-only source cleanup

- Removed internal training/model acquisition/worker/benchmark/deployment source, related tests/configuration and operating guides. Removed execution HTTP routes rather than leaving410 shims; dataset eligibility and manual creation use `/api/v1/dataset-records` and `/api/v1/manual-data/{sft|direct|preference}`. Dataset remediation/review/freeze remains.
- Moved shared dataset masks/validation to dedicated modules and renamed the explicit local-tokenizer validator. Replaced architecture and user/developer/API documentation with Chat→Review→Quality→Version→external Unsloth. Consolidated safety, prior failures/skips, privacy/provenance and rights evidence; removed obsolete training artwork/screenshots.
- This is source-only: existing private data/job/log evidence, frozen exports and applied migrations stay intact. No installed update, external-service/configuration change, hosted cleanup CI, push/PR/merge or publication is claimed. Source rollback requires no data/schema rollback; review old interfaces before launch.

## Preceding Chat and integrations work — 2026-10-31/11-01

- Added own complete raw multi-turn Chat, exact template-token admission/reply reserve, separate collection OFF on creation/restart, pending review segments, immutable model identity, Stop/rollover/archive safeguards and bounded device evidence. Ollama uses immutable local digest requests on source-reviewed0.40.13; LM Studio uses pinned1.5.0 public instance-bound SDK methods. Actual installed-model/owner capacity acceptance remains open.
- Added privacy-locked immutable Unsloth prompt/completion JSONL/provenance/manifests, preserving the final target only with external completion-only loss/no packing/truncation. Earlier restricted context and changed holdout block handoff.
- Settings integrations use fixed-loopback bounded transport and explicit session-only consent. Hermes receiver refuses before reading any body; sender filtering/disconnect remains UNVERIFIED. Earlier source retirement used410 shims; this cleanup removes those source interfaces entirely.

## Preceding private preparation — 2026-10-26/30

English controls preserved Arabic content, authenticated native ingest and Host/Origin/CSRF/JSON/framing checks; unsafe readiness HTML was escaped. Portable setup, no-demo launchers and private recovery were exercised in disposable state. The separate hash-reviewed Core added atomic review/privacy/dataset/artifact/recovery boundaries and actual synthetic screenshots. Prior failures, exact platform results/skips and inaccessible-original limits remain in [verification evidence](docs/verification-evidence.md).

Private integration through PR#5 (`fdebe50aaf1a20d2f2478eed8fc979cac8372347`) did not activate licensing/publication or clear historical privacy/ownership/data rights. The dated74-row [rights ledger](docs/rights-evidence.md), [source provenance](docs/source-provenance.md), [history review](docs/privacy-history-review.md) and [release decision](docs/public-release-decision.md) retain open gates. Apache-2.0 remains a future target only.

Cleanup regression evidence, all removed/refactored files and source-only rollback are recorded in [cleanup results](docs/cleanup-results.md).
