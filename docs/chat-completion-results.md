# Chat completion results

Draft follow-up to PR #11, on branch `feat/chat-workspace-claude`, based on reviewed commit `aa328ff` and targeting `feat/dataset-chat-workspace`. Evidence collected 2026-11-01. This is not merge or installation approval. [Contract](chat-workspace.md) · [owner acceptance](chat-windows-acceptance.md).

## What this adds

- **Ollama Chat**, previously BLOCKED, with [per-turn admission proof](chat-workspace.md#ollama-admission).
- Context budget checked against the runtime at creation and on each send, with numbers in the rollover notice.
- [Hardware evidence](chat-workspace.md#hardware-evidence) in separate tiers, with a labeled unverified suggestion.
- LM Studio moved from private SDK helpers to public handle methods on the same instance reference.

## Audit of PR #11

Kept unchanged: receipts and revisions, consent epochs, atomic rollover, review ingestion, single database owner, instance binding and strict fail-closed checks.

Defects found and fixed. Each has a regression test.

| Defect | Effect | Fix |
|---|---|---|
| `chat_lease` held the integration lock through inference | Settings and integration status froze for a whole reply | Lease set plus condition; reads stay live, disconnect/select still wait |
| `shutdown()` does not wake a blocked `recv` on Windows | Stop waited for the engine; hidden only because the deadline equalled the socket timeout | `WakingSocket` wakes reads to check for expiry |
| Status checked before the receipt | Retry of a completed request after its conversation closed returned `CHAT_CLOSED` | Receipt first |
| Worker reduced every failure to `ENGINE_UNAVAILABLE` | "Model not loaded" looked like a broken engine | Fixed code set passed through, never SDK text |
| 15-second SDK gap timeout | Long prompt processing sends no messages, so it would be killed | Gap limit set to the total deadline |
| 90-second total deadline | Could not fit a cold load plus an 8192-token reply | 600 seconds |
| Non-string provider | Unhandled `TypeError` | Clean refusal |

## Decisions

- **Prove behavior, do not trust a version.** Ollama's `truncate`/`shift` are in its public Go API types but not on its REST reference page, and old servers silently ignore them. A version gate would be both weaker and broken by each automatic update, so every turn checks that the engine really refuses overflow.
- **A one-token probe, accepted.** PR #11 ruled out inference probes. No tokenize route exists at 0.40.13, and `num_predict:0` is not a dry run. `prompt_eval_count` of a one-token prediction is the only exact count from documented fields. It evaluates the prompt once, and the reply reuses it from cache.
- **Ollama load approval.** The brief forbids loading without approval, and Ollama loads on request, so each conversation needs an explicit choice.
- **Thinking models accepted on Ollama, still refused on LM Studio.** The owner's only installed Ollama model has thinking on by default, so refusal would make Ollama Chat unusable. Ollama already separates the final text, so nothing is edited. LM Studio's mixed fragments keep the PR #11 refusal.
- **Cloud models refused.** They forward prompts off this machine, which local-only forbids.
- **A new table, not `ALTER TABLE`.** Migration 006 stays idempotent across the loader's crash gap.
- **Estimates use an upper bound.** KV assumes all layers are full-attention, so sliding-window models are underestimated in capacity, never overestimated.
- **LM Studio SDK pin kept.** Public methods are an improvement, but passing a specifier to the handle constructor is verified behavior, not a documented contract.

## Actual versus synthetic verification

| Claim | Evidence | Kind |
|---|---|---|
| Default `/api/chat` silently drops history; `truncate:false` refuses | Installed `ollama.exe` 0.40.13, disposable instance | **Real engine, synthetic model** |
| `prompt_eval_count` is the full prompt on a cached repeat | Same | **Real engine, synthetic model** |
| Multi-turn chat, exact boundary, rollover, length stop, Stop ending generation | `tests/test_chat_ollama_real.py` through the real `OllamaEngine` and `ChatWorkspace` | **Real engine, synthetic model** |
| `/api/show`, `/api/ps` reads never load a model | Same | **Real engine, synthetic model** |
| `num_ctx` clamp, parallel slots, slot padding | Recorded probes on the same binary | **Real engine, synthetic model** |
| Clamp, digest swap, cloud model, tool calls, incomplete replies, engine that ignores `truncate` | `tests/test_chat_ollama.py` scripted server | Synthetic |
| LM Studio wire behavior | Real SDK 1.5.0 against a synthetic WebSocket engine | Synthetic |
| UI, escaping, Stop, approval, rollover | Real Chrome against synthetic engines | Synthetic |

**Not performed:** any installed model, including `gemma4-local:e4b` (never loaded); any real LM Studio session, since its server was off and starting it would change the owner's runtime; any GPU load or memory measurement, since the disposable engine ran CPU-only; hosted CI. The rendered path for a renderer/parser model like `gemma4-local` is read from source only, so the first real send may block with `CONTEXT_REFUSAL_UNPROVEN`. That is the safe outcome, and owner acceptance decides it. The suggested contexts have never been compared with a real allocation.

The owner's running Ollama was checked after each run: same process, no models loaded, same model list. No engine configuration, model or personal conversation was read or changed. Model metadata for `gemma4-local:e4b` was read with `/api/show`.

## Test results

All on the final code. Reproduce with the commands in [acceptance](chat-windows-acceptance.md).

| Check | Windows 11, Python 3.12.10 | Linux (WSL Ubuntu 24.04), Python 3.12.3 |
|---|---|---|
| `pytest tests` | **453 passed, 24 skipped, 0 failed**, with real-engine tests enabled | **443 passed, 34 skipped, 0 failed** |
| Baseline at `aa328ff` | 381 passed, 24 skipped | Not run |
| Source-only builder | 11 passed; 74 candidate files verified | 11 passed |
| Node controllers | 10 passed | 10 passed |
| Real browser acceptance | PASS (Chrome) | Not run |
| Docs and API inventory | PASS | Not run |

**Skipped, exact reasons.** Windows, 24: 23 private historical artifacts not distributed; 1 symlink creation not permitted for this account. Linux, 34: the same 23; 9 real-engine tests requiring the opt-in and an installed Ollama; 1 Windows PowerShell launcher check; 1 Windows drive type boundary. No existing test was skipped, removed or weakened. Existing tests changed only for new required contracts: `load_approved`, `limits()`, the `measure()` signature, and the public handle.

**Not failures, but not proof:** the Ollama test run is local only and cannot run in hosted CI. The real-engine run was repeated to rule out flakiness after the fixture was made deterministic.

## Remaining limitations

- Ollama depends on two request fields absent from its REST reference, and on the wording of one error message. A change blocks sending rather than truncating, but it would block.
- Each Ollama turn costs two extra requests. The refusal check tokenizes filler of about 6 bytes per budget token, so very large budgets add a noticeable preflight.
- Ollama's Stop relies on client disconnect, observed but undocumented; a stop during a cold load may leave the load running.
- Hardware only reads NVIDIA GPUs. The margin in the estimate is a rule of thumb. LM Studio gets no memory estimate.
- LM Studio remains pinned to SDK 1.5.0; reasoning output is refused there.
- One-turn-per-runtime means a second tab gets `ENGINE_BUSY` rather than a queue.
- Hosted CI has not run on this branch.

## Dependencies and data

No new runtime or test dependencies. Migration 006 is additive and idempotent, with no change to existing rows. Rollback is in [Backup and rollback](chat-workspace.md#backup-and-rollback). The seven new files are classified `excluded` in `public_source/policy.json`, so the source-only candidate stays at the same 74 files.
