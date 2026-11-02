# Chat Experience V2 and NajdiLab Native — development log

| | |
|---|---|
| Branch | `feature/chat-experience-v2` |
| Based on | `integration/pr19-pr20-local-20261102` at `634e7a5414aa7e620f674f420adeda2d97f02c43` (verified on GitHub before branching) |
| Merge state | Not merged. Draft PR only. `main`, PR #19 and PR #20 are untouched. |
| Data used | Synthetic only. No real conversation, model or installed instance was read, changed or deleted. |
| Started | 2026-11-02 |

## Baseline (before any change, on `634e7a5`)

| Suite | Result |
|---|---|
| `python -m pytest -q tests` | 673 passed, 33 skipped, 0 failed |
| Node unit tests (6 files, CI list) | 29 passed, 0 failed |
| Chromium: `chat-browser.cjs` | PASS |
| Chromium: review-restrictions / i18n / a11y | 12/12, 10/10, 13/13 |

The 33 skips are private historical artifacts that are not in the repository (Phase 3.8/3.9 datasets and reports) and the real-Ollama tests; they are skips, not passes.

## Plan and dependency order

1. Data layer: migration 008, titles, pin, archive/restore, search, permanent deletion.
2. Streaming, thinking, timings, completion diagnostics, presets (needs 1 for titles/activity).
3. NajdiLab Native (needs 2 for streaming and the engine interface).
4. UI V2 (needs 1–3).
5. Dataset segments (built into 2, verified against the export path).
6. README restoration (owner task RESTORE-README), documentation, test log, Draft PR.
7. Local permanent installation update — **blocked**, see [Local installation](#local-installation-update).

## 1. Session data, titles, archive/restore, permanent deletion

**Requirement.** ChatGPT-like history: readable titles, rename, search, last-activity order, date groups, pin, archive/restore, and a real permanent delete distinct from archive.

**Files.** `migrations/008_chat_experience_v2.sql`, `migrations/registry.json`, `app/chat_history.py`, `app/chat_workspace.py`, `app/chat_deletion.py`, `app/server.py`.

**Design decisions.**
- SQLite cannot change the `provider` CHECK constraint (needed for `native`), so 008 rebuilds `chat_sessions` the same way 004 rebuilt `reviews`: counts and a row-by-row comparison are asserted inside the transaction before the old table is dropped; the trigger that names the table is dropped and recreated unchanged; foreign keys are checked by tests afterwards.
- New columns are nullable so pre-V2 inserts keep working; no title, pin or prior status is invented for existing rows. Legacy archived rows restore as `OPEN` (send-time gates still apply).
- Titles are suggested locally from the first user message (markup stripped, cut at a word boundary, 60 characters). Rename and pin do not change the send revision, so they cannot stale an in-flight turn.
- Permanent deletion scope, redaction where immutable audit events exist, `secure_delete` + WAL truncation, refusal when exported, backups counted not touched, content-free tombstones: see [data retention](../data-retention.md#permanent-chat-deletion-chat-experience-v2).

**Sources and licenses.** None (original code).

**Issues found and fixed during the work.**
- Deleting the review conversation before `chat_turns` failed on the `review_conversation_id` foreign key; chat rows are now deleted first (caught by test).
- First draft of 008 made `last_activity_at` NOT NULL and required `archived_at` for archived rows; an existing pagination test that inserts rows the pre-V2 way failed, so both were relaxed (compatibility over strictness).
- `provider` given as a list raised `TypeError`; an existing test caught it; now a clean `UNKNOWN_PROVIDER` refusal.

**Rollback.** See [Rollback](#rollback).

## 2. Streaming, thinking, timings and diagnostics

**Files.** `app/integrations.py` (`request_stream`, optional request headers, non-consuming `peek` for chunked reads), `app/chat_engine.py`, `app/chat_engine_worker.py`, `app/chat_workspace.py`, `app/server.py` (`send-stream` NDJSON route, `/chat/presets`, `check` in error payloads), `app/hardware.py` (4096 tier).

**Design decisions.**
- One NDJSON stream per turn over the existing local HTTP server (no new dependency, same Host/Origin/CSRF checks). Streamed text is display-only; the commit path and every completion check are unchanged, so streaming cannot weaken "no partial or truncated reply is saved".
- Ollama and LM Studio streams are parsed separately (Ollama NDJSON with a single final `done`; LM Studio SDK fragments relayed by the helper process; llama-server SSE). No assumption that they are alike.
- Thinking is a separate channel end to end. It is never written to the database, logs or collected data (tests read the raw database bytes).
- `INCOMPLETE_RESPONSE` now carries a fixed `check` naming the failed predicate; the user message and code are unchanged. Diagnosis of the Gemma 4 report: [chat workspace](../chat-workspace.md#incomplete_response-diagnosis).
- Latency: the per-turn Ollama overflow-refusal proof is reused for 10 minutes per port/version/digest/budget; identity and real context are still checked every turn. Timings are returned per phase without text.
- Context presets Light/Balanced/Long are offered in the UI and at `/api/v1/chat/presets`; custom values stay available within engine limits.

**Protected files.** `chat_engine.py`, `chat_engine_worker.py`, `chat_workspace.py` and `integrations.py` are hash-pinned in `docs/cleanup-inventory.json` by `tests/test_dataset_boundary.py`. They had to change for streaming; the pins were updated deliberately after review of the diff. **Reviewers should treat these four files as security-sensitive.**

**Issues found and fixed.** `http.client` needs `peek` for chunked `readline`; the bounded reader lacked it (found against the real llama-server). The worker event queue held 4 items and dropped on overflow; it now blocks instead of dropping.

## 3. NajdiLab Native

**Files.** `app/native_runtime.py`, `app/gguf.py`, `app/server.py`, `docs/native-runtime.md`.

**Design.** Use llama.cpp's `llama-server` as an **owner-supplied external program** (MIT). It already provides exact template rendering and tokenization (`/apply-template`, `/tokenize`), refuses oversized prompts with `--no-context-shift`, reports full `usage.prompt_tokens` even with prompt caching, separates reasoning (`--reasoning-format deepseek`) and streams over SSE. Binding a Python llama.cpp library instead would have added a native dependency and a build step to NajdiLab. Details and limits: [native runtime](../native-runtime.md).

**Sources and licenses.** llama.cpp tag `b12059`, commit `1b6935b`, MIT — external tool only; no code copied. The test binary was built from source in a temporary directory and not committed. [THIRD_PARTY_ATTRIBUTION.md](../THIRD_PARTY_ATTRIBUTION.md).

**Tested for real** (Linux, CPU, synthetic GGUF): start, exact admission, streaming, stop during generation, wrong context, changed model file, stopped runtime, API key required, loopback only. **Not tested:** Windows, any GPU, RTX 5070, real models, thinking-capable templates.

## 4. UI V2

**Files.** `static/index.html` (chat view), `static/chat.js` (rewritten), `static/chat.css` (rewritten), `static/chat-markdown.js` (new), `static/i18n-ar.js` (+235 entries and one pattern).

**Design.** Collapsible sidebar with date groups and per-chat menu; a *New chat* dialog with presets and a budget breakdown; heavy settings moved to a drawer (conversation details, device/model tables, NajdiLab Native). Streaming text grows with `Text.appendData`, so the conversation is not rebuilt per token. Thinking opens while the model thinks and collapses when the answer starts, unless the user toggled it. Enter sends; Shift+Enter, composition (`isComposing`, keyCode 229) and modifiers never send; `pending` is set synchronously so repeated Enter cannot duplicate a request. Device and model values are labelled *Measured*, *Reported by the runtime*, *Estimate* or *Unknown*. Logical CSS properties serve RTL and LTR; under 760px the list becomes an overlay.

**Ollama load approval text** is now short and explains the reload: "Allow Ollama to load or reload this model at this context size … Starting with a different context makes Ollama reload the model, which takes time and memory. Nothing loads unless you tick this box." It is never pre-ticked and resets every time.

**Sources.** Common chat-application conventions only. Open WebUI, LibreChat and assistant-ui licenses were read; nothing was copied ([attribution](../THIRD_PARTY_ATTRIBUTION.md)).

**Issues found and fixed.** A global `.icon-button{display:none}` hid the new header buttons; a bulk class rename then also renamed the app's own mobile-menu button, which a README screenshot revealed; fixed and re-verified. Latin key names inside Arabic hint text were flagged by the RTL scan; key names now sit in `<kbd>` elements.

## 5. Dataset segments

Collection stays off by default and after restart, never retroactive, never auto-approved, never includes thinking or partial replies. Consecutive consented turns form a segment: first turn `single_turn`, later turns `multi_turn` linked to the previous collected answer, with context metadata for audit. Verified against the existing export: `sft.jsonl` gets the first pair, `multi_turn.jsonl` the later pairs with only consented context, and no unconsented text appears in any export file. No schema change was needed for this part. [Collection segments](../chat-workspace.md#collection-segments-single-turn-and-multi-turn).

## 6. README restoration (RESTORE-README)

The owner-approved README design (`feat/native-conversation-capture:README.md`, commit `2870eae`) was shortened during PR #11. Restored on this branch: the four badge rows (same shields.io `for-the-badge` style and colors, statuses updated), introduction, idea and problem, capabilities, visual introduction with screenshots and the architecture SVG, table of contents, technology table, requirements, downloads, Windows/Linux quick start, two Mermaid diagrams, project structure, configuration, security, testing, roadmap, developer guide, licensing and maintainer handover — every approved section in its approved order. Content was updated to the current state (training removed in PR #11, Chat V2, NajdiLab Native, permanent deletion) with a feature status table separating available, in development and planned.

Images: `docs/images/screenshots/dashboard.png` had been deleted in PR #11 and showed a superseded UI, so it was **recaptured** from the synthetic fixture instead of restored. New captures: `chat-v2-desktop.png`, `chat-v2-arabic.png`, `chat-v2-mobile.png`, all made by `tests/readme-screenshots.cjs` from the disposable synthetic fixture. The architecture SVG generator received small text updates (Native runtime, streaming, deletion scope). Links in the approved README to documents removed in PR #11 (training guides, older verification reports) were not restored as links; their topics are covered by current documents.

Guard: `tests/test_readme_structure.py` (8 checks) fails if a refactor removes an approved section, changes their order, drops the badge rows, the table of contents, the screenshots or diagram, the Mermaid diagrams, the install commands, the structure tree, the feature-status split or the licensing links. Verified by running it against the shortened PR #11 README: all 8 checks fail there. Limit: it checks structure, not wording or visual quality.

## Test results

Run on 2026-11-02, Linux container (Python 3.13.18, Node 22.23.4, Chromium build 1243 via `puppeteer-core@25.16.0`, llama.cpp `llama-server` b12059 CPU build). The tested code is exactly the commit that adds this log; only this section changed after the run. **Windows was not run. Hosted GitHub Actions results are not claimed.**

| Suite | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---|
| `pytest tests` with `NAJDILAB_NATIVE_TEST_SERVER` set | 729 | 0 | 33 | 59 subtests passed. Includes 3 real llama-server lifecycle tests. |
| `pytest tests` without a llama-server | 726 | 0 | 36 | The 3 extra skips are the Native lifecycle tests. |
| Node unit tests (7 files, CI list) | 43 | 0 | 0 | Includes the new `chat-v2-ui.test.cjs` and the extended Arabic catalog checks. |
| Chromium `chat-browser.cjs` | PASS | — | — | One end-to-end script: keyboard, duplicates, streaming, thinking, Markdown/XSS, sidebar actions, 320/390px, rollover, Stop, Ollama approval, hardware tables, draft preservation, permanent delete. |
| Chromium `review-restrictions-browser.cjs` | 12 | 0 | 0 | |
| Chromium `i18n-browser.cjs` | 10 | 0 | 0 | Arabic RTL scan includes the chat view, the new-chat dialog and 390px. |
| Chromium `a11y-browser.cjs` | 13 | 0 | 0 | Keyboard, names, 200%/400% zoom. |
| `scripts/check_docs.py` | PASS | — | — | 73 Markdown files, links and API inventory. |
| `compileall app scripts tests` | PASS | — | — | |

Skipped tests (33) are not passes: 24 need private historical artifacts that are not in the repository; 9 need a real Ollama binary (`NAJDILAB_DISPOSABLE_OLLAMA=1`), not installed here.

New tests in this branch: `test_chat_v2.py` (24), `test_chat_v2_stream.py` (11), `test_native_runtime.py` (11), `test_readme_structure.py` (8), `chat-v2-ui.test.cjs` (14), the Chat V2 catalog check, and the rewritten chat section of `chat-browser.cjs`. Failure cases are covered explicitly: stale revision, wrong confirmation, active turn, exported copy, mid-transaction failure, stream error lines, data after the final chunk, missing final chunk, wrong content type, length stop, empty answer, prompt-count mismatch, changed model file, wrong context, stopped runtime, hostile GGUF headers, path traversal, unsafe links and raw HTML.

Two existing UI-contract tests (`test_dataset_scope_ui.py`, `test_dataset_ui.py`) asserted the old chat wording; they were updated to the V2 labels for the same controls and disclosure. `test_chat_hardware.py` was updated for the new 4096 tier. `test_phase_a_regressions.py` now expects 008 as the last registered migration.

Not tested: Windows; any GPU; RTX 5070; real LM Studio, Ollama or llama.cpp models; the owner's permanent installation.

## Local installation update

**Blocked — not performed.** The permanent installation (`C:\Users\Admin\NajdiLab-PR19-20-Local`, port 8870) is on the owner's Windows computer. No computer was attached to this cloud session (`list_computer_folders` returned none), so its source, services, database and backups could not be inspected, backed up or updated. Nothing on that machine was touched. Owner steps when ready are in [Rollback](#rollback) and the update checklist below.

Update checklist for the owner (do not skip any step):
1. Stop NajdiLab on port 8870. Do not stop Ollama or LM Studio.
2. Back up: `python scripts\backup.py` (or copy the whole folder), then verify the backup opens and `PRAGMA integrity_check` returns `ok`.
3. Copy `data\najdilab.db` to a scratch folder, run migrations on the **copy** with this branch's source, and check `integrity_check`, `foreign_key_check`, and that the number of rows in `chat_sessions`, `chat_turns`, `chat_requests` matches before and after.
4. Only then update the real source and start NajdiLab. Open several old conversations and confirm their text.
5. Collection must still be off; the selected model must be unchanged.

## Rollback

- **Source:** revert the branch's commits (or check out `integration/pr19-pr20-local-20261102`).
- **Database after migration 008:** 008 only rebuilds `chat_sessions` with extra nullable columns and adds `chat_deletions`. Older source keeps reading `chat_sessions` because every original column is unchanged. Two caveats: older source cannot read sessions whose provider is `native`, and archive/restore metadata columns are simply ignored. If a full schema rollback is required, restore the verified backup taken in step 2 above into a separate location first; **permanently deleted conversations cannot be brought back by any rollback except restoring that earlier backup**.
- **NajdiLab Native:** unset `NAJDILAB_NATIVE_SERVER`; nothing else was installed.

## Remaining risks and limits

- Real-model behavior is unverified for all three runtimes in this branch (streaming with Gemma 4 thinking on Ollama, LM Studio reasoning fragments, llama-server with real templates).
- Windows was not run for this branch; hosted GitHub Actions results are not claimed.
- The permanent-delete export scan matches the conversation id in files under `exports/`, `datasets/` and `reports/`; content copied manually elsewhere is outside its reach.
- `review_events.reason` text cannot be redacted (immutable by design).
- Split GGUF files are not supported; one Native model at a time.
- The 10-minute Ollama refusal-proof reuse trades one oversized request per turn for a time-bounded assumption that the same Ollama build behaves the same; it is invalidated by any version, digest, budget or admission failure.
