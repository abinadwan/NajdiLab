# English localization and public release readiness work log

## Scope and initial decisions
The owner authorized implementation in a separate private development branch, with a review stop before merge/publication. Existing architecture and data contracts are retained. No final license will be added. A clean independent clone is used because the active workspace is not a Git checkout and the running project's checkout contains protected changes.

## Baseline and risks identified before edits
- Branch starts from the existing backup commit; no history is replaced.
- Private fixture copies and a SQLite online snapshot are confined to ignored development directories. Original dataset/artifact hashes are recorded in private evidence.
- Existing HTTP code lacks Host/Origin and JSON content-type validation. These require executable regression proof before fixes.
- Existing history includes author identity, machine paths and local backup details. A legacy curation module also contains actual Arabic review corrections; these are protected data, not UI strings. They must not be translated.
- The owner selected mandatory ingest credentials by default, with a documented transition and explicit temporary legacy opt-in. Production configuration remains unchanged.

## Rollback
No production deployment occurs. Discarding or reverting the development branch restores the previous code. Keep private evidence and corpus copies out of Git. Never rewrite existing public/private history as part of rollback. Security changes require their documented configuration migration before any later deployment.

## Implementation and verification checkpoints
- Baseline: 257 tests and 8 subtests passed using private copies; protected original files were hashed before edits.
- Security RED tests reproduced Host/Origin/content-type/CSRF and ingest authentication failures. GREEN request-boundary suite passed 19 cases. Owner-selected mandatory ingest policy supports bearer or existing Hermes raw-body HMAC; invalid credentials remain rejected even in compatibility mode.
- English UI, backend/CLI errors, explanatory comments and docs were translated at their owning layers. Protected corpus/review content and API values were classified before edits. Windows analysis paths/launchers became checkout-relative; training adapter logic did not change.
- Real browser: entered synthetic Arabic in English controls, observed RTL content and LTR English notes, saved through CSRF and read back the identical text. No actual corpus was used in the browser.
- Browser observation found low-contrast dark modal metadata; paired theme variables fixed it. Contrast regressions and light/dark visual confirmation passed.
- Independent security reviewer found no blocking web-boundary issue after 20 raw probes and four JavaScript checks. Independent localization reviewer verified 113 HTML values, protected source/data and unchanged backend AST structure except strings. A broken PowerShell command escape was found in three guides and repaired/rechecked.
- Final complete fixture-enabled suite: 291 passed, 68 subtests, one existing warning. A separate code-only test copy: 267 passed, 24 historical missing-private-fixture failures. These remain publication work, not silent skips.
- All 317 protected original data/artifact files matched baseline SHA256. Schema/migrations and protected actual correction/evaluator modules were preserved. Backup volumes and production/training services were unchanged.
- Full history/current-file privacy review found no real credentials, but historical personal paths/author metadata/backup details and actual-data source remain public-release blockers. Sensitive exact evidence stays outside Git.
- Decision: NOT READY. No final LICENSE, public conversion, release, merge, history rewrite or production deployment is performed. The private development branch is the review artifact.

## 2026-10-27 — Expanded installation and maintainer handover request
Baseline: existing development branch, HEAD `85c39ac3f4e15db916d46db22e05095cca10a286`; all prior uncommitted localization/security work preserved. Latest private-fixture suite: 293 passed, 68 subtests, one existing warning. Remote main matches the baseline; no development branch exists remotely yet.

Additional authorized work: authoritative multi-track PROJECT_STATUS; portable version-checked virtual-environment launchers; idempotent local setup without third-party core dependencies; developer/API/migration/shell handover; contribution templates and proposed attribution; clean-checkout verification on Windows and available isolated Ubuntu/WSL. No production migration, service control or training is authorized.

Ruling: make historical-artifact requirements explicit in the specific tests that consume them. Missing private artifacts may report SKIP with a reason; existing-but-invalid artifacts must continue to fail. Preserve previous failed-run evidence. A public checkout cannot reproduce historical model results.

Ruling: setup creates an isolated standard-library venv without pip or network installs; development test packages are a separate optional step. Setup never initializes a database or applies SQL. Launch defaults to no demo; explicit NAJDILAB_NO_DEMO=0 allows samples only in disposable instances. Existing data/settings are never replaced.

## 2026-10-27 — Expanded implementation and verification complete
- Shared offline installer and thin platform wrappers; deterministic interpreter/venv selection, Python/port checks, no-demo launcher default. Eight regressions RED to GREEN; setup preserves existing settings/database/complete venv and refuses incomplete environment replacement.
- PROJECT_STATUS reconciles three tracks, v008/v009, REJECT versus early approval snapshots, Round 2 zero-step Dry Run and pending approvals. Expanded handover/API (101 routes)/shell/requirements/migration/training guides and contribution artifacts prepared; no final LICENSE.
- Source-only suite: 278 passed, 23 explicit historical-private-file skips, 68 subtests, one old warning. Previous 24-failure baseline preserved; one empty-registry test fixed as synthetic, 23 prerequisites declared. Full authorized fixture-copy suite: 301 passed, 68 subtests, one old warning.
- Windows 11 and Ubuntu 24.04/WSL2: fresh/repeated setup and paths with spaces, actual launch/health/conflict/shutdown, no-demo, synthetic SQLite online backup/hash/restore and reinstall preservation passed. Optional Windows development dependency commands passed separately. Native Linux/other platforms/real training remain unverified.
- Final independent reviewer: important wrong Ingest docs field fixed (conversation_id); status-code docs aligned with actual 400. Corrected example authenticated and idempotency/Arabic roundtrip verified in WSL. No new setup/collector safety blocker. Inherited CSP chart-width issue deferred as visual debt; inherited startup-before-bind documented; production/rights/history/platform breadth remain explicit gates.
- 317 original protected files SHA256 matched again; protected corpus/correction/evaluator source and schema/config unchanged. No backup-volume or live-service changes. Current/history scan: no actual credentials discovered; synthetic sentinels classified; personal/history/real-data rights blockers remain.
- Ruling: no final license/copyright identity, history sanitation, metadata/visibility/release/merge or production rollout is inferred from preparation. A private review branch/PR is the deliverable; decision remains NOT READY — BLOCKERS REMAIN.

## GitHub CI portability failures — root causes and fixes
First hosted run exposed two test-harness assumptions that did not fail on local Windows: Windows temp paths can have 8.3 aliases while production path resolution returns canonical long names; the portability assertion now compares resolved paths. Newer Linux Python shutil.copy2 passes follow_symlinks to the injected chmod stub; that fault-injection wrapper now forwards standard-library arguments while preserving all intentional failure/rollback checks. No production deployment code changed. Hosted failures are retained as RED evidence. Workflow now runs branch work through pull_request and main through push to avoid duplicate jobs.

## Remote delivery verification
Ordinary push created the development review branch; Draft PR #1 opened and attached. Real GitHub clone passed fsck, setup, 278 source-only tests (23 historical skips), docs/API verification and actual cloned launcher/health/shutdown. Corrected hosted CI run 40451855276 passed Windows (278 / 23 skips) and Ubuntu (277 / 24 skips), both 68 subtests and one existing warning. No production code changes were needed for the two test-harness corrections. Private visibility and unchanged main confirmed.

Ruling: hosted native-Linux source checks add evidence without claiming broad native deployment support. Public release stays blocked by license/copyright, historical privacy/actual-data and exact rights decisions. Rollback remains ordinary revert/continued unchanged main; backup and production untouched.
