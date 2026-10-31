# Changelog

## Unreleased — Settings integrations (2026-10-31)

- Added a server-owned connector registry and Settings UI for bounded read-only discovery of Hermes directory evidence and known numeric-loopback LM Studio/Ollama APIs. No external configuration/history/secret reads, custom endpoints, DNS, proxies, redirects, downloads, migrations or new application dependencies.
- Added explicit session-only connect/select/synthetic-test/disconnect consent with existing Host/Origin/CSRF; test approval binds the displayed selection revision to prevent cross-tab model changes. Bounded transport includes HTTP framing, payload limits and total deadlines. Disconnect waits for in-flight work and revokes only local permission; runtime processes remain unchanged. No automatic LM Studio/Ollama application history collection.
- Security compatibility change: `/api/v1/hermes-hook` now refuses with 409 `HERMES_UNSAFE_SOURCE` before body reading/parsing/storage, including authenticated/legacy clients. Hermes v0.22.5 may ignore `fields` and `enabled:false`; automatic collection and external disconnect verification remain BLOCKED/UNVERIFIED. Preserved existing records and generic authenticated manual ingestion. Retired the misleading live acceptance utility and withdrew unsafe webhook instructions.
- Added fixture-only unit/integration/controller tests and CI controller checks on Windows/Linux. Updated API/security/configuration docs and [safe Windows update/rollback](docs/integrations-windows-update.md). See the PR and [validation record](docs/integrations-validation.md) for actual results and remaining real-service acceptance gates. Applied the same Hermes receiver block to the separately packaged Core profile and updated its reviewed classification/hashes; runtime integrations remain outside Core. No merge, release, publication or installed-device change is performed by this branch.

## Unreleased — Core verification link repair (2026-10-31)

- Replaced the deleted `dev/public-core-workflow-completion` verification link in `public_source/README.md` with the existing `main` documentation path.
- Updated the Core builder SHA-256 pin for the changed README; no runtime behavior, private data, publication status, or licensing changes.
- Verified the new destination exists in `main` and the original README pin matched before modification. Full candidate build and CI tests require a post-commit run.

## Unreleased — README technology badges (2026-10-30)

- Added ten centered, linked Shields.io technology/status badges to the main README: enforced Python/SQLite minimums, vanilla JavaScript, HTML5/CSS3, local-first design, dated Core CI verification, optional Hermes integration, private repository status and future-only Apache-2.0 license target.
- The Core test badge links to the actual private GitHub workflow and explicitly dates the verification rather than claiming perpetual test success. Badge labels reflect verified source capabilities and the documented licensing boundary. No Go, React, TypeScript, Tailwind, Docker-ready or active source-license claims were added. Links point to authoritative project guides/status rather than undocumented features.
- Presentation-only change: no application code, dependencies, project visibility, licensing, package, model, training, private data or deployment changes. External badge rendering requires access to img.shields.io; documentation content remains readable without it.

## Unreleased — private post-merge documentation correction (2026-10-30)

- Integrated the four stacked development branches into private `main` via [PR #5](https://github.com/abinadwan/NajdiLab/pull/5), merge commit `fdebe50aaf1a20d2f2478eed8fc979cac8372347`; deleted the four merged branch refs. PRs #2–#4 are closed. This item records the earlier GitHub operation, not a new merge in this documentation task.
- Corrected current README/Windows/Linux installation, developer setup and maintainer checkout instructions to use default `main` rather than a deleted preparation branch.
- Reconciled present-day GitHub state across project status, release decision and documentation navigation, while preserving dated engineering/PR baselines as historical evidence.
- Documentation-only correction: no application/runtime/data/schema/production/training changes, no publication or active license. Verify current links, instructions and repository checks before merging the documentation PR.

## Unreleased — Public Core Phase 5 implementation

- Added mandatory atomic review revisions, preserved omitted flags/notes/tags/reviewer, strict boolean validation and safe lifecycle handling in candidate-only code.
- Added contextual conversations/review/search/saved-state UI, safe Arabic rendering, explicit decisions and conflict/draft controls. Independent review regressions cover privacy, lifecycle and asynchronous state handling.
- Added read-only readiness/duplicate/quality/balance/version/holdout inspection, strict contextual privacy and mask gates, explicit workshop fixtures and single-storage-instance protection.
- Added selected manifest-verified JSONL downloads, coherent snapshot-registered private backup and exclusive separate restore with integrity checks. Preserved original backup implementation unchanged.
- Original source, research, images and historical reports remain preserved; no training, license activation, publication or production operation.

## Unreleased — public core scope review (2026-10-27)

- Added original/candidate UI, 27-module, 101-route and workflow parity inventories, with actual unavailable/partial behavior and reusable-versus-historical boundaries.
- Proposed a minimum local review-to-dataset release scope and dependency-ordered B01–B12 backlog with acceptance, regression, rollback and owner gates; no feature migration.
- Clarified that existing screenshots, user guide and architecture show the original application; preserved every asset, historical record, protected source and candidate pin.
- Re-ran isolated candidate and preserved-source Linux tests; recorded explicit skips and prior-versus-current evidence in the parity report/worklog. Publication remains blocked.

## Private research isolation engineering — 2026-10-27

- Added a separate source-only core server/UI, explicit unavailable extension interface, opt-in fictional fixtures and deterministic hash-pinned candidate builder.
- Preserved all original source/research; documented blocked original-server compatibility edits.
- Added exact-candidate regression and Windows/Linux CI; legal/history/publication gates remain unresolved.

## Visual documentation and provenance continuation — 2026-10-27

- Added an editable source-grounded seven-layer SVG and deterministic generator; preserved the owner conceptual JPEG byte-for-byte and every existing Mermaid/media asset.
- Added architecture gallery, seven real synthetic UI screenshots, practical correction walkthrough and audience-based navigation.
- Added source/asset provenance and third-party attribution registers with explicit ownership, historical artifact and optional AGPL uncertainties.
- Verified SVG rendering/labels/contrast, synthetic-original preservation and documentation/application regressions; mobile detail needs zoom/scroll. No application source or protected research data changed.

## Unified readiness preparation — 2026-10-27

- Recovered the prior local rights/privacy decision package onto a branch from current main.
- Reworked the README around the project concept, verified version distinctions, official prerequisites, installation and two source-grounded Mermaid diagrams.
- Reconciled stale branch/PR references and expanded architecture/developer handover cross-links.
- Recorded fresh isolated source/installation/documentation checks with explicit historical-fixture limits.
- Preserved application behavior and research-bearing source; privacy/history, ownership/license and exact distribution-rights gates remain open. No active license or deployment.

## Unreleased — private preparation branch

- English UI/docs and LTR shell, retaining Arabic/RTL content and compatibility values.
- Host/Origin/framing/JSON/CSRF checks and authenticated Ingest with migration guide; no production activation.
- Escape export-readiness HTML; improve modal metadata contrast.
- Portable Python/venv discovery, version/port checks and idempotent offline setup. Launchers default to no demo; direct module retains historical default.
- Checkout-bound collector tools reject wrong target before data/credential writes.
- Explicit private historical-test prerequisites; present corrupt fixtures still fail; synthetic checks remain runnable.
- Authoritative multi-track status, install/developer/API/migration/training/restore handover and contribution templates.

No final license, release, history rewrite, schema migration, download, training, deployment or privacy change. Historical milestones remain in docs/historical-project-status.md. No release version or new trained model is claimed.

## Phase5 Goal5 — candidate onboarding and genuine visuals

- Added separate Core README, fictional user guide, API/architecture/contributor pages and eight actual synthetic browser captures; archived the prior minimal candidate README. Preserved original full-platform guides/assets.
- Added editable original SVG/generator and bounded, metadata-restricted PNG and external-resource-free SVG validation. Review found XML stylesheet/base bypasses; regression tests now refuse both.
- Corrected recovery instructions and verified copy-before-install into another fresh source candidate, launch and decision/version readback. No schema, private research, license or production changes.

## Phase5 Goal6 — exact-candidate acceptance controls

- Require manifest/hash-selected copies before candidate test startup; refuse original/non-candidate input and never copy unlisted local state.
- Controlled unsupported HTTP methods, strict test-only pytest import allowance, actual installer/port/runtime/native HMAC regressions.
- Include reviewed unchanged Windows/Linux install wrappers; add hosted real browser acceptance without model/runtime installs or artifact upload.

### Windows recovery corrective evidence

Retained first hosted candidate failure5 and diagnostic failure2. Explicit UTF-8 fixture IO fixed three test defects. A new real-filesystem staging-alias regression reproduced valid restore refusal; normalize only the newly created owned staging directory while preserving all link/containment/exclusive-write checks. Hosted acceptance must pass before closing this finding.

### Final-review native-ingestion refusal

Candidate-only request boundary now refuses inherited legacy unauthenticated-ingest override with explicit503, preserving original helper/production. Real fictional unauthorized writes and negative raw requests were reproduced before fix; current no-write/credential/path regressions pass locally, with hosted retest required.

## Phase5 final accepted local Core scope

- Completed B02–B06 candidate workflows, exact Windows/Ubuntu73tests/68subtests, builder11/18 and real browser review-to-version/download/backup/restore/resume. Late native legacy override is refused; final raw/no-write cases pass.
- Retained Windows5FAIL then2FAIL, REDs and all earlier evidence; fixed only candidate code/tests/docs and explicit reviewed selections.
- Prepared exact74-file rights inventory, owner decisions and private clean snapshot; no license/publication clearance.
- Verified270 baseline files retained,136 original protected hashes and12 original media hashes unchanged; inaccessible original private artifacts remain NOT_VERIFIED. Original PR#2/#3/main and Private visibility unchanged.
- Final reports, rollback and next owner decisions are linked from PROJECT_STATUS and documentation index. No models/training/production/migration/history/merge/publication action.
