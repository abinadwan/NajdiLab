# Native capture evidence and limitations — 2026-10-31

**No native capture PASS is claimed for any application.** The implementation adds metadata diagnostics and fail-closed consent/UI/API guards; it does not implement a source reader, watcher, poller, extraction/privacy pipeline, deduplication cursor or native queue importer. Research found no end-to-end mechanism demonstrated safe under the untouched-source requirements. [Research and exact source pins](native-capture-research.md) explain the limitations. [Owner acceptance](native-capture-windows-acceptance.md) remains separate and NOT TESTED.

## Phase A matrix

PASS below means the stated synthetic guard/diagnostic check passed, never that a conversation was captured. BLOCKED means no verified collector can exercise that positive capture requirement. NOT TESTED means installed-app compatibility/acceptance was deliberately not attempted. No real conversation data was used.

| Required case | Hermes | LM Studio | Ollama | Evidence / practical scope |
|---|---|---|---|---|
| 1. Discovery | PASS, metadata fixtures | PASS, metadata fixtures | PASS, Windows-path metadata fixture | Real temporary source paths; no installed app files; Linux desktop database not invented |
| 2. Unsupported version/format | PASS, refusal | PASS, refusal | PASS, refusal | All versions remain unverified/blocked; plausible SQLite and unknown schema are not parsed or called compatible |
| 3. Read-only source access | PASS, metadata only | PASS, metadata only | PASS, metadata only | Content opens/enumeration/SQLite calls forbidden by test guard; source DB/JSON and synthetic WAL/SHM bytes/mtime preserved; no source SQL or snapshots |
| 4. Connection and consent | PASS, refusal guard | PASS, refusal guard | PASS, refusal guard | Exact `approved:true` plus CSRF/Origin. Runtime consent cannot authorize native capture; native connect still returns 409 |
| 5. Detect new completed turns | BLOCKED | BLOCKED | BLOCKED | No supported capture mechanism; no timer or model inference substitutes |
| 6. Extract correct pair | BLOCKED | BLOCKED | BLOCKED | No fabricated source format/extractor or positive import fixture |
| 7. Privacy filtering | PASS, content access refusal; extraction BLOCKED | Same | Same | Source content is excluded entirely, including synthetic secret/history sentinels. No claim of implemented text redaction/filtering |
| 8. Duplicate prevention | BLOCKED | BLOCKED | BLOCKED | No imports/cursor exist; existing manual-ingest idempotency is not native capture proof |
| 9. Review queue persistence | PASS, existing queue preserved; capture persistence BLOCKED | Same | Same | Real isolated NajdiLab SQLite item remains PENDING / training_eligible=0; no native item inserted |
| 10. Restart/recovery | PASS, remains OFF | PASS, remains OFF | PASS, remains OFF | New manager has no persisted consent/path/cursor/backfill; positive collector recovery BLOCKED |
| 11. Disable collection | PASS, OFF invariant | PASS, OFF invariant | PASS, OFF invariant | Approved disable acknowledges local OFF, never reports previously active capture |
| 12. Complete disconnect | PASS, local OFF | PASS, local OFF | PASS, local OFF | No collector exists; native/runtime disconnect cannot claim external process/sender stop |
| 13. Missing/inaccessible source | PASS | PASS | PASS | Stable sanitized statuses, no paths/error details leaked; unsafe fallback refused |
| 14. Concurrent writes | PASS, metadata/guard safety; capture consistency BLOCKED | Same | Same | Synthetic source byte changes do not trigger content reads/import. Windows ancestor-junction and Linux pinned-parent regressions test path redirection separately |
| 15. Corrupt/unexpected records | PASS, no content/parser access | Same | Same | Unknown/corrupt data never authorizes capture; no corruption repair/migration is attempted |
| 16. Existing regressions | Run full root/Node/Core checks | Same shared gate | Same shared gate | Exact final command counts and CI links recorded below/in PR; unavailable historical fixtures remain explicit |

Installed versions, the owner's actual database schemas and a real original-application completed pair reaching review are **NOT TESTED** for all three. Native capture status is BLOCKED/UNSUPPORTED for all three; none becomes PASS from mock/runtime connectivity.

## Test mechanisms and security proof

- `tests/test_native_capture.py`: temporary files/SQLite with synthetic-only content; passive snapshots, metadata discovery, native consent combinations, refusal under unknown/corrupt content, manual fallback, path/type/URI/UNC/device/ADS/link constraints, permission errors, concurrent writes, restart, returned-state tampering, no Linux desktop inference, and existing own review preservation.
- Windows path lookup resolves a fixed drive's local volume object and uses metadata-only `NtCreateFile` with kernel reparse refusal; a synthetic ancestor is replaced with a junction immediately before lookup and must be rejected. It uses share-read/write/delete, no source content read/write or SQLite lock. Source-independent platform test rejects unknown metadata backends.
- Linux metadata traversal uses `openat2` with O_PATH and RESOLVE_BENEATH/NO_SYMLINKS/NO_MAGICLINKS/NO_XDEV; a synthetic parent replacement cannot redirect the child lookup. Unsupported metadata primitives/platforms fail closed. No fallback to race-prone full-path stat is allowed.
- `tests/test_integrations_http.py`: ephemeral NajdiLab/fake runtime servers; direct native enable/connect refusal, separate consent, CSRF/Origin, metadata path selection, OFF/disconnect and retained Hermes early-body refusal. No installed service is contacted.
- `tests/integrations-ui.test.cjs`: eight controller cases include native capability/OFF rendering, separate confirmation, no request for unsupported enable, path fallback only after missing detection, escaped untrusted values and independent runtime consent. These are controller tests, not full browser/owner acceptance.
- Existing source security, runtime synthetic tests and manual ingest tests remain distinct. No test enables Hermes webhook, reads WhatsApp/Baileys/session/config state, extracts a desktop token, scans dynamic ports or changes service routing.

## Commands and observed results

Baseline at PR #8 head: `python -m pytest -q tests -rs` on Windows/Python 3.12 returned **333 passed, 24 skipped, 68 subtests, one existing warning**. The skips comprise unavailable private historical artifacts and an unavailable symlink privilege; warning is the pre-existing return value in `test_training_plan_mismatch_unit.py::test_smoke_test_logic`.

Focused new guards/HTTP after path-race hardening: **96 passed, 1 platform-specific skip**. Node controller: **8 passed**. An initial Windows HTTP regression run had a loopback `WinError 10053` connection abort during an early security refusal; the subsequent focused guard/HTTP run passed without weakening the security checks. An initial junction test fixture used incorrect shell quoting; it was corrected to native PowerShell creation confined to its own temporary paths, and the real Windows junction refusal passed. Restricted filesystem redirection may refuse low-level metadata lookups; the fixture proof runs with access to its own temporary paths, never third-party app files. Final full-suite, packaging and Windows/Linux CI results are recorded in the PR.

No owner acceptance, deployment, main merge, installed pull, data deletion, source migration, service restart or privilege/security-setting change was performed. See [safe update/rollback](integrations-windows-update.md) and [acceptance gate](native-capture-windows-acceptance.md).

Path review also identified a Linux mount-resolution race beyond symlink refusal. The final backend therefore uses kernel openat2 NO_XDEV/NO_SYMLINKS/NO_MAGICLINKS/BENEATH, with no weaker fallback; a Linux-only regression rejects a mount crossing even if the advisory locality result is stale. Unsupported primitives/mount crossings remain refused. Windows junction proof runs locally; Linux kernel-specific cases run in hosted Linux CI.

Final local Windows/Python 3.12 proof after all guard/path changes and fixture transport repair: `python -m pytest -q tests -rs` — **425 passed, 26 skipped, 68 subtests, one pre-existing warning**. Skips: 23 unavailable private historical artifacts, one unavailable symlink privilege, two Linux-specific kernel metadata cases. `node --test tests/integrations-ui.test.cjs` — **8 passed**. Source prerequisites, compileall, JavaScript syntax, 108-file Markdown/generated API checks and final diff whitespace checks passed. Core builder **11 passed / 18 subtests**; build/manifest verification **74 files**, with selected Core files unchanged from PR #8.

The repeated early-refusal Windows TCP reset was traced to fixture headers/body being written separately while the server legitimately closed at the security boundary. Disposable test clients now batch their small header/body fixture output in one write, without retries, response stubs or changes to server security. Headers-only Hermes tests still prove refusal before a body is sent. Both security/native HTTP suites then passed (25 tests / 48 subtests), followed by the complete green suite above. Hosted final-head Windows/Linux results belong in the PR; native capture/owner acceptance remain BLOCKED/NOT TESTED regardless of CI success.
