# Chat review workflow — implementation, evidence and safe update

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](user-guide.md) for present operation.

Date: 2026-11-02 (owner time zone Asia/Riyadh). Base: PR20 `634e7a5414aa7e620f674f420adeda2d97f02c43`, reached through the independent `integration/pr19-pr20-local-20261102` branch. Fix branch: `fix/chat-review-workflow-20261102`. PR19 and PR20 remain Draft and unmerged; main is untouched. This owner-authorized local preview update is separate from release acceptance.

## Behavior and findings

- [UI changes](chat-ui-fixes.md): clear context/reply presets and Advanced controls, effective engine ceiling and unverified VRAM estimates, immutable saved settings, guarded Enter send, draft retention and DOM-only Markdown with exact raw view.
- [Collection audit](chat-dataset-context-audit.md): actual consented history travels into multi-turn SFT; single-turn remains available. Complete prior context is masked, only the reviewed final assistant is a target. Incomplete/unverifiable Chat segments remain reviewable and cannot be promoted/exported for training/evaluation. Collection stays OFF by default and after restart. No forced 60/40 quota or automatic training.
- No schema change, migrations, retrospective import or historical export rewrite. The existing seven migration files/registry are byte-preserved. Old Chat records without complete provenance are conservatively blocked from future training selection, never modified.

## Gemma/Ollama diagnosis

The UI previously used `textContent` only, which displays Markdown syntax literally. The new renderer is presentation-only: a small safe subset (headings, bold, inline/fenced code and lists), no HTML parsing, links, images, entity decoding or backslash-unescaping. The exact model text remains available and unchanged in history/review/dataset. Literal escaped Markdown remains literal.

The reported shape (`done=true`, `done_reason=stop`, 102 content characters, 1352 thinking characters, `eval_count=413`, reserve 999) is not by itself invalid. A regression fixture with that shape is accepted unchanged when prompt counts and identity match. Thinking is a separate Ollama field, discarded without storage; its tokens still consume the reserve.

Two synthetic-only calls on the existing Ollama 0.40.13 / gemma4-local:e4b established:

| Synthetic scenario | Measured/final prompt | Completion | Result |
|---|---|---|---|
| Short Arabic greeting | 38 / 38 | stop, 7 output, 11 content chars, no thinking | Accepted engine contract |
| Logic question | 56 / 56 | length, 999 output, 963 content chars, 2543 thinking chars | Correctly incomplete; cannot save |

A further full-workspace test on its own temporary database completed two synthetic real-Gemma turns at 8192/2048: prompt counts 33 then 56, output count 4 each, collection OFF and zero review rows. The first execution passed both turns but exposed an unclosed test-only SQLite handle during temporary cleanup; closing that handle made the final entire execution exit 0. No private Chat messages or database were used in those probes, and no runtime configuration/service was changed. The exact historical successful-stop refusal was **not reproduced**. Do not claim it fixed or attribute it to thinking without evidence. The old generic workspace error is now split into constant diagnostics for abnormal stop, invalid final text, prompt-count mismatch, context usage or tool output. The public `INCOMPLETE_RESPONSE` code and all fail-closed checks remain. Output-count type/range failures keep `INVALID_LIMIT`. Arabic/English messages are covered by catalog checks.

## Verification

Final local source checks (all commands exited 0):

| Check | Actual result |
|---|---|
| Windows Python 3.12.10 / pytest 9.1.1 | 697 passed, 32 skipped, 59 subtests passed |
| Ubuntu 24.04 / Python 3.12.3 | 696 passed, 33 skipped, 59 subtests passed |
| Node unit suites, Windows and Ubuntu | 37 passed on each platform |
| Windows Chromium Chat and new enhancements | Both scripts passed |
| Windows Chromium review restrictions, bilingual UI and accessibility | 35 passed |
| Core builder adversarial tests | 12 passed, 18 subtests passed |
| Core candidate build/verify | 73 classified/hashed files, passed; publication not approved |
| Core Python Windows | 75 passed, 3 symlink-capability skips, 68 subtests passed |
| Core Python Ubuntu | 78 passed, 68 subtests passed |
| Core harness Windows and Ubuntu | Passed |
| Core Chromium Windows (artifacts/backup/recovery/dataset/review) | Passed |
| Compile, documentation links/API inventory, Ubuntu shell syntax | Passed |
| Independent code review | No critical or important findings |

Windows skips: 22 private historical artifact tests (private data was not fetched), nine opt-in disposable-Ollama tests (no new model/binary instance started), one unavailable Windows symlink privilege. Ubuntu skips: the same 22 private and nine opt-in real-engine tests, plus two Windows-only checks. Ubuntu Chromium was not run because a native Linux browser/dependencies were unavailable; Windows Chromium covered the full browser flow. Memory estimates are not allocation proofs, and synthetic composition events do not certify every OS IME.

The first comprehensive run exposed an AI05 test expecting promotion of a mid-chat segment, now correctly refused by the new context invariant; that test now proves quarantine plus ordinary human review without training eligibility. It also caught a misplaced CI browser timeout, corrected before the final run. An old browser assertion expected a single description ID and was updated to validate both real accessibility descriptions. Initial restricted loopback failures and these earlier failures remain in local evidence logs; they are not counted as final passes.

Source/registry hashes were reviewed and repinned for the two changed protected Chat files and shared Core dependencies. The new browser suite is wired into future hosted checks without changing the Draft-job skip policy. Initial restricted Windows baseline failed 43 loopback calls; rerunning with local network permission passed all 96 baseline Chat tests. New root tests first showed three expected failures, then passed after fixes. Agent audit evidence records the frontend/backend red-to-green checks. These are local checks, **not GitHub Actions green**. Hosted Actions credit is exhausted and no manual run or Ready-for-review is requested.

## Safe persistent Windows upgrade

Target: `%USERPROFILE%\NajdiLab-PR19-20-Local`, URL `http://127.0.0.1:8870`. The installation contains real user data. Tests use separate temporary roots only.

Before changing source: require clean tracked source at the expected old SHA; compare all seven migration sources/registry; verify exact listener PID plus creation time and command line; verify no active Chat request; stop only this owned instance. A private backup must include a SQLite online-backup snapshot with full `integrity_check`, data, exports, datasets, existing backups, config, .env and launcher files, plus a git bundle for the old source. Verify SHA-256 of every copied file and logical database digest. Do not upload backup manifests, data or settings to GitHub.

Upgrade only the source by fast-forwarding the separate fix branch, update the launcher SHA pin, run its read-only database preflight, and restart using the existing hidden launcher. The launcher still refuses dirty source or a migration mismatch before server startup. With an identical applied registry there are no pending SQL migrations; none is replayed. Verify health points at the same database, collection is OFF, source SHA matches, startup is idle, database integrity and logical digest match the pre-upgrade snapshot. Browser smoke is read-only; do not send/collect into the user's database for testing.

Rollback: stop only the recorded owned instance; switch source to the original integration branch at `634e7a5414aa7e620f674f420adeda2d97f02c43`, restore the saved launcher/README/preflight files, perform read-only preflight, and restart. **Do not overwrite or restore the database automatically.** The source change needs no schema rollback. If integrity or provenance checks fail, keep the service stopped and preserve all files for review. Old source restores the previous weaker incomplete-context export behavior, so review privacy restrictions before launching or exporting.

The guarded deployment outcome, installed SHA and verification will be recorded in the PR20 follow-up comment and the private installation README after upgrade. A private manifest under the installation upgrade-backups directory records backup location/hashes; it is never published. This source record alone does not claim the installed upgrade succeeded.
