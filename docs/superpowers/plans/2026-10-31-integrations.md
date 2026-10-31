# Settings integrations implementation plan

> **For agentic workers:** Execute inline with superpowers:executing-plans; obtain a fresh whole-branch review using superpowers:requesting-code-review.

**Goal:** Safe Settings discovery, consented local runtime tests, and truthful BLOCKED Hermes status.

**Architecture:** `app/integrations.py` owns registry, bounded numeric-loopback transport, discovery, consent and serialized state. `app/server.py` preserves request security and delegates routes. `static/integrations.js` uses existing API/escaping helpers and theme-aware controls.

**Tech Stack:** Python standard library, Vanilla JS, existing pytest development runner.

**Spec:** [design](../specs/2026-10-31-integrations-design.md)

## Global constraints

- No external configuration/history/secret reads or service changes; no real service tests.
- No new dependencies, migrations, training actions, persistent consent, merge or installation.
- English UI/docs; preserve Arabic content and Host/Origin/CSRF.
- Hermes collection BLOCKED; local receiver verification never means external sender verification.

## Review focus

- Slow response and header/body abuse must be bounded in time and bytes.
- Credentials, proxies, redirects and endpoint overrides must never leave the trust boundary.
- Concurrent disconnect/test/selection must not permit generation after revocation.
- Stale models and auth failures must invalidate selection without inventing success.
- Hermes legacy/authenticated traffic must not reach parsing or storage.

### Task 1: Connector manager

Files: create `app/integrations.py`, `tests/test_integrations.py`.
Interfaces: `IntegrationManager.snapshot()`, `.discover()`, `.action(connector_id, action, payload)` return JSON-safe snapshots; `IntegrationError` provides code/status.

- [x] Write behavior tests for discovery, loopback transport, consent, synthetic payloads, failure classes, stale models and serialized verified disconnect; run and observe missing feature failure.
- [x] Implement fixed registry/transport and process-local locked state; metadata-only known-path discovery.
- [x] Run focused tests with only ephemeral fixture services; confirm no real service access.

### Task 2: HTTP and Settings

Files: modify `app/server.py`, `static/index.html`, `static/app.js`, `tests/test_http_security.py`; create `static/integrations.js`, `static/integrations.css`, `tests/test_integrations_http.py`, `tests/integrations-ui.test.cjs`.
Consumes: Task 1 manager interfaces. Produces: GET `/api/v1/integrations`, POST `/api/v1/integrations/discover`, POST `/api/v1/integrations/{id}/{connect|disconnect|select|test}`.

- [x] Write failing route/security/Hermes refusal and UI consent tests.
- [x] Delegate after existing security checks; block Hermes before body read; add Settings cards, accessible status, selection and confirmations using existing browser helpers.
- [x] Run route and UI tests; validate keyboard flow, escaping, errors, cancellation and no automatic generation.

### Task 3: Reviewable delivery

Files: update README, CHANGELOG, PROJECT_STATUS, SECURITY, API/configuration/Hermes documentation; add `docs/integrations.md`, `docs/integrations-windows-update.md`; regenerate API inventory.

- [x] Document actual behavior, unsafe historical instructions, API compatibility, blocked features and rollback.
- [x] Run compile, documentation, JavaScript and full Python suite; record exact results and skips.
- [x] Fresh security/correctness review, resolve material findings with regression proof.
- [ ] Commit/push feature branch and create PR with results; inspect CI and leave merge/installation pending owner approval.

## Execution record

Tasks 1 and 2 implemented with fixture unit/HTTP/controller proof. Whole-branch review findings fixed: selection-revision consent, mapped-drive/local mount refusal, total HTTP wire budget, truthful external state, and retirement of live acceptance. Task 3 verification also found the separate Core builder classification gate: update explicit exclusions for root-only feature files, repin selected modified files, and apply the same Hermes HTTP refusal to Core. This is a security/CI compatibility requirement, not an inference feature or publication approval for Core. Root final proof: 332 passed, 24 skipped, 68 subtests, one pre-existing warning; controller 5 passed; builder 11 passed/18 subtests. PR/CI and installation remain gated as documented.

Cross-platform follow-up: newer CPython trailer guards and partial headers exposed a Linux classification discrepancy. Added deterministic deadline regression and platform-independent trailer-byte fixture; total deadline now checked immediately after header parsing. Local full proof: 333 passed/24 skipped/68 subtests; hosted Core 74 passed/68 subtests on both platforms. PR #8 is open; final head CI is pending and merge remains owner-gated.
