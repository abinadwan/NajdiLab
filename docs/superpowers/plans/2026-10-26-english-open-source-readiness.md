# English localization and open-source readiness implementation plan

> For agentic workers: implement the assigned file ownership boundaries and use failing regression tests before security behavior changes; independently review the complete branch before handoff.

**Goal:** Provide an English developer/operator experience while preserving Arabic data and preparing a private review branch for a possible public release.
**Architecture:** Retain the standard-library Python HTTP server, SQLite schema, API keys and identifiers. Translate presentation at its existing owning layer. Protect Arabic corpus, review corrections and test fixtures by classifying strings before editing. Add trust-boundary controls in HTTP request handling, without deploying them.
**Tech stack:** Python 3.11+, sqlite3, unittest/pytest, plain HTML/CSS/JavaScript.
**Spec:** The owner's complete English localization, public release audit and safety requirements supplied for this task.

## Global constraints
- Work only on `dev/english-open-source-readiness` in an isolated development clone.
- Keep repository private; do not merge, force push, rewrite history, create a release, choose a final license, or deploy.
- Never write to the production project, private source data or private backup volumes.
- Preserve Arabic training/evaluation inputs, original conversations, actual corrections, schema keys and compatibility identifiers.
- Use generic public paths and synthetic examples; do not publish local backup details or private audit evidence.
- The owner selected mandatory ingest credentials by default with an explicit compatibility migration.

## Review focus
1. Browser requests with hostile or null Origin, forged Host, simple content types or missing protection must not read/mutate private data.
2. Hermes server-to-server compatibility must have an explicit, tested migration path without touching the running integration.
3. English chrome must not override Arabic data direction, alter text values or change training masks/normalization algorithms.
4. Error-message translations must not change machine-readable API codes or invalidate data contracts.
5. Historic personal details and actual review manifests remain historic even after working-tree cleanup; license approval and data rights are release gates.

## Tasks
- [x] Establish a baseline: copy private test fixtures into ignored development paths; online-snapshot SQLite; hash protected production datasets; run the complete suite.
- [x] Translate static UI and operator messages, switch chrome to English/LTR and keep Arabic text surfaces auto/RTL. Add regression coverage for both directions.
- [x] Translate Python/CLI messages and developer comments while preserving corpus values, actual curation data, protocol markers and Arabic-specific fixtures. Make developer paths portable.
- [x] Reproduce HTTP vulnerabilities using disposable servers, add failing regression cases, then enforce coherent Host/Origin/content-type/request authorization controls. Apply the owner-approved mandatory ingest policy and migration contract.
- [x] Translate and sanitize existing docs/plans; add installation, quick start, configuration, security, contribution, troubleshooting and restore guidance. Document MIT versus Apache-2.0 without adding LICENSE.
- [x] Audit all reachable history and current diff for credentials, personal details, machine paths, corpus/review manifests and backup disclosures. Keep sensitive evidence outside Git. Classify confirmed findings versus potential risks.
- [x] Run all tests, browser checks with synthetic Arabic input, data/mask processing checks, protected-source hash comparison and an explained Arabic-exception inventory.
- [x] Obtain fresh independent reviews of security and localization, resolve actionable findings, then commit/push only the development branch for review. Keep main and privacy unchanged.
- [x] Deliver an evidence-backed SAFE TO PUBLISH or NOT READY decision, remaining risks and rollback instructions. Do not merge or publish.

## Expanded request: installation and handover completion
- [x] Reconcile historical tracks and current source into PROJECT_STATUS.md, preserving superseded evidence.
- [x] Verify RED/GREEN for portable launcher selection, unsupported Python, safe setup and no-overwrite behavior.
- [x] Add shell, requirements, developer, database/migration, dataset/training, API and maintainer guides; contribution metadata and proposed NOTICE, no final license.
- [x] Make private-fixture prerequisites explicit and preserve the failed source-only baseline.
- [x] Rehearse fresh/repeated setup and launch/health/shutdown in temporary Windows and Ubuntu/WSL checkouts; verify protected hashes.
- [x] Review full candidate, scan privacy, commit and ordinary-push private review branch, verify a clean clone.
