# Chat V2 security review

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

| | |
|---|---|
| Date | 2026-11-03 |
| Scope | `app/chat_engine.py`, `app/chat_engine_worker.py`, `app/chat_workspace.py`, `app/integrations.py`, `app/chat_deletion.py`, `app/native_runtime.py`, `app/gguf.py`, `app/server.py`, `migrations/008_chat_experience_v2.sql`, plus the PR #21 code merged in the reconciliation |
| Method | Line-by-line source review of trust boundaries, concurrency, persistence, rollback, streaming and error paths; every finding below has a test that fails without the fix or demonstrates the residual. Synthetic data only. |
| Reviewer | Claude (automated agent). **Not** an independent human security review; the owner should treat this as input to one. |
| Status | Findings F1–F8 and R1–R3 fixed and tested. Residual risks listed below are accepted-and-documented, not fixed. |

Threat model: NajdiLab is a trusted local single-operator service. In scope: other web origins in the browser, a misbehaving or replaced model runtime, malformed model files, network peers (must have no access), crashes and concurrency, and accidental exposure of private text in logs, exports or after deletion. Out of scope: malware running as the same OS user (it can read the database and files directly).

## Findings

| ID | Severity | Area | Finding | Fix | Evidence |
|---|---|---|---|---|---|
| R1 | **High** (privacy / data integrity) | Collection → export | PR #22 alone let a collected segment that began mid-chat be approved for training and exported, although the answer can depend on unconsented context. | PR #21's `context_complete` gate merged and wired to PR #22 segments (review form, `save_review`, export readiness, both exporters). | `test_chat_dataset_context.py` (PR #21), `test_chat_v2.py::test_segment_export…` |
| R2 | Medium | Ollama load consent | Load approval survived a model or context change inside the new-chat dialog. | Approval withdrawn on every model, preset or budget change (from PR #21). | `chat-enhancements-browser.cjs` |
| R3 | Low | Input | Auto-repeating Enter and composition events could send; Send enabled for blank drafts and for a different selected model. | Shared `canSend` guard, `repeat` and composition handling (from PR #21). | `chat-v2-ui.test.cjs`, `chat-enhancements-browser.cjs` |
| F1 | **Medium** | Native runtime | The `llama-server` child inherited every environment variable. llama.cpp reads `LLAMA_ARG_*` as flags, so an inherited variable could enable `/props` writes, metrics, slots, a web UI, another host or a Hugging Face download (`LLAMA_ARG_HF_REPO`). | Child environment drops `LLAMA_*`, `GGML_RPC*`, `HF_*`, `HUGGING*`, proxy and hub-token variables; only NajdiLab's explicit flags configure the child. GPU selection variables (e.g. `CUDA_VISIBLE_DEVICES`) are kept. | `test_native_runtime.py::test_child_environment_drops_llama_flags…` |
| F2 | Low | Native runtime | Discovery listed (and read the header of) `.gguf` symlinks pointing outside the models folder. Start already refused them. | Entries whose resolved path leaves the folder are skipped. | `test_symlinked_gguf_outside_the_folder…` (skips where symlinks are not permitted) |
| F3 | Low | Native runtime | Model identity used size + mtime only, and the file was not re-checked after the server came up. | Identity adds the file id (inode / NTFS index); the stat is compared again after `/props` confirms the model. | `test_replacing_a_model_file_changes_its_identity…` |
| F4 | **Medium** | Deletion | If another reader held a snapshot, the WAL could not be truncated after deletion (old pages stay in `najdilab.db-wal`), but the UI still said "permanently deleted". | Result's `wal_checkpoint` is shown honestly in the UI; the workspace retries the truncating checkpoint at start. | `test_chat_v2.py::test_concurrent_reader_makes_wal_cleanup_busy…` |
| F5 | **Medium** (residual disclosure) | Deletion | Immutable `review_events.reason` is free text written by a reviewer and could quote the conversation; it is kept after deletion but was not disclosed. | Preview, result and dialog count and explain these reasons. They remain immutable by design. | `test_preview_counts_reviewer_reasons…` |
| F6 | **Medium** (availability) | Streaming | Stream writes had no timeout: a client that stopped reading without closing could block the reply thread and its runtime lease indefinitely (`ENGINE_BUSY` for everyone). | Socket write timeout (30 s) on the stream; a stalled write stops the turn like a disconnect; nothing is saved. | `test_chat_v2_stream.py::test_client_that_stops_reading…` |
| F7 | Low | Logs | The request log printed full query strings, including chat search terms (which can be conversation text). | Query strings are replaced with `?[query omitted]` in logs. | `test_request_log_never_contains_query_text` |
| F8 | Medium (release gate) | Build | PR #22 files were not classified in `public_source/policy.json`; the Core builder failed 4/12 on `d085ed2`. This check had not been run for PR #22 before. | All new files classified as excluded (Chat is not part of Core). | `public_source/tests/test_builder.py` 12/12; Core candidate build, verify, 78 tests, harness and browser PASS |

## Verified without change (tested)

| Property | Evidence |
|---|---|
| Partial, stopped, failed, length-limited, empty or count-mismatched replies are never committed or collected | `test_chat_v2.py` (stop, length, completion checks), `test_chat_v2_stream.py` (Ollama error line, missing final chunk, data after final, wrong content type), Native fake-server tests (missing `[DONE]`/usage, data after `[DONE]`, error event, second choice, invalid JSON) |
| Browser disconnect stops the turn; nothing saved | `test_browser_disconnect_mid_stream…` |
| Duplicate submissions | Receipt per request UUID (`test_chat_workspace.py`), `pending` set synchronously (`chat-v2-ui.test.cjs`), repeated Enter in Chromium creates one request (`chat-browser.cjs`) |
| Concurrency | One turn per session (`CHAT_BUSY`), one per runtime lease (`ENGINE_BUSY`), deletion refused during a turn (`test_delete_is_refused_during_an_active_turn`) |
| Thinking isolation | Raw database bytes contain no thinking text (`test_stream_events_thinking_is_shown_never_saved`, Ollama stream test); Native `reasoning_content` never enters the answer |
| Model identity change / context mismatch | Ollama digest change → `MODEL_CHANGED`; Native file change, wrong context, stopped runtime (real llama-server tests) |
| Streaming does not hold the workspace lock | Events are emitted outside every `self._lock` block (source review) |
| Native process | Arguments are a fixed list (no shell); GPU layers regex-validated; model path confined to the models folder; binds `127.0.0.1` only; API key required (401 without it); `--offline`; NajdiLab stops only the PID it started |
| GGUF parser | Bounded counts and strings, nested arrays refused, truncation detected, tensors never read (`test_gguf_rejects_damaged_or_hostile_headers`) |
| Markdown | DOM nodes only, no HTML parsing, http/https/mailto links only, escapes literal (`chat-v2-ui.test.cjs`, browser XSS assertions) |
| Migration 008 rollback | Older code (`634e7a5`) against a database already migrated to 008: its loader accepts the ledger, list/get/send/create/archive work, `integrity_check` ok, no FK violations (manual run 2026-11-03, see [test results](CHAT_EXPERIENCE_V2.md#test-results)). Older code cannot use `native` sessions. |

## Residual risks (accepted, documented)

| Risk | Why it stays | Mitigation |
|---|---|---|
| If NajdiLab is killed (not stopped normally), its `llama-server` child keeps running and holding the port and GPU memory. | No Windows job object / Linux parent-death signal yet. | Stop Native before closing NajdiLab; the process name and PID are shown in the Native panel. |
| The Native API key and file paths are visible to other processes of the same OS user. | Same-user processes are inside the trust boundary. | — |
| `review_events.source_sha256` can confirm a guessed exact text of a deleted reviewed reply. | Audit events are immutable by design. | Disclosed in the deletion preview and policy. |
| Ollama overflow-refusal proof is reused for 10 minutes per port/version/digest/budget. | Latency trade-off. | Version, digest, local reference and real context are checked every turn; any failure discards the proof. |
| Native GPU out-of-memory is classified only at start; a crash later fails the turn (nothing saved) and marks Native FAILED. | — | **NOT TESTED** on a GPU. |

## Not tested

Windows, any GPU (including RTX 5070), real LM Studio / Ollama / llama.cpp models, real IMEs, hosted CI. See [test results](CHAT_EXPERIENCE_V2.md#test-results) and the [Windows acceptance checklist](WINDOWS_ACCEPTANCE.md).
