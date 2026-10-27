# Phase 5 verification evidence

Current result: **ENGINEERING PASS — RELEASE GATES REMAIN**. Final exact sourcee03a640:74 selected files, manifestcc94baf399dd66056d8a64b9150237cf5d14ffe651cd67fd9839547138c94044; hosted Windows/Ubuntu73PASS/68subtests, builder11/18 and actual browser/harness PASS. [Authoritative final table](#final-exact-profile-acceptance--authoritative-current-results). Earlier intermediate/pending/failing statements below are chronological historical checkpoints, retained for traceability. Publication remains blocked.

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

## Goal6 local and hosted acceptance ledger

Local exact74-file profile: **70 passed /62 subtests /zero skips**,16.59s. Builder **11 passed /18 subtests**. Browser/harness PASS on the preceding71-file same runtime/UI profile; final expanded profile acceptance and hosted results follow. Source-only negative guard fixtures are fictional and never invoke original startup. Unsupported-method7subtest RED, runtime-pytest2subtest RED, missing guard-module RED, initial overbroad hidden-file rejection1FAIL/42errors, and shell-wrapper omission1FAIL/69PASS are retained; fixed without weakening containment. Original suite fresh **277 passed /24 skipped /68 subtests**, one existing return-value warning,5.49s. Hosted Windows/Ubuntu status remains pending and is not PASS yet.

Independent Goal6 code/isolation review accepted with no Critical/Important findings. Final74-file local real browser/harness PASS including separate restored candidate launch. Used profiles with caches correctly fail pristine verify; fresh profiles verify. Hosted matrix still pending. Goal6 code commit below supplies executable CI evidence, not inferred Windows success.

### Hosted attempt1 — retained failure, not acceptance

Commit ea2347f: [candidate run40527390859](https://github.com/abinadwan/NajdiLab/actions/runs/40527390859): Ubuntu70PASS/62subtests plus actual browser/harness PASS; Windows65PASS/5FAIL/62subtests. Three failures are test JSONL reads/writes using the Windows default cp1252 instead of explicit UTF-8. Two restore failures expose only the controlled CLI refusal; underlying cause is **not yet established**. Added direct-function subprocess diagnostics on the same disposable restore path, retaining actual CLI acceptance in the browser; no product change without root-cause evidence. Source run[40527390894](https://github.com/abinadwan/NajdiLab/actions/runs/40527390894) PASS: Ubuntu277/24SKIP/68subtests, Windows278/23SKIP/68subtests, existing warning. Runtime observations: UbuntuPython3.12.15/SQLite3.45.1; WindowsPython3.12.10/SQLite3.49.1. No critical test skipped to obtain green.

### Hosted attempt2 and recovery root cause

[Run40528604620](https://github.com/abinadwan/NajdiLab/actions/runs/40528604620), commit78dcedd: Ubuntu candidate/browser PASS; Windows68PASS/2FAIL/62subtests,104.31s. Explicit UTF-8 fixed all three encoding failures. Direct restore API diagnostic traced rejection to checked_version's strict canonical path comparison on its newly allocated temporary staging path; no malformed archive or privacy gate failure. A real nonlinked filesystem alias regression reproduces DATASET_PATH_DENIED on Linux (RED), independently of availability of Windows short names. Normalize only the program's newly owned staging root after creation; retain output-parent symlink/junction checks, exclusive destination claiming, byte/manifest checks and all link denials. Full hosted acceptance remains pending the fix run.

## Goal8 — first-time-user acceptance observations (pre-final-review checkpoint)

Exact final runtime/source profile:74 files + MANIFEST, SHA256 e6a80cf092d5a6ad519af318f21a0c744930bed712e36f00c396f57b45b52083, selected source commit4513686. Local fresh tests71PASS/62subtests/zeroSKIP,19.50s; real browser/harness PASS. Four browser acceptance groups cover the following22 required steps; these are assertion mappings, not22 separately counted pytest tests. Batch fixture approvals use real authenticated API requests after individual browser approval is proven. No fake UI/API response, original research or training result is used.

| Step | Actual observation/assertion | Local result |
|---|---|---|
| 1 Fresh install | Manifest-selected copy, offline installer success, no DB before opt-in/launch | PASS |
| 2 Launch without private data | Candidate-local loopback health/session, no private modules | PASS |
| 3 Explicit synthetic examples | --confirm-disposable --workshop,32 pending fictional conversations;3 independent browser fixtures | PASS |
| 4 Real browser | Chromium navigates actual server and Overview | PASS |
| 5 Conversation/context | Conversations detail and review context show fictional user question and original | PASS |
| 6 Correction | Real Arabic editor and Save correction request | PASS |
| 7 Original unchanged | Browser original equality, review source hash regression and DB-row comparison | PASS |
| 8 Explicit flag | Browser selects personal-information flag; correction edit itself changes no unrelated flag | PASS |
| 9 Flag persistence | API/UI readback and restart confirm flag1/training0 | PASS |
| 10 Stale update | Second client real save, stale browser409 retains draft; atomic/no-write unit integration regressions | PASS |
| 11 Approval | Individual real browser approval; remaining independent workshop fixtures explicitly approved via real API | PASS |
| 12 Exclusion | Browser excludes fictional shelfB with reason; persisted after restart | PASS |
| 13 Readiness | Initial blocked state, explicit demo inclusion, actual readiness/dedup/diagnostics | PASS |
| 14 Prepare | Real UI preparation after sufficient final eligible records and unchanged split gates | PASS |
| 15 Version evidence | Actual manifest SHA/counts, quality warnings, balance/holdout API inspection | PASS |
| 16 Selected retrieval | Browser-selected sft.jsonl bytes match manifest; full archive403 | PASS |
| 17 Backup | Candidate CLI creates coherent online snapshot of synthetic current state | PASS |
| 18 Separate restore | CLI restores into new directory; exclusive/no-overwrite/link/ZIP checks tested separately | PASS |
| 19 Integrity | SQLite integrity/FKs, conversation/message/review/tag/version rows and every dataset file hash equal; fresh source resumes restored state | PASS |
| 20 Private/training unavailable | Actual training/models/acquire requests503; historical routes/imports excluded | PASS |
| 21 Shutdown | Only owned disposable server process exits, temporary state cleaned | PASS |
| 22 Preservation boundary | Manifest-selected source, new temporary storage, original baseline/protected/media hashes unchanged; production never accessed | PASS within accessible scope |

Unobservable original private datasets/checkpoints/frozen versions remain NOT_VERIFIED. No production-integrity comparison is claimed. Browser tested desktop1440×1000,390px no horizontal page overflow, long Arabic editing, inert HTML, empty/blocked/conflict/saved states and actual restart/recovery. Diagram/long technical tables can require zoom or scrolling. Not every browser/OS combination is certified; no public-network hosting/RBAC or automatic PII detection.

## Final verification commands

From engineering checkout: python public_source/build.py --output NEW-SEPARATE-DIR; python public_source/build.py --verify PRISTINE-DIR; python -m pytest -q public_source/tests/test_builder.py; python scripts/check_docs.py. In the exact built candidate: python -m pytest -q tests -rs; node tests/harness.cjs; node tests/browser.cjs . with separately installed puppeteer-core and a real browser (NODE_PATH/NAJDILAB_BROWSER_EXECUTABLE). Original suite runs independently from engineering root: python -m pytest -q tests -rs. Never run candidate browser acceptance against the original checkout; guards refuse it.

## Remaining verification limits

Python3.11/SQLite3.24 are enforced floors, not freshly tested combinations. WSL2/macOS and other browsers are NOT_VERIFIED. Original-source private artifacts remain explicit SKIP; Linux-only PowerShell skip is covered by the actual Windows job. No model training/runtime/export/deployment, live Ingest transition, proposed migration or multi-user/public-network hardening was exercised. HMAC has no freshness/replay protection; review identity is asserted, not authenticated RBAC. No complete append-only event log or signed build authenticity is claimed. Advisory lock protects supported same-root server instances, not arbitrary external writers. Source-only privacy patterns and manifest checks do not certify ownership or rights.

### Goal9 additional native-auth finding — do not conceal late failures

Independent final review agreed that inherited NAJDILAB_ALLOW_LEGACY_INGEST=1 is an Important candidate-contract gap, although it is not a remote privilege escalation under local operator trust. Harnesses removed that environment flag, so defaults alone did not exercise it. Raw malformed-JSON requests produced2RED subtests (400instead of503); actual disposable API requests with/without credentials produced4RED subtests plus changed-row failure, proving a real unauthenticated fictional write. Candidate-only body guard now refuses the configuration with503 LEGACY_INGEST_DISABLED before shared auth/JSON/DB, without mutating os.environ in request threads or editing the protected helper. Both native paths and unchanged conversation/message/review counts are tested. Final profile acceptance must be rerun; prior71-pass Windows/Ubuntu result remains historical for4513686, not current final acceptance.

Legacy-refusal fix local exact74-file profile: **73 passed /68 subtests /zero skips**,19.54s; builder11PASS/18subtests. Real-count assertions prove no native conversation/message/review writes with override1, whether unauthenticated or correctly credentialed. Hosted retest and independent review follow before closure.

## Final exact-profile acceptance — authoritative current results

Selected source **e03a640c08554ee8e171faeed0fb8686f324dbfa**, manifest **cc94baf399dd66056d8a64b9150237cf5d14ffe651cd67fd9839547138c94044**,74 selected files plus generated MANIFEST.json. Only the final measured screenshot caption differs from10907b1; runtime/UI images are unchanged, and the exact final profile was rerun below. Prior failed/partial checkpoints above remain historical evidence. Current verdict: **ENGINEERING PASS — RELEASE GATES REMAIN**.

| Layer / actual command | Environment | PASS | FAIL | SKIP | Evidence |
|---|---|---|---|---|---|
| Exact candidate pytest tests | ubuntu-latest;Python3.12.15/SQLite3.45.1 |73 +68subtests |0 |0 |[Run40532489241](https://github.com/abinadwan/NajdiLab/actions/runs/40532489241);21.34s |
| Exact candidate pytest tests | windows-latest;Python3.12.10/SQLite3.49.1 |73 +68subtests |0 |0 |[Same run](https://github.com/abinadwan/NajdiLab/actions/runs/40532489241);84.01s |
| Builder pytest test_builder.py | Ubuntu |11 +18subtests |0 |0 |Same run;4.37s |
| Builder pytest test_builder.py | Windows |11 +18subtests |0 |0 |Same run;9.22s |
| Node harness + real browser.cjs | Windows and Ubuntu separately |4 workflow groups each; all22 mapped steps |0 |0 |Same run: actual review/dataset/download/backup/restore/resume/shutdown |
| Original-source pytest tests | Ubuntu |277 +68subtests |0 |24 |[Source40532489260](https://github.com/abinadwan/NajdiLab/actions/runs/40532489260); existing return-value warning |
| Original-source pytest tests | Windows |278 +68subtests |0 |23 |Same source run; existing return-value warning |
| Final local code profile pytest | Linux container;Python3.12.14/SQLite3.53.1 |73 +68subtests |0 |0 |18.68s; Chromium154.0.8037.57/Node24.19.0 browser+harness PASS on10907b1 |
| Documentation | Engineering root / exact Core |98 /7 Markdown files |0 |0 |Local links/API inventory; final SVG generator/XML/Mermaid parse+render, actual screenshots |
| Isolation/privacy/determinism | Final74-file snapshot |PASS |0 |0 within defined scan |Pristine verify, exact hashes/imports,2 identical builds, tamper/private-path negative tests |
| Protected preservation | Starting270 paths, protected136, original media12 |PASS |0 |0 accessible hashes |Private starting-byte baseline; original private artifact content NOT_VERIFIED |

Candidate Python breakdown (disjoint73):18 pure clean-export/quality tests;55 HTTP/process/filesystem/install acceptance tests. Per-file counts: artifacts12,context5,contract1,datasets15,installation3,reviews13,security6,clean-export15,dataset-quality3. Security boundary6/review13/artifact12 are overlapping security-focused subsets of the73, not31 additional tests. Subtests are reported separately, not added to pytest case counts. Browser groups are assertion-driven workflows, not a fabricated pytest count.

The23 absent-private-artifact skips in the original suite are not passes; Linux's additional Windows PowerShell check is skipped only there and executed by the actual Windows original/candidate jobs. No candidate P0 gate is skipped. WSL2/production/original private datasets are NOT_VERIFIED, not tested by hosted Windows or Ubuntu. Historical runs40527390859 (Windows5FAIL),40528604620 (Windows2FAIL), initial REDs and successful pre-final-review4513686 remain retained.

Late P5-31 native-auth guard is independently reviewed and passes real no-write integration on both OSes; P5-29 restore alias is verified through real CLI/browser recovery on both. No Critical/High engineering finding remains open. P5-05 ownership/privacy/history/license/publication remains BLOCKED. [Rights/inventory](public-core-phase5-rights.md) separates technical/privacy scan success from legal approval.

Pristine inspection snapshot remains private/outside source. Its source/hash inventory matches the current policy and rights table; original Git is absent. No binary/model/archive package is uploaded, active license created, private source edited or training performed. Evidence-only commits do not alter selected bytes; PR#4 checks repeat the same final manifest and log its safe SHA256/count. Final delivery links reference the actual metadata-head run as well.
