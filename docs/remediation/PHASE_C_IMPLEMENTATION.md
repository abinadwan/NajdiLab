# Phase C implementation record — real AI engine acceptance

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

Status: **PREPARATORY IN_PROGRESS / DRAFT**. Owner authorized beginning Phase C in a **separate pull request** on 2026-11-02 while Phase B PR #19 remains Draft. This is an explicit **sequencing exception for source-only development**, not approval to merge or deploy Phase C early. The Phase C PR targets the Phase B feature branch so its diff does not include Phase B work. After Phase B passes acceptance and merges, retarget Phase C to `main`, inspect the diff and rerun tests. **Do not merge Phase C before Phase B.**

## Six original findings (no added finding IDs)

| ID | Work | State |
|---|---|---|
| QA-02 | Nine skipped real-Ollama tests | **BLOCKED** on a disposable real Ollama and owner approval; acceptance plan below (Increment 5) |
| AI-01 | LM Studio `RESULT_MISMATCH` on `google/gemma-4-e4b` | **OPEN — BLOCKED on owner reproduction**. Diagnostics, source narrowing and end-to-end synthetic tests added (Increment 2); cause not reproduced and nothing fixed |
| AI-02 | Identify the failed LM Studio post-generation integrity predicate | **IMPLEMENTED_PENDING_VERIFICATION** (Increment 1; verification defect fixed in Increment 1a) |
| AI-03 | Actual-model Ollama integration acceptance | **BLOCKED** on the owner's local environment; acceptance plan below (Increment 5) |
| AI-04 | Runtime contracts: immutable identity, full token count, cancellation, context overflow | **IMPLEMENTED_PENDING_VERIFICATION** (evidence only): NajdiLab's side proven through the real pinned SDK with a synthetic engine (Increment 4); real-runtime behavior **NOT VERIFIED** |
| AI-05 | Independent privacy and collection acceptance | **IMPLEMENTED_PENDING_VERIFICATION** (evidence only): independent synthetic acceptance suite (Increment 3); hosted CI and owner review pending |

No finding is PASS. Every test named here uses synthetic data; none reads a private dataset, an installed model or the owner's machine.

## Increment 1 — content-free LM Studio mismatch diagnostics (AI-02, commit `c2e642f`)

Existing `LoadedModel.generate` refused any mismatch if one of four checks failed: instance reference, structured output, streamed text equivalence, or final prompt token count. All four reported the generic `RESULT_MISMATCH`. This increment preserves that **same external error code** and strict refusal, while reporting an **allowlisted check name only** over the bounded helper process wire:

- `INSTANCE_REFERENCE`: post-response model instance reference changed.
- `STRUCTURED_OUTPUT`: model returned structured data, not strictly plain text.
- `STREAM_CONTENT`: final content differs from fragments emitted by the stream.
- `PROMPT_TOKEN_COUNT`: reply statistics disagree with the measured tokenized prompt.

Only a fixed safe explanation is shown to the operator. Never emit actual instance identifiers, model output, prompts, token sequences, SDK exception bodies, or the unsanitized child-process `check` string. Unknown identifiers keep the generic error. No failing result is saved into the chat or training dataset. Existing pre-inference checks are unchanged.

**Source acceptance added:** parameterized fake-SDK checks for all four predicates and privacy; whitelist mapping from worker errors to public generic code; unknown-code rejection; compatibility of the fixed `RESULT_MISMATCH` external code. These are synthetic tests, not reproduction of the real Gemma 4 mismatch.

## Increment 1a — verification of `c2e642f` and two defects fixed

Review of the AI-02 diff found it correct: check order equals the previous `or` short-circuit order, the parent only appends a detail for a known string identifier, and no value crosses the process boundary. Running the full suite found two problems:

1. **Failing guard test (blocking).** `tests/test_dataset_boundary.py::test_chat_security_implementation_and_export_contract_are_preserved` failed: `app/chat_engine.py` and `app/chat_engine_worker.py` are hash-pinned protected Chat files in `docs/cleanup-inventory.json`, and `c2e642f` changed them without updating the pins. Cause: the pin is a deliberate tripwire for security-relevant Chat code and was not refreshed with the authorized change. Fix: after reviewing the diff, the two pins were updated to the reviewed Git-blob bytes (`684ec06a…` → `ad29ab5f…`, `036c31aa…` → `c2a13b4d…`). The test itself, the other three pinned files and their hashes are unchanged; imports and declarations recorded in the inventory are still accurate. Both files are excluded from the Core candidate, so Core pins are unaffected.
2. **Untranslated refusal messages (UX, bilingual).** Chat engine refusals reach the page as the error text, but the Arabic catalog lacked the six LM Studio worker messages, the helper-unavailable message and thirteen Ollama refusals, and the AI-02 suffix produces four new composite messages. Added these 24 English → Arabic entries to `static/i18n-ar.js`, plus a Node check in `tests/i18n-catalog.test.cjs` that extracts every fixed message from `app/chat_engine.py` (including each `RESULT_MISMATCH` + integrity check combination) and requires an Arabic translation.

## Increment 2 — AI-01 diagnosis support (no fix claimed)

The mismatch on `google/gemma-4-e4b` was observed once by the owner and cannot be reproduced here. Work done:

- **Source narrowing against the pinned SDK (`lmstudio==1.5.0`).** The SDK builds `result.content` by joining exactly the fragments it yields to the helper, ignores fragments after cancellation in both places, and sets `structured` only when a response format is requested — the helper never requests one. With this SDK, `STRUCTURED_OUTPUT` and `STREAM_CONTENT` are therefore unreachable in normal operation and stay as defence in depth. The realistic candidates are `INSTANCE_REFERENCE` and `PROMPT_TOKEN_COUNT`. This is a reading of SDK source, not an observation of LM Studio.
- **End-to-end tests** in `tests/test_chat_sdk_integration.py` run the real pinned SDK, the real helper subprocess and the real Chat workspace against the synthetic WebSocket engine, with collection ON: instance replaced after generation, and prompt token count ±1. Each yields `RESULT_MISMATCH` with the exact diagnostic, saves no Chat turn and no review, and leaks no prompt, reply, instance reference or model key. A further test pins the narrowing assumption (SDK version, no structured config sent).
- **Hypotheses for the owner's reproduction** (unconfirmed; do not weaken a check to test them):

| Diagnostic shown | Plausible causes to investigate | Next owner step |
|---|---|---|
| `The final token count differed from the measured prompt.` | Template already contains a literal `<bos>` and the tokenizer adds another (or the server strips one); the server reports only uncached prompt tokens when it reuses a cached prefix (would appear on later turns, not the first) | Repeat one short synthetic first turn and one second turn; record which turn fails and the LM Studio version |
| `The loaded model instance changed.` | Just-in-time reload, idle-TTL unload/reload, or a manual reload during the turn | Disable auto-unload for the test; retry once; record whether the instance changed in LM Studio's UI |
| Either of the other two | Would indicate an SDK or LM Studio change beyond 1.5.0 behavior | Record the SDK and LM Studio versions; stop |

No change to the four checks, the pinned SDK version or the refusal is proposed until the owner reproduces the mismatch with a diagnostic.

## Increment 3 — AI-05 independent collection-privacy acceptance

`tests/test_ai05_collection_privacy.py` (13 tests) was written from the documented contract (`docs/chat-workspace.md`, `docs/review-restriction-integrity.md`) rather than from the existing Chat tests, and drives the real Chat workspace, review service and exporter:

- Collection is OFF for a new conversation; an uncollected turn stays in Chat storage only — no review, no message row, nothing in training selection, training files **or** `full_archive.json`.
- Consent must be a real boolean (`1`, `"true"`, `"yes"`, `null` are refused with `CONSENT_REQUIRED` and collection stays OFF). Enabling it never imports earlier OFF turns; turning it OFF stops copying at once.
- A collected pair is PENDING and ineligible; while it is undecided, every export is blocked (`REVIEW_PENDING`). Only explicit human approval places it in training selection.
- Each restriction (sensitive, personal, fact-check, evaluation-only, excluded) forces `training_eligible=0`, survives a later save that omits it, and keeps the text out of training files.
- An archived conversation's pairs are excluded; approving them again and a direct SQL update are both refused by the database trigger.
- Native stores: synthetic `~/.lmstudio/conversations`, `~/.ollama/history` and `~/.cache/lm-studio/conversations` are planted in an isolated home. A Python audit hook records every `open`/directory listing during discovery, a collected turn, approval and export: none touches those stores, and the planted text appears in no database column.

No product code changed for AI-05; no defect was found. Limits: synthetic engine and data; the HTTP layer is covered by existing route tests, not repeated here; a real-runtime session is outside scope.

## Increment 4 — AI-04 runtime contracts through the real pinned SDK

Ollama's contracts already had broad synthetic coverage (`tests/test_chat_ollama.py`). LM Studio had four tests over the real SDK. Added to `tests/test_chat_sdk_integration.py`, all using the real pinned SDK and helper subprocess against the synthetic engine:

- **Identity / configuration drift** between measurement and inference — instance reference, loaded context, or an injected template change — is refused as `MODEL_CHANGED` with **zero** generations.
- **Token accounting / context overflow:** the measured count is the whole rendered template including the BOS marker; budget = count + reserve completes; one less rolls over to `CONTEXT_LIMIT` with a new empty collection-OFF session and no generation. The prediction request carries `maxPredictedTokens = reserve` and `contextOverflowPolicy = stopAtLimit`.
- **Stop reasons:** `maxPredictedTokensReached`, `contextLengthReached` and `userStopped` from the engine save nothing, even with collection ON.
- **Cancellation:** Stop pressed while the engine is streaming makes the pinned SDK send a `cancel` on the prediction channel; the turn ends `STOPPED`; nothing is saved.

Mutation checks: removing the worker's template re-check fails the drift test; disabling the workspace's stop-reason guard fails the stop-reason tests (both restored; no product change). Limits: proves NajdiLab's side of each contract only. Real LM Studio/Ollama behavior on real models remains **NOT VERIFIED** (AI-03, QA-02).

## Increment 5 — AI-03 and QA-02 acceptance plan (not executed)

Nothing here was run: no Ollama binary, LM Studio or model was started, downloaded or contacted. Execution requires the owner's explicit, separate authorization after Phase B closes.

**Preconditions (all required):** Phase B merged and Phase C retargeted to `main` with green hosted checks on the exact SHA; owner names the machine, the approved SHA and a disposable working copy and database (`docs/chat-windows-acceptance.md`); the owner's running Ollama/LM Studio, models, settings and personal conversations are not touched; synthetic prompts only.

**QA-02 — disposable real Ollama (engine behavior, not model quality)**

1. On the owner machine, in the isolated copy, confirm `ollama --version` and record it. No model pull.
2. Run `NAJDILAB_DISPOSABLE_OLLAMA=1 python -m pytest -q tests/test_chat_ollama_real.py -rs`. The fixture (`tests/ollama_disposable.py`) starts its own `ollama` process on a private loopback port with an empty model directory, GPUs hidden, and a tiny generated random-weight GGUF.
3. Acceptance: 9 passed, 0 skipped, 0 failed; record counts, duration, Ollama version, OS. A skip is **not** a pass. Any failure: stop, keep logs, do not change the guard.
4. Afterwards confirm the owner's own Ollama process, model list and loaded models are unchanged (`/api/ps`, `/api/tags` from the owner's instance, read-only).

**AI-03 — the owner's actual Ollama model (e.g. `gemma4-local:e4b`)**

1. Isolated NajdiLab copy and database; connect Ollama in that copy; select the model. Selecting is not permission to load.
2. Owner approves the load at a chosen context. Record the `/api/show` digest and Ollama version.
3. Short synthetic turns covering: first turn completes or refuses with a named code (`CONTEXT_REFUSAL_UNPROVEN` is a safe outcome); multi-turn up to the exact budget and a rollover to a new collection-OFF session; Stop during a reply saves nothing; a reply-limit stop saves nothing; collection OFF by default, ON only by explicit choice, pairs PENDING/ineligible.
4. Evidence per step: code or status, token counts reported in the UI, whether a pair/review was saved. No conversation text beyond the synthetic prompts is recorded.
5. Acceptance: every step matches; anything else is recorded as a failure, not adjusted. GPU/VRAM capacity is out of scope unless measured separately.

**AI-01 retest (LM Studio, same session rules):** one first turn and one second turn on `google/gemma-4-e4b`; record the diagnostic line shown for any `RESULT_MISMATCH` and apply the Increment 2 table.

## Local verification (this container, 2026-11-02)

Run on the Phase C working tree (on top of `c2e642f`) after these changes, with Chromium only; `lmstudio==1.5.0` from `requirements-chat.txt` was installed into the container so its four SDK tests run (before installing, they were skipped). Results are recorded in the CHANGELOG entry for this increment and in the report to the owner; hosted Windows/Ubuntu runs have **not** been made (no Actions were started).

## Gates and exclusions

- No local Windows, WSL, Hermes, Telegram/WhatsApp, Ollama or LM Studio service changes are authorized.
- No model downloads, execution, telemetry export, new network discovery, inference prompts or private data reads.
- Do not flip `NAJDILAB_REQUIRE_FRESH_SIGNATURE`, enable legacy ingress, or alter collection consent policy.
- Hugging Face Direct stays a disabled future preview.
- Real-model/hardware tests are **not** represented as successful until separately authorized and run on disposable/owner-approved instances. Respect the existing 9 real-Ollama skips.
- QA-03 private historical artifacts from Phase B and QA-06 external Hermes sender verification are not waived by opening Phase C.
- Phase B PR #19 remains Draft; Phase C is a separate stacked Draft PR, not a second Phase B PR.

## Risks

- The inventory re-pin accepts the reviewed AI-02 bytes; any later edit to the two Chat files must be re-reviewed and re-pinned deliberately.
- The AI-01 hypotheses come from SDK source and Gemma template conventions; the real cause may differ.
- Synthetic engines can agree with NajdiLab's assumptions where a real runtime would not; that gap is exactly AI-03/QA-02.
- The AI-05 audit hook observes Python-level file access; native code paths outside Python are not observed (NajdiLab has none for discovery).

Rollback: revert the Phase C commits before deployment; no schema, persistent data, downloaded model or backup was changed. Reverting Increment 1 also requires restoring the previous two inventory pins (revert both together). If retargeting after Phase B merge produces conflicts, reconcile against reviewed `main` and do not force-push or bypass checks.

## Review follow-up — Phase A backup protection pin and Phase C roadmap metadata (2026-11-02)

A read-only GitHub provenance check established that the cleanup inventory's old `scripts/backup.py` SHA-256 (`3105167010b396412296ce92ebd2bd0c8f9c5106381855f64cd7caf559ee678d`) exactly matches the file at Phase 1 HEAD `812f28f`, while Phase A merge `5de14f9` deliberately replaced its inline SQLite copy with `app.db.backup_db()` to centralize snapshot validation. The resulting `scripts/backup.py` bytes on `main` and Phase C HEAD are identical and normalize to SHA-256 `1bf2d9cedd82d8950946007614fc8768a2d6665ceedebe37d99b67fa6a288aed`. No subsequent edit to that script was made. Only the stale protection inventory entry was reconciled; this does not approve future changes to the backup code or constitute a fresh backup/restore runtime test. The distinct PowerShell `scripts/backup.ps1` pin was **not** changed: its Windows CRLF checkout is governed by `.gitattributes`.

The Phase C row in the legacy three-column mapping table was restored to three columns. The status-summary row now lists AI-02, AI-04 and AI-05 as implementation pending verification; AI-01 remains OPEN and AI-03/QA-02 remain BLOCKED. No finding is upgraded to PASS. Review methods: GitHub commit/file provenance and normalized source SHA-256; no model, private data, Windows runtime or hosted CI was executed. Rollback: revert this documentation/inventory-only follow-up commit; no schema or application change is involved.
