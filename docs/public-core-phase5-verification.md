# Phase 5 verification evidence

This is a current execution ledger, distinct from historical reports. Test environments are disposable/private; source and original evidence remain preserved. Final results supersede milestone counts without erasing failures.

## Baseline

Linux container: Python 3.12.14, SQLite 3.53.1; pytest 9.1.1 installed separately. Original source command: `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs` from the implementation checkout. Candidate command is the same **inside the exact 37-file baseline candidate**, whose manifest was built/verified from PR #3. Baseline original: **277 passed, 24 skipped, 68 subtests**, one existing return-value warning. Baseline exact candidate: **22 passed, 13 subtests, zero skips**, 1.36s. No private artifact is supplied; expected historical skips must remain explicit.

## Reproduction protocol

Builder tests run separately from original and exact-candidate suites. Always build into a new directory, verify pristine bytes, then run tests on a disposable copy. Preserve a pristine directory for deterministic comparison. New fixtures are independently fictional; do not reuse research cases. Browser acceptance uses actual HTTP/SQLite responses, never mock UI responses. Windows evidence requires actual hosted CI, not script inspection. Failed attempts are recorded here.

## Goal 1 regression history

Initial candidate tests reproduced five failing cases plus four failing malformed-type subtests against the old boundary. First fix: 28 passed / 18 subtests. An added generic-save/approve bypass test produced three failing subtests; status guards fixed it (30 passed / 28 subtests). Independent review then found missing lifecycle timestamps and reviewer mapping: fresh lifecycle/provenance tests produced four failures. Fixed candidate SQL timestamps, stored action reason, and explicitly mapped/preserved reviewer assertions. Final backend profile: **33 passed / 31 subtests**, zero skips, 1.80s (including restored-overlay refusal regression). Initial minimal UI now sends revision and only deliberately changed flags and prefills retained correction; complete browser workflow is Goal 2. No original source changes.

## Goal 2 current acceptance

44 selected candidate files. Exact Python suite: **37 passed, 31 subtests, zero skips**, 2.03s. `NODE_PATH=/workspace/mermaid-tools/node_modules node tests/browser.cjs .` inside the exact candidate: **PASS**, real Chromium154/puppeteer-core25.16.0. No mocked API responses; outgoing request was briefly held for a busy-control assertion, then sent to the real server. Browser covered conversation detail, user/context/original, correction and privacy, explicit approval and exclusion, original-preserving readback, second-client conflict, draft retention/reload, restart, accepted discard and narrow layout. No page script errors or active HTML payload.

RED/failed evidence retained privately: three missing context routes, missing-DB detail write probe, same-page dirty-loss browser regression. Intermediate browser attempts also failed on premature selector/state assertions, detached list nodes and OS TIME_WAIT during same-port restart; fixed test synchronization, saved-list completion state and explicit new test port. Repeated fresh profile finally passed. Independent review rechecked async/readonly fixes; no Critical/Important issues remain in this milestone.

## Goal 3 acceptance and retained failures

Exact49-file profile: **53 passed / 34 subtests / zero skips**, 7.87s. Real browser suite PASS for both contextual review and opt-in workshop → explicit approvals → readiness → local version → manifests/quality/holdout. Python coverage includes empty/tiny/valid, explicit demo type, duplicates, conflicting corrections, source staleness, exclusions/evaluation, private earlier context, manual privacy, symlink exportroot, manifest/file tamper, strict train/holdout masks, empty holdout and second-instance refusal. Read-only inspections preserve original rows and version hashes.

RED/failed attempts: initial dataset5 failures/1pass; first fix1 failure (two records were permitted by legacy under20 exception), then explicit candidate20 minimum. Independent additions initially4 failures: context leak, linked write root, incompatible holdout and an incomplete manual fixture. Corrected manual fixture reproduced its actual privacy bypass separately. Snapshot adapters twice caused4 integration failures (missing open, then text-mode encoding); fixed in-memory read interface. Training-user-mask/deferred-kind tests2 RED; second-server test RED because old secondprocess remained running; empty-holdout test1 RED. All corresponding current tests pass. Legacy private/full-archive distribution is not cleared by these checks.
