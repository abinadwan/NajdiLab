# Changelog

## V2.0.0 — development candidate (2026-11-03, `update-project`, Draft PR #23; not a release)

- **Product version V2.0.0** from one source (`app/version.py`): server banner and `Server` header, Hugging Face User-Agent, `/api/v1/config`, `/api/v1/health`, the sidebar under the Najdi Lab / نجدي لاب name and Settings → About Najdi Lab. Release notes: `docs/development/RELEASE_NOTES_V2.0.0.md`.
- **Hugging Face Direct** (`app/hf_hub.py`): GGUF search, revision-pinned details with license, access and per-file size/SHA-256, bounded remote GGUF header reads. HTTPS to Hugging Face hosts only, every redirect checked, no credentials, gated repositories blocked.
- **Storage-safe downloads and model library** (`app/model_store.py`, migration 009): per-volume preflight (file + reserve, larger on the system drive, + other active downloads), live free-space monitoring with safe pause, `.part` + atomic rename, size and SHA-256 verification, pause/resume/cancel, recheck, delete with typed confirmation; files only in `data/models/huggingface/`.
- **Smart Model Advisor** (`app/model_advisor.py`): COMPATIBLE / LIMITED / UNVERIFIED / BLOCKED with evidence labelled measured, reported or estimate; download, load and performance kept separate.
- **NajdiLab Native**: refuses managed files that are not verified READY; loading stays an explicit approved step.
- **Chat V2**: context usage indicator from engine-measured counts, configurable 70/85/95 % notices, context-limit panel with exact counts; exact admission and the audited `CONTEXT_LIMIT` transition unchanged; summary handoff deferred.
- **Fixes found during acceptance**: the chat preset check held the runtime lease during the host hardware snapshot (Windows `ENGINE_BUSY` on the next Start; regression test added); a finished download could be reported active for an instant (Delete hidden; regression test added); Arabic sentence patterns ordered before a generic `{a} of {b}` pattern; analytics/balancer bar widths (CSP) carried over from the redesign.
- **Managed llama.cpp runtime** (`app/runtime_catalog.py`, `app/managed_runtime.py`, Model library → llama.cpp runtime, `scripts/install.py --runtime`): pinned official build `b12059` with the SHA-256 of every archive; local GPU/driver detection (compute capability, driver CUDA version) selects CUDA 13.4 / 12.x, Vulkan or CPU and explains every rejected package; HTTPS downloads from GitHub's release hosts only, or owner-supplied offline archives; safe extraction into a staging folder; the build must prove its version and commit, list its device and compute on it with a locally generated tiny model before an atomic switch; previous install kept for rollback; repair, update, verify and typed-confirmation uninstall; Native start gate re-checks the files. No binaries in git. Verified on Windows with an RTX 5070 (CUDA 13.4 package). Record: `docs/development/MANAGED_RUNTIME.md`.
- **Tests**: `tests/test_managed_runtime.py`, `tests/fake_github.py`, runtime steps in `tests/models-browser.cjs`, runtime messages in `tests/i18n-models.test.cjs`; the synthetic GGUF writer moved to `app/synthetic_gguf.py` (used by the GPU probe); `tests/test_hf_direct.py`, `tests/fake_hub.py`, `tests/test_version.py`, `tests/chat-context.test.cjs`, `tests/i18n-models.test.cjs`, `tests/models-browser.cjs`; CI workflow lists the new Node tests; inventory pins updated for migration 009 and the reviewed `chat_workspace.py` change.

## Unreleased — Najdi Lab premium bilingual redesign (2026-11-03, `update-project`, Draft PR #23)

- **Brand identity:** original Najdi Lab mark (ن with a triangular Najdi wall opening), Arabic and English outlined wordmarks, lockups, light and dark variants, optically sized favicon and app icon (`static/brand/`, `static/favicon.svg`). Arabic interface shows نجدي لاب, English shows Najdi Lab.
- **Design system:** all colours, status pairs, radii and type roles are tokens in `static/theme.css` (light and dark); ~186 hard-coded colours in ten legacy stylesheets were replaced with tokens; new `static/najdi.css` layer for type, shell, components and screens. Reference: `docs/design-system.md`.
- **Type:** IBM Plex Sans + IBM Plex Sans Arabic as one family, IBM Plex Mono for identifiers; bundled woff2 subsets under the SIL OFL (`static/fonts/`), no network fonts. `app/server.py` registers `font/woff2`.
- **Shell and screens:** framed-sheet layout, quiet sidebar with outline SVG icons and a scrolling nav, breadcrumb top bar with icon-led language and theme controls, dashboard rebuilt around the conversation → Gold pipeline, unified PASS/FAIL/BLOCKED/REVIEW/PENDING status vocabulary with shapes, consistent buttons, inputs, tabs, tables, notices, dialogs, empty and loading states across all 15 views and the chat dialogs.
- **Fixes:** Analytics and Balancer bars now render at their real width (inline `style` attributes were blocked by the CSP); breadcrumb text now translates in both directions; emoji icons replaced; phone menu reports `aria-expanded` and closes on Escape or an outside click.
- **Verification:** axe WCAG 2 A/AA 0 violations and 0 overflow across 212 states (light/dark × Arabic/English × desktop, tablet, phone, 200 % and 400 % zoom). Record, screenshots, test results, limitations and rollback: `docs/development/NAJDI_LAB_REDESIGN.md`.

## Unreleased — Chat V2 remediation (2026-11-03, same Draft PR #22)

- **PR #21 reconciled** (`cherry-pick -x 95e7604`): incomplete-context collected segments are review-only; presets need a proven ceiling and a fitting estimate; Ollama approval withdrawn on any model/context change; Enter repeat/IME guards; literal Markdown escapes; raw-text view; PR #21's INCOMPLETE_RESPONSE wording with PR #22's `check` and a `hint`. See `docs/development/PR21_PR22_RECONCILIATION.md`.
- **Security review** (`docs/development/CHAT_V2_SECURITY_REVIEW.md`): Native child env no longer inherits llama.cpp flags; symlink escapes not listed; stronger model identity; stalled stream writes time out; query strings omitted from logs; Core builder classification fixed (was failing on `d085ed2`).
- **Permanent deletion audit** (`docs/development/PERMANENT_DELETION_AUDIT.md`): busy WAL reported and retried at start; immutable reviewer reasons disclosed.
- **UX/UI phase** (`docs/UX_UI_DESIGN_REVIEW.md`): axe-core WCAG 2 A/AA violations 148 → 0 and page overflow 28 → 0 across 212 states; tablet layout, header New chat, dialog scrolling at 400 % zoom, dark-mode contrast, tab semantics, focusable code blocks.
- **Windows/RTX acceptance BLOCKED** (no computer connected): `scripts/acceptance_chat_v2.py` and `docs/development/WINDOWS_ACCEPTANCE.md`.
- README guard extended (well-formed badge URLs, four badge rows, all relative links).

## Unreleased — Chat Experience V2 and NajdiLab Native (`feature/chat-experience-v2`, Draft, stacked on the PR #19/#20 integration branch)

- Chat history sidebar: local automatic titles, rename, search, pin, date groups, archive and restore (prior status recorded), collapsible with a saved preference; mobile overlay.
- Permanent chat deletion with typed confirmation, preview, refusal while running or exported, redaction where immutable review events exist, `secure_delete` and WAL truncation, content-free tombstones. Tested on synthetic data only.
- Streaming replies (NDJSON) for Ollama, LM Studio and NajdiLab Native; Stop; separate thinking panel never saved or collected; phase timings; partial replies marked and never saved.
- `INCOMPLETE_RESPONSE` now reports which completion check failed (`check`), e.g. `STOP_REASON_LENGTH` when thinking consumes the reply reserve.
- Safe Markdown rendering of replies (original renderer; stored text unchanged).
- Enter to send, Shift+Enter newline, IME-safe, duplicate-safe.
- Context presets Light/Balanced/Long with a budget breakdown; clearer Ollama load approval; hardware tables with measured/reported/estimated/unknown labels; 4096 estimate tier.
- NajdiLab Native: owner-supplied llama.cpp `llama-server`, GGUF discovery and validation, exact admission, loopback-only with API key, start/stop. CPU + synthetic model only tested.
- Consented collection now records single-turn/multi-turn segments with context metadata.
- Migration 008 (lossless `chat_sessions` rebuild, `chat_deletions`). Protected chat file pins updated deliberately.
- README: owner-approved design restored and updated (RESTORE-README), with a structure guard test; new synthetic screenshots.
- Docs: `docs/development/CHAT_EXPERIENCE_V2.md`, `docs/native-runtime.md`, `docs/THIRD_PARTY_ATTRIBUTION.md`, retention policy update.

## Unreleased — Phase C (separate stacked Draft PR; preparatory only)

- Reconciled the outdated `scripts/backup.py` protection SHA-256 with the already merged Phase A backup refactor after checking GitHub provenance and both file digests; no backup script code changed. Fixed the Phase C mapping-table column count and current finding summary. Hosted tests and real-model acceptance remain pending.

- Owner approved beginning Phase C source-only work while Phase B PR #19 remains Draft; merge and local real-model testing remain gated on Phase B closure.
- AI-02: preserve generic `RESULT_MISMATCH` while reporting exactly which of four LM Studio reply-integrity checks failed via a fixed, content-free allowlist. No prompts, generated output or model IDs are logged/exposed. All failing turns still refuse saving.
- Added fake-SDK test coverage for each predicate and for rejecting untrusted diagnostic identifiers. Hosted and real-model acceptance is **not yet verified**; no client/device changes, schema updates or model downloads.
- The six original Phase C finding IDs and blocked hardware/consent acceptance are tracked in `docs/remediation/PHASE_C_IMPLEMENTATION.md`.
- AI-02 verification: the guard test `test_chat_security_implementation_and_export_contract_are_preserved` failed because the two changed Chat files are hash-pinned in `docs/cleanup-inventory.json` and the pins were not refreshed. After reviewing the diff, re-pinned only those two entries (test unchanged). Added 24 Arabic catalog entries for Chat engine refusals, including the four `RESULT_MISMATCH` diagnostics, with a Node check that every fixed message in `app/chat_engine.py` is translated.
- AI-01 (not fixed, not reproduced): pinned `lmstudio==1.5.0` source shows `STRUCTURED_OUTPUT` and `STREAM_CONTENT` cannot fail in normal operation; end-to-end tests through the real SDK, helper and workspace prove a named, content-free refusal that saves nothing for instance and token-count mismatches. Owner retest table documented.
- AI-04 (evidence only): real-SDK contract tests for identity/context/template drift, full templated token admission and overflow rollover, non-EOS stop reasons, and Stop sending an SDK channel cancel. Mutation-checked; no product code changed.
- AI-05 (evidence only): new independent suite `tests/test_ai05_collection_privacy.py` (13) for OFF-by-default collection, explicit non-retrospective consent, pending pairs blocking exports, restrictions and archive keeping pairs out of training, and native LM Studio/Ollama chat stores never opened. No defect found.
- AI-03 and QA-02: acceptance plans prepared, **not executed**; no Ollama, LM Studio or model was started.
- Local results on this tree (container, Chromium only, `lmstudio==1.5.0` installed from `requirements-chat.txt`): Python 673 passed, 33 skipped (22 private historical artifacts, 9 disposable real Ollama, 2 Windows-only), 59 subtests; Node unit 29/29; chat-browser PASS; review-restrictions 12/12; i18n 10/10; a11y 13/13; Core builder 12, candidate build/verify OK (72 files, unchanged manifest), candidate 78 tests, harness and browser PASS. Skips are not passes. Hosted Windows/Ubuntu not run.


## Unreleased — Phase B (in progress): NajdiLab-first model integrations

Initial increment only; **31 original Phase B findings are not yet complete**. A single draft PR holds the whole Phase B effort.

- Removed the Hermes card and all Hermes actions from Settings. The controller filters both rendered cards and actionable snapshots to the two supported model runtimes, Ollama and LM Studio.
- Preserved the backend and Core's blocked legacy Hermes receiver. No installed Hermes, Gateway, sessions, native conversations or external services were touched.
- Updated Settings copy to make NajdiLab-owned chat the primary experience, and added a noninteractive, explicitly unavailable Hugging Face Direct preview for a separately authorized later phase.
- Added controller regression coverage for HTML escaping, excluding legacy source cards, and refusing synthetic actions for a hidden connector.
- Recorded architecture and acceptance requirements in `docs/remediation/PHASE_B_IMPLEMENTATION.md`. Phase A is closed after merged PR #18 and green main CI; Phase B started with explicit owner authorization.
- No local installation, database migration, model download, GPU allocation, merge or Phase C implementation.



### Phase B operational QA (local, pending hosted verification)
- QA-07: optional timestamped ingest signatures (`X-NajdiLab-Timestamp`) refuse stale and replayed requests; `NAJDILAB_REQUIRE_FRESH_SIGNATURE=1` makes them mandatory. Existing senders keep working.
- QA-06: `GET /api/v1/hermes-hook/refusals` shows whether anything still delivers to the blocked Hermes hook, without storing request content.
- QA-04: symlink and junction refusal is tested without needing permission to create links.
- QA-08: retention and deletion semantics are tested end to end and documented in `docs/data-retention.md`. Owner approved logical deletion/exclusion/archive for Phase B (2026-11-02); true erasure is a separate future feature, not implemented or promised today.
- QA-03 stays blocked on private historical files that must not be recreated.

### Phase B UX-05 complete content (local, pending hosted verification)
- Reviewed cards and dataset records keep their short preview and add "Show full text" with the exact stored text; review context continuity is now covered by a test.

### Phase B UX-22 / QA-05 accessibility and zoom (local, pending hosted verification)
- Every control now has an accessible name in English and Arabic; filter and sort menus are named; skip link added.
- Single-key review shortcuts (4 approves) are off by default and never act behind an open dialog or in a field; enable them in Settings.
- No page-level horizontal scrolling at 200% and 400% zoom in either language.
- New check: `tests/a11y-browser.cjs`. See `docs/accessibility.md`. Other browsers and real screen readers are not verified.

### Phase B UX-10 navigation (local, pending hosted verification)
- Sidebar regrouped in workflow order (Overview, Chat, Review, Data entry, Datasets, Export, Administration); all 15 destinations and routes kept.
- Groups are announced as labelled groups, icons are hidden from screen readers, the current page is marked with `aria-current`, and collapsed items keep their names.
- Blocked browser storage no longer stops the interface from starting.

### Phase B UX-21 Arabic and English interface (local, pending hosted verification)
- Complete right-to-left Arabic and left-to-right English interface with a language selector in the top bar and Settings; the choice is remembered in the browser and switching needs no reload.
- Dynamic messages, errors, confirmations, dates and server validation messages are translated; unknown server messages are labelled and shown isolated.
- Conversation and dataset content, identifiers and model names are never translated.
- Fixed while doing this: top-bar overflow at 390px, unguarded theme storage, and browser fixtures that could read project exports or the default database.
- New checks: `tests/i18n-catalog.test.cjs`, `tests/i18n-browser.cjs`. See `docs/localization.md`.

### Phase B UX-20 record paging (local, pending hosted verification)
- Conversations, reviewed records, manual data and saved chat sessions are paged by the server with `limit`/`offset` and `page` metadata; invalid values return 400. The silent 500/200 caps and the unbounded conversation list are gone.
- Shared UI pager with exact "Showing a–b of N" ranges; saved sessions show "N of M loaded" with Load more.
- Browser fixtures now fail loudly if a route would use the default application database.

### Phase B CI repair and Actions cost control
- Fixed the `review-restrictions-browser.cjs` failures that kept `Source checks` red since UX-07: the test assumed an empty restored note and did not handle the intentional `beforeunload`/`confirm` guards. The test now asserts the restored server value and each guard prompt.
- UX-19: the error toast's dismiss glyph is hidden from screen readers so alerts announce only the message; the message has its own `.toast-message` element.
- `Source checks` now runs `tests/phase39-ui.test.cjs` and `tests/dataset-identity-ui.test.cjs`, which had never run in CI and were both broken: a stale code-slice marker after UX-13 (phase39) and a tick-count timing assumption (UX-27; product guard correct, mutation-checked). `tests/test_ci_workflows.py` guards that every Node unit test is wired.
- Both heavy workflows cancel superseded runs, skip draft-PR pushes, allow manual dispatch and have job/step timeouts. See `docs/developer-setup.md`.

### Phase B functional UX increment (implementation pending verification)
- UX-04: display review-collection outcome on each persisted model answer without treating a pair as approved training data.
- UX-08: never clear a newer draft when an older send completes; synthetic delayed-browser and Node regressions added.
- UX-06: persistently render all export-readiness blockers, with output escaping.
- UX-14/15: isolate Add Data subtabs from dialog tabs and reject an empty/manual SFT turn list with a recoverable message.
- UX-16/17: provide manual save pending/failure/retry feedback and label the exclusion reason as required.
- UX-12: use existing readable Frozen dataset versions for Unsloth handoff; no manual version names.
- Eight findings are marked IMPLEMENTED_PENDING_VERIFICATION in the roadmap; remaining Phase B findings stay open. CI/browser evidence on the final commit is still required.


### Phase B review safety and status display (pending acceptance)
- UX-07: protect unsaved review corrections/notes/restriction tags and flags on navigation, reload and queue refresh, without persisting drafts.
- UX-09: display pinned saved-session identity and reject Send when its original runtime/model is not selected; new-chat selectors are explicitly separate.
- UX-11: replace static dashboard readiness prose with API-supported snapshot wording; export readiness remains a separate gate.
- UX-24: collapsed sidebar now changes the shell grid width; synthetic Chromium width assertion.
- UX-26: remove hardcoded local port and unsupported “SQLite Passed” badge; current origin and live service check are presented with truthful limitations.
- Pending: final Windows/Ubuntu CI and browser acceptance for these new changes, remaining UX/QA findings and complete Arabic RTL + English LTR localization.


### Phase B dataset integrity UI and responsive presentation — pending final verification

- UX-13: always refresh Dataset Versions library on page visit; reject stale/unreadable version selections.
- UX-18: post-edit verification UI uses server-sized queues; handles zero rows, preexisting decisions, unknown audit gate values and failed-save retry (without changing historical private data).
- UX-23: mobile CSS constrains 390px workflow layouts while preserving deliberate scrolling inside wide tables.
- UX-25: dark review/status text and surfaces use legible paired colors; browser contrast tests added.
- UX-27: Evaluation results show the requested dataset version and do not accept stale responses from a previous selection.
- Synthetic Node and hosted-browser tests are included. CI and complete mobile/zoom/accessibility acceptance are still required. No local deployment or merge.


### Phase B human-review approval and persistent errors — pending validation

- UX-03: independent dataset export eligibility is explained beside the review approval control, including assistive descriptions and a browser test protecting stored restrictions.
- UX-19: error notifications are accessible and persistent with explicit dismissal; only successful status messages auto-expire.
- Existing synthetic DOM test scaffolding models the required browser element and ARIA APIs; fresh Chromium and CI acceptance is required.
- Updated remediation count: 20 implemented awaiting verification, 11 open; PR #19 remains DRAFT, not merged.

## Unreleased — Phase A: Data Integrity and Security (11 findings)

Includes the corrections from both independent reviews of PR #18.

### Review lifecycle and audit trail
- SEC-03: `_save_review_conn` validates the lifecycle transition before writing, independent of the `review_events` table, so a DELETED or IGNORED review cannot be approved without restoration. Re-saving a decision with the same status (edited correction or restriction flags) is now an allowed, audited transition; without it, `review_events` would have blocked marking an approved review as personal data.
- SEC-05: `migrations/007_review_events.sql` creates the immutable `review_events` table and a one-row immutable `review_event_baseline` holding the highest pre-upgrade review id. No historical events are fabricated. Readiness reports legacy reviews without events as `REVIEW_HISTORY_UNVERIFIABLE` (warning), post-upgrade reviews without events as `REVIEW_EVENT_MISSING` (blocking), and event conflicts as blocking; a missing baseline fails closed. The public Core profile keeps its 001–004 contract and does not ship 007.

### Bulk manual edits
- SEC-04: `bulk_update_manual_data` validates the whole request first (non-dict items, unknown types and invalid ids are rejected, not skipped), rejects more than 500 items instead of truncating, and applies all updates and version rows in one transaction.

### Migrations and backup
- DB-01: only migrations listed with a matching SHA-256 in `migrations/registry.json` run; unregistered files are never read, and a changed, missing or malformed registered entry stops startup before the database is touched. The Core candidate ships its own 001–004 registry (`public_source/migration_registry.json`).
- DB-02: migrations are split into statements with `sqlite3.complete_statement` and executed by the loader inside one `BEGIN IMMEDIATE` together with a parameterized ledger row. Any transaction-control statement other than one leading `BEGIN` and one final `COMMIT` (including an inline `...; COMMIT;`, found in the second review), plus `ATTACH`/`DETACH`/`VACUUM` and body `PRAGMA`s, is refused before any pending migration runs.
- DB-03: `backup_db()` is the single snapshot implementation, now used by `scripts/backup.py`: read-only source, `integrity_check` on the copy, never overwrites, never creates a missing source. Docs make the verified pre-upgrade backup the rollback for 007 and prohibit dropping `review_events`.

### Dataset contracts
- DATA-01: freeze refuses a version with no training records; end-to-end tests prove Frozen manifests carry matching diagnostics and loss-mask metadata and that missing or stale metadata keeps the version Draft.
- DATA-02: absent diagnostics give an actionable reason distinct from stale diagnostics; a valid Draft reports READY.
- DATA-03/DATA-04: the Balancer takes evaluation files from `dataset_platform.EVAL_FILES` and now supports `native_tool_use.jsonl`, matching Health, Quality and Unsloth export.
- DATA-05: a missing exports directory is created; a fresh installation's `/api/v1/dataset-versions` returns an empty list, which the UI shows as "No dataset versions are available to check."

### Tests and policy
- `tests/test_phase_a_regressions.py` (migration, lifecycle, bulk, legacy-upgrade and backup tests, run against an isolated copy of `migrations/`) and `tests/test_phase_a_dataset_acceptance.py` (freeze, health, balancer and HTTP).
- `public_source/policy.json`: re-pinned the changed Core-selected modules; selected `public_source/migration_registry.json` as the Core `migrations/registry.json`; excluded `migrations/007_review_events.sql`, `migrations/registry.json` and both new test files from the Core candidate.
- Docs: `database-and-migrations.md`, `database-schema.md`, `backup-and-restore.md`, remediation roadmap (phase inventory corrected to 0/5/11/31/6 = 53).

## Unreleased — Phase 1: Review integrity and QA-01 fix

- Fixed QA-01: resolved an intermittent Chromium regression where `contains_personal_data` was not saved as `0` after an explicit uncheck during a correction. Root cause: `init()` in `static/app.js` called `loadQueue()` unconditionally before `switchView()`, then `switchView()` called `loadQueue()` a second time without awaiting. If the user interacted with a restriction checkbox between the first and second render, `renderReview()` in the second call reset the checkbox to the persisted value (`1`), clobbering the explicit change. Fix: `init()` now skips the upfront `loadQueue()` call when the initial view is `review-queue`, preventing the double render. The single `loadQueue()` called inside `loadView('review-queue')` from `switchView()` is authoritative for that view. All other views retain the existing behavior. Closes QA-01. Addresses SEC-01 and UX-01 (explicit flag change path).
- Added regression subtest 9 to `tests/review-restrictions-browser.cjs`: "init race regression: exactly one queue fetch on /review init" — uses `page.evaluateOnNewDocument` to intercept `fetch` before navigation and count `/api/v1/review-queue` requests; chains a `Promise.allSettled` fence (`window.__rqDone`) so the assertion awaits all init-time fetches before reading the count. Post-fix: count === 1. Pre-fix: count === 2. The assertion is deterministic because the `init()` microtask dispatches any second fetch synchronously before Puppeteer's `waitForFunction` notification reaches the test. Also asserts checkbox stability after the single render cycle.
- Verified: 10/10 browser subtests pass on 5 consecutive in-container test runs prior to CI submission. All four GitHub Actions checks passed on `cc0edc5` (Source checks run `41345407604`, Source-only candidate run `41345407573`), including `node --test tests/review-restrictions-browser.cjs` on both Windows and Ubuntu. 31/31 restriction-integrity Python tests pass. 11/11 review lifecycle and management Python tests pass.
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

## 2026-11-02 — Chat review workflow (isolated fix branch)

- Clear new-conversation context/reply presets, Advanced limits and proven ceiling with unverified memory estimates. Saved settings remain immutable.
- Guarded Enter send, Shift+Enter newline, failed/newer draft retention, safe presentation-only Markdown with raw view.
- Consented Chat multi-turn context with final-only targets; quarantine incomplete historical/mid-chat prefixes without retroactive capture. No schema change, forced ratio, old data rewrite or automatic training.
- Constant completion diagnostics preserve strict validation. Historical successful-stop refusal is not reproduced. See [actual checks and safe update/rollback](docs/chat-review-workflow-results.md).
