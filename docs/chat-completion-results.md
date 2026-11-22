# Chat completion results

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](user-guide.md) for present operation.

Historical PR #12 record: draft follow-up to PR #11, on branch `feat/chat-workspace-claude`, based on reviewed commit `aa328ff` and targeting `feat/dataset-chat-workspace`. Original evidence collected 2026-11-01; the original result counts and dates below are retained as that history, not current cleanup-head counts. PR #13 now reviews `refactor/remove-legacy-training` against the exact PR #12 head; its hosted results are recorded separately below. This is not merge or installation approval. [Contract](chat-workspace.md) · [owner acceptance](chat-windows-acceptance.md).

## Independent security review and Codex remediation (2026-11-01)

The independent review of `4937cd9` found **P1 model-name retargeting (potential cloud disclosure and A→B→A misattribution)** and **P2 Stop failing to interrupt stalled Ollama metadata reads**. No actual cloud transmission occurred. These findings supersede the earlier claim that post-response digest checks alone bind Ollama inference.

Codex remediation on the same Claude feature branch:
- Model routing now uses `sha256:<manifest digest>:local` for **every** Ollama Chat probe and inference. Only the source-reviewed v0.40.13 resolver is allowed; other versions and invalid/missing digests fail closed before user data is sent. The selected digest is saved when the Chat is created and compared again **before** any text-bearing request on each turn.
- The Stop event propagates to `/api/tags`, `/api/version`, `/api/show`, `/api/ps`, inference, and the post-generation metadata read. Synthetic metadata-stall tests assert timely interruption without stored turns.
- New synthetic regressions exercise alias-to-cloud and A→B→A flips, first-turn substitution, unsupported versions/digests, and cancellation during metadata and after generation. They are **not** proof of real Gemma4/LM Studio acceptance.
- The digest-ref semantics were checked in the versioned Ollama v0.40.13 `server/model_resolver.go`, `server/routes.go` and `internal/modelref/modelref.go`. After Ollama update, Chat blocks until the new resolver is reviewed. No third-party configuration is altered.

**Hosted source/candidate CI for security fix commit [7659c8b](https://github.com/abinadwan/NajdiLab/commit/7659c8b00e961f6c291cbe5c53041bff9eedb27f): GREEN on both OSes.**
- [Source checks](https://github.com/abinadwan/NajdiLab/actions/runs/41275717498): Windows **452 passed, 32 skipped, 68 subtests passed**; Linux **450 passed, 34 skipped, 68 subtests passed**; one existing warning each, no failures. Node chat/integration controllers, compile/docs and hosted synthetic browser acceptance completed successfully.
- [Source-only candidate](https://github.com/abinadwan/NajdiLab/actions/runs/41275717499): Windows/Linux **74 passed / 68 subtests** each; builder **11 passed / 18 subtests**; same 74 selected candidate files and manifest SHA256 `9047157b634c862122eb2ff71e707e442debe44856a9c06ca2df5418210ffa56`; hosted candidate browsers passed.
- Skips reflect unshipped historical private artifacts, unavailable OS-specific cases, and **nine opt-in tests against a real Ollama binary not run in hosted CI**. All new synthetic security tests are included and not skipped. No installed real Gemma4, real LM Studio or GPU acceptance has run as part of this Codex remediation.
- This result applies to the listed implementation commit; documentation-only follow-up commits also require a green final-head CI check before merging.

**Owner acceptance for real Gemma4/LM Studio, GPU/VRAM feasibility and owner Windows acceptance are still NOT VERIFIED.** Neither PR #12 nor PR #13 hosted CI grants merge, installation or operational approval. Hermes remains BLOCKED; the approved scope is Chat/review/dataset preparation and external Unsloth handoff.

## Subsequent PR #13 cleanup CI — 2026-11-01

Cleanup head `f4cff7c5edfd8015f3027eecc9f367c0596239f9` is the direct child of PR #12 head `a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9`. [Source checks 41287022924](https://github.com/abinadwan/NajdiLab/actions/runs/41287022924) and [Source-only candidate 41287022915](https://github.com/abinadwan/NajdiLab/actions/runs/41287022915) completed successfully on both Windows and Linux. Source: **Windows 417 passed / 31 skipped / 59 subtests passed; Linux 415 passed / 33 skipped / 59 subtests passed**. Core: **78 passed / 0 skipped / 68 subtests passed on each OS**. Builder: **12 passed / 18 subtests passed on each OS**. There were zero failures in these suites. The source Node suites passed **5 integration + 5 Chat tests per OS**; synthetic root/Core browsers and the manifest-copy harness passed. Exact job IDs, skip reasons and the 71-file Core manifest are in [PR #13 verification evidence](verification-evidence.md#pr-13-hosted-cleanup-evidence--2026-11-01).

These counts are new hosted cleanup evidence, not replacements for the historical PR #12 or local cleanup counts below/in the [initial cleanup report](cleanup-results.md). The five Chat/worker/workspace/integration/Unsloth implementation files remain byte-identical to PR #12. Every later documentation commit needs its own hosted status; these runs do not qualify a different head. Real Gemma4, real LM Studio, GPU capacity and owner acceptance remain NOT VERIFIED.

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

- **Historical pre-remediation rationale: prove behavior, do not trust a version alone.** Ollama's `truncate`/`shift` are in its public Go API types but not on its REST reference page, and old servers silently ignore them. Every turn still checks refusal of overflow. The later security remediation additionally requires the source-reviewed v0.40.13 resolver allowlist and immutable local digest; overflow probes do not replace those checks, and an update is not permission to bypass them.
- **A one-token probe, accepted.** PR #11 ruled out inference probes. No tokenize route exists at 0.40.13, and `num_predict:0` is not a dry run. `prompt_eval_count` of a one-token prediction is the only exact count from documented fields. It evaluates the prompt once, and the reply reuses it from cache.
- **Ollama load approval.** The brief forbids loading without approval, and Ollama loads on request, so each conversation needs an explicit choice.
- **Thinking models accepted on Ollama, still refused on LM Studio.** The owner's only installed Ollama model has thinking on by default, so refusal would make Ollama Chat unusable. Ollama already separates the final text, so nothing is edited. LM Studio's mixed fragments keep the PR #11 refusal.
- **Cloud models refused.** They forward prompts off this machine, which local-only forbids.
- **A new table, not `ALTER TABLE`.** Migration 006 stays idempotent across the loader's crash gap.
- **Estimates use a KV upper-bound assumption.** KV assumes all layers are full-attention, which can overestimate sliding-window KV needs. That modeled component is not measured VRAM consumption or a guarantee of total allocation safety. No 8K/16K/32K context is accepted without separately approved owner trials and actual memory evidence.
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

**Not performed by the original local verification:** any installed model, including `gemma4-local:e4b` (never loaded); any real LM Studio session, since its server was off and starting it would change the owner's runtime; any GPU load or memory measurement, since the disposable engine ran CPU-only. Hosted CI had not yet run when that local record was written; the later PR #12 security-fix runs and PR #13 cleanup runs above supersede only that CI absence. Real-model/GPU/owner acceptance remains NOT VERIFIED. The rendered path for a renderer/parser model like `gemma4-local` is read from source only, so the first real send may block with `CONTEXT_REFUSAL_UNPROVEN`. That is the safe outcome, and owner acceptance decides it. The suggested contexts have never been compared with a real allocation.

The owner's running Ollama was checked after each run: same process, no models loaded, same model list. No engine configuration, model or personal conversation was read or changed. Model metadata for `gemma4-local:e4b` was read with `/api/show`.

## Historical PR #12 local test results

These are the original pre-security-remediation implementation's local observations collected on 2026-11-01, preserved separately from the later `7659c8b` hosted security evidence and PR #13 cleanup results. They do not qualify the current head. The [acceptance guide](chat-windows-acceptance.md) now targets an exact owner-approved cleanup commit rather than replaying the old feature-branch checkout.

| Check | Windows 11, Python 3.12.10 | Linux (WSL Ubuntu 24.04), Python 3.12.3 |
|---|---|---|
| `pytest tests` | **453 passed, 24 skipped, 0 failed**, with real-engine tests enabled | **443 passed, 34 skipped, 0 failed** |
| Baseline at `aa328ff` | 381 passed, 24 skipped | Not run |
| Source-only builder | 11 passed; 74 candidate files verified | 11 passed |
| Node controllers | 10 passed | 10 passed |
| Real browser acceptance | PASS (Chrome) | Not run |
| Docs and API inventory | PASS | Not run |

**Skipped, exact reasons.** Windows, 24: 23 private historical artifacts not distributed; 1 symlink creation not permitted for this account. Linux, 34: the same 23; 9 real-engine tests requiring the opt-in and an installed Ollama; 1 Windows PowerShell launcher check; 1 Windows drive type boundary. No existing test was skipped, removed or weakened. Existing tests changed only for new required contracts: `load_approved`, `limits()`, the `measure()` signature, and the public handle.

**Not failures, but not proof:** that recorded real-Ollama-binary run was local only. The hosted workflows did not opt into these nine real-binary checks and reported them as skips. The original real-engine run was repeated to rule out flakiness after the fixture was made deterministic; it used a synthetic CPU-only model and did not establish installed Gemma4/LM Studio or GPU acceptance.

## Remaining limitations

- Ollama depends on two request fields absent from its REST reference, and on the wording of one error message. A change blocks sending rather than truncating, but it would block.
- Each Ollama turn costs two extra requests. The refusal check tokenizes filler of about 6 bytes per budget token, so very large budgets add a noticeable preflight.
- Ollama's Stop relies on client disconnect, observed but undocumented; a stop during a cold load may leave the load running.
- Hardware only reads NVIDIA GPUs. The margin in the estimate is a rule of thumb. LM Studio gets no memory estimate.
- LM Studio remains pinned to SDK 1.5.0; reasoning output is refused there.
- One-turn-per-runtime means a second tab gets `ENGINE_BUSY` rather than a queue.
- The original local record preceded hosted CI. The PR #12 security-fix runs and PR #13 cleanup runs above are now completed evidence for their cited revisions; later commits require new checks and no CI run establishes owner/model/GPU acceptance.

## Dependencies and data

Historical PR #12 introduced no new runtime or test dependencies. Migration 006 is additive and idempotent, with no change to existing rows. Rollback is in [Backup and rollback](chat-workspace.md#backup-and-rollback). At that historical stage the seven new files were classified `excluded` in `public_source/policy.json` and the source-only candidate had 74 files. PR #13 intentionally reduced the dataset-only Core map to 71 files; its exact manifest and verified counts are recorded separately above. This documentation correction changes no source, migrations, configuration, dependencies, tests or workflows.
