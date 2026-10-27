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

## Goal 4 acceptance and failures

Exact52-file candidate: **64 passed / 50 subtests / zero skips**, 13.95s. Real browser PASS: selected JSONL download matches manifest SHA256, full archive denied, online SQLite/export backup, separate restore, original/correction/flag and all-row/file-hash equality, model/private routes remain503, clean shutdown. Concurrent real API preparation + backup produced a restorable snapshot.

Failed history: initial missing artifact/restore checks8 failures (including five file subtests); first implementation1 failure because path-denial ReviewError was incorrectly normalized into409 (fixed explicit exception preservation). Backup staging/incomplete-inventory regressions2 RED; fixed snapshot-registered selection and shared structural verification. Atomic publication subsequently introduced filename shadowing:6 failures, fixed archive_name/member_name separation. Initial collision probes were masked by that bug; controlled unowned-cleanup mutation on corrected names yielded1 expected failure, and actual guard passes. Bounded-read regression failed before size checks. Current existing-empty/nonempty destination, malformed ZIP/traversal, symlink/hardlink/path/hash, resource and ownership checks pass. Partial restore marker behavior is explicit; no generated package uploaded.

## Goal5 current visual/documentation evidence

Builder **9 passed /15 subtests**, including both independently reproduced SVG resource bypasses (two RED subtests retained). All eight real screenshots inspected for fictional-data accuracy/privacy and normal text/flag/hash rendering. Editable SVG XML valid; Chromium inline rendering desktop/narrow inspected; direct file:// was blocked by environment policy and is not claimed passed. Browser acceptance PASS includes full review/dataset/download/backup flow plus recovery into a different fresh candidate: copy validated data/exports BEFORE install, install preserves state, same-schema launch and actual browser/API readback. Mermaid source remains available; syntax/render checks and exact profile counts below complete this milestone. Windows is not inferred from Linux.

Final Goal5 profile68 files: **64 passed /50 subtests /zero skips**,14.93s. Builder after CSS image-set regression: **9 passed /16 subtests**; third SVG bypass reproduced RED before restricted CSS fix. Root97/candidate7 Markdown pages checked; links resolve. Mermaid12 parse/render and exact SVG regeneration PASS; desktop/narrow actual Chromium render visually inspected. Baseline270 retained/protected136 identical. Eight PNGs pinned verbatim after privacy/visual review.
