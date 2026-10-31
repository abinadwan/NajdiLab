# Native capture diagnostics implementation plan

> **For agentic workers:** execute inline with superpowers:executing-plans and a fresh final safety review.

**Goal:** investigate native capture honestly and expose only verified, zero-change capabilities, preserving fail-closed behavior.

**Architecture:** reuse the PR #8 integration manager and browser API/security helpers. Consolidate local metadata validation in `app/local_sources.py`; `app/native_capture.py` owns native capability/discovery/consent refusal. No collector is enabled without completed-turn and acquisition proof.

**Tech stack:** Python standard library, Vanilla JS, existing pytest/Node CI.

**Spec:** [design](../specs/2026-10-31-native-capture-design.md).

## Global constraints

- No installed app/config/service/database/traffic changes, real chat development data, or unknown history reads.
- Content-free discovery; native collection OFF; native runtime tests are not capture proof.
- Preserve Host/Origin/CSRF and blocked Hermes HTTP receivers.
- Separate PR stacked on open PR #8; no merge, installed pull or owner acceptance claim.

## Review focus

- Metadata paths must reject remote/device/alternate-stream/link escapes before content access.
- A manual path fallback cannot imply version/schema verification or authorize collection.
- Direct API callers must not bypass the visible blocked capture control.
- Failures, restart, disable and disconnect must leave existing review data and source files intact.
- Distinguish guard/diagnostic PASS from actual native capture, and researched versions from installed versions.

### Task 1: Evidence and read-only diagnostics

Files: `app/local_sources.py`, `app/native_capture.py`, `app/integrations.py`, `tests/test_native_capture.py`, relevant existing integration tests.

- [x] Complete independent primary-source API/event/storage investigation and record pins/blockers.
- [x] Write failing synthetic tests for per-app metadata discovery, consent refusal, path handling, source/queue immutability, unknown/corrupt input, restart and concurrent changes.
- [x] Implement shared metadata-only validation and native diagnostic snapshots/actions, with capture disabled and refusals server-side.
- [x] Run focused tests and preserve existing integration behavior.

### Task 2: Settings and HTTP

Files: `app/server.py`, `static/integrations.js`, `static/integrations.css`, `tests/test_integrations_http.py`, `tests/integrations-ui.test.cjs`.

- [x] Write failing HTTP/controller tests for native capability status, separate consent, blocked enable/connect, fallback path and local disable/disconnect.
- [x] Add Settings fields/actions using existing escaping/API/theme patterns; no terminal/config steps, uploads or fake success.
- [x] Verify existing runtime actions and fail-closed Hermes ingress regressions.

### Task 3: Proof and reviewable delivery

Files: README, CHANGELOG, status, architecture, security/privacy/integration docs, research/results, Windows acceptance/update/rollback, generated API inventory, Core policy classifications.

- [x] Document exact capability matrix and all 16 requested test categories; mark unavailable capture evidence BLOCKED/NOT TESTED.
- [x] Run root/controller/docs/compile and Core checks; preserve historical fixture/environment limitations explicitly.
- [x] Fresh safety review; fix material findings with regression proof.
- [ ] Push separate branch/open stacked PR, verify final Windows/Linux CI; no merge or owner acceptance.

## Execution record

All three source investigations completed independently; no end-to-end zero-change native collector proven. Implemented capability/metadata/consent guards only, not positive collection. Windows ancestor-junction and Linux mount/link races addressed with kernel-enforced lookup; unknown metadata primitives fail closed. Existing Windows rejection-test transport race repaired only in disposable fixture client. Final local root proof 425 passed/26 skipped/68 subtests/one pre-existing warning; controller 8 passed, Core builder 11 passed/18 subtests and 74-file build/verify. Owner compatibility/acceptance NOT TESTED. PR/CI pending; no main merge or installed-app operation.
