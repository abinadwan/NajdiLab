# Chat Workspace operations and API

Start from Settings → Integrations: discover, explicitly connect, select a model. Chat lists connected providers/models. New conversation fixes provider/model, admission budget and reply reserve. NajdiLab never changes an engine service/configuration. LM Studio must already have the model loaded. Ollama loads models on request and a different context reloads them, so an Ollama conversation requires a separate explicit `load_approved` choice; nothing else ever causes a load. If an engine's API is not reachable, Chat stays unavailable; this release does not add setup steps inside third-party apps.

LM Studio Chat needs optional `requirements-chat.txt` installed in **NajdiLab's own environment** during an approved update. Core review/export still requires only Python's standard library. SDK 1.5.0 is pinned. Handles from `list_loaded()` are symbolic and re-resolve their identifier on every call, so Chat builds the public `lmstudio.LLM` handle on the SDK's `instanceReference` specifier instead: template, token, context and prediction calls all use public handle methods and can only reach that one instance. The handle constructor is typed for a plain identifier, so passing a specifier relies on SDK behavior verified at 1.5.0; different versions fail closed. LM Studio's REST APIs have no tokenize route, so the SDK remains the only exact preflight. Connection discovery/tests use the existing bounded REST connector. Chat alone uses the SDK API on the same fixed numeric loopback port, no credentials/proxy forwarding or automatic discovery. SDK I/O runs in a dedicated child with a 600-second total deadline, long enough for a cold load plus a maximum reply; only that child may be terminated, never the engine service.

Only user/assistant plain text is sent. No NajdiLab system/developer prompt, tools, RAG, retrieved memory, preset, sampling override or rewritten response. The model's normal engine template is applied for counting and inference. A system prompt or `MESSAGE` that a model's own Modelfile defines is part of that model, not added by NajdiLab; device specs report when one exists, and its tokens are in the count. The only values set on a request are the two limits the workspace exists to enforce: context and maximum reply tokens (`num_ctx`/`num_predict` on Ollama, `maxTokens`/`contextOverflowPolicy` on LM Studio). Unknown/empty tokenization, changed instance/template/count, oversized/invalid/structured/tool output, incomplete stop reasons, errors and cancellation produce no saved training pair. This is a limitation requiring actual engine acceptance; no promise that every model will work.

Reasoning differs by engine. Ollama separates it into its own field before NajdiLab sees the reply, so `content` is the engine's final text, stored unchanged, and the trace is discarded and never stored. Provenance records `reasoning_discarded`. Reasoning tokens still count against the reply reserve, so a reply that uses the whole reserve thinking is refused as incomplete. LM Studio streams mixed fragments, which are refused rather than silently edited.

`context_budget` is an admission limit. On LM Studio it sits within the context already loaded and changes no allocation. On Ollama it is also sent as `num_ctx`, so it sets the runner's context. It never guarantees GPU memory. A budget above the runtime limit is refused when the conversation is created and again on each send, which catches stale metadata. Before inference, exact templated input + reply reserve must be <= budget <= runtime limit. Equality is allowed. At overflow the current session is closed, saved and a new empty, collection-OFF session opens. The notice states the numbers. The draft stays visible for a separate user action; it is never automatically sent, trimmed or summarized. An unknown limit blocks sending.

An Ollama conversation is bound at creation to the **content-addressed local manifest digest**, before any user text is sent. Every refusal probe, count probe and final generation uses `sha256:<full digest>:local`, **not the selected mutable model name**. The server-side resolver in the source-reviewed Ollama **v0.40.13** maps that form to an immutable local manifest and refuses remote inference. Unknown versions or missing digests block Chat with `MODEL_REFERENCE_UNVERIFIED`; no name-based fallback is allowed. The binding is checked again before any text-bearing probe on each turn. If a model tag changes A→B→A during generation, all requests still address A's immutable manifest; a post-response tag check is defense in depth, never the sole privacy boundary. Sessions lacking the binding must be recreated. This behavior still needs owner acceptance against the installed real Gemma4 model. A conversation is bound to the model that answered it: Ollama's manifest digest or LM Studio's model key. If that name later resolves to a different model, sending is refused with `MODEL_CHANGED`, because the history is no longer that model's own. A prompt that did not grow beyond the previous turn's is refused with `CONTEXT_SHRANK`: history only ever extends, so a smaller count means something was dropped.

### Ollama admission

Ollama has no tokenize route at 0.40.13, and by default `/api/chat` silently drops the oldest messages that do not fit, then shifts context during generation. Both were reproduced on the real binary. `truncate` and `shift` are declared in Ollama's public Go API types and honored by the server, but are absent from its REST reference page, so they are treated as observed behavior to verify, not as a promise. Older servers ignore them silently (they are absent at v0.12.0). So each turn proves the behavior rather than trusting a version:

1. `/api/tags` retrieves a full local manifest digest and `/api/version` must be the source-reviewed `0.40.13`. Read-only `/api/show` resolves **the pinned digest with `:local`**, not the mutable tag; `/api/ps` observes the running context. Cloud or unknown model references are refused *before any user text*.
2. **Refusal proof:** an oversized three-message history is sent with `truncate:false`. A silent drop would leave a tiny prompt and succeed, so the engine must answer `request (N tokens) exceeds the available context size (M tokens)` with N > M. Nothing is evaluated. Anything else blocks with `CONTEXT_REFUSAL_UNPROVEN`.
3. **Exact count:** the real history is sent with `num_predict:1`. `prompt_eval_count` is documented as the tokens in the prompt, and on the real binary it stays the full count on a cached repeat. `num_predict:0` is not a dry run, so the probe costs one generated token, which is discarded. A prompt beyond the context is refused by the engine with its exact count, which rolls over.
4. **Clamp check:** `/api/ps` must show the model at exactly the budget. Ollama silently clamps `num_ctx` to the trained maximum and shows the result only there. `OLLAMA_NUM_PARALLEL` does not divide this value.
5. **Reply:** the same messages and options with `num_predict` = reply reserve. Anything other than `done` with `done_reason` `stop`, or a count differing from step 3, or a changed digest, saves nothing.

`num_ctx` travels with every request, so another client cannot move the limit between steps 3 and 5. The engine pads its real slot to a larger size, so it may accept slightly more than the budget; NajdiLab's own arithmetic is the stricter check, and step 2 is only a backstop. Stop propagates through **every** per-turn read (tags, version, show, ps), overflow/count probes, generation and the post-reply identity check. A request waiting for stalled metadata is canceled without waiting for the full 600-second deadline. Stop closes the socket; the real engine was observed to end generation. A looping reply can make Ollama abort with a token repeat error: the turn fails and saves nothing.

Each turn therefore sends two extra requests. The refusal proof tokenizes a large filler, and the count evaluates the prompt once, but the reply then reuses that prompt from cache.

No native LM Studio/Ollama chats are collected, and Hermes ingress remains BLOCKED.

### Hardware evidence

`/api/v1/chat/hardware` reports four kinds of evidence separately and never merges them:

| Evidence | Source | Meaning |
|---|---|---|
| Model maximum | `/api/show` context length; SDK `max_context_length` | What the weights allow |
| Runtime context | `/api/ps`; SDK loaded context | What is configured now |
| Measured | `/api/ps` `size`/`size_vram` for a loaded model | What this model uses now, at that context |
| Estimated feasibility | Weights + KV bound, against free VRAM | A prediction, labeled unverified |

The estimate is `(weights + kv_per_token × context) × 1.15 + 512 MiB` against the largest GPU's free memory, plus VRAM this model already holds, since a reload replaces it. `kv_per_token` assumes every layer is full-attention with f16 keys and values, an upper bound: sliding-window layers use less. The 1.15 and 512 MiB are rules of thumb, not measurements. Tiers are 4K/8K/16K/32K/64K. The largest tier that fits is a *suggested starting context*, always labeled **unverified**, or `NO_ESTIMATED_FIT` if none does. If layer sizes, GPU memory or weight size are unavailable the result is `INSUFFICIENT_EVIDENCE` with no number. LM Studio does not expose layer sizes, so it reports `LOADED_CONTEXT_ONLY`: the context you already loaded. Reading specs never loads a model, and no stress test exists. Only your own [acceptance](chat-windows-acceptance.md) can validate a capacity.

## Storage, consent and privacy

`chat_sessions`, `chat_requests`, `chat_turns` store completed raw local text pairs and delivery receipts separately from review conversations. History is reconstructed only from complete receipt-backed turns; the legacy `/messages` ingestion path cannot inject roles into Chat history. No drafts/partial outputs enter SQLite. Failed/interrupted receipts contain a request UUID, payload hash, status and timestamp, without raw draft text.

Collection is a separate explicit boolean, OFF by default and after server restart. Each choice creates a new consent epoch; OFF→ON cannot re-authorize an older in-flight turn. Continuous ON turns are copied as complete pairs to one review segment with provider/model/request/session provenance. Earlier OFF history is not copied. Review context is the consented segment; if its first turn follows earlier saved chat, its title warns that earlier context is excluded. Collected pairs and their receipt commit in one transaction using the existing ingest service; raw whitespace/Unicode is preserved. PENDING and training_eligible=0 remain authoritative until explicit human review.

One process owns each Chat DB using an OS file lock. One turn per session, one turn per runtime (`ENGINE_BUSY` rather than a queue) and revision-bound UUID receipts reject stale/overlapping requests. Completed retries return the same result, even after the conversation closed; failed/interrupted requests require an explicit new request. Restart marks old RUNNING receipts INTERRUPTED. Stop/revoke/archive can act while inference is in progress, before commit. Integration status stays readable during a turn. Disconnect and select wait for active leased work, then guarantee no later inference/capture under that permission; they never stop the runtime. Upstream cancellation is best effort; local persistence remains forbidden after Stop.

Archive cancels active work and excludes linked reviews from future training; a DB trigger prevents re-eligibility of archived Chat. Text/receipts/historical exports remain. This is **not physical erasure**. Own backup archives contain all local Chat text because they back up the database; keep backups private. Dataset `full_archive.json` preserves its existing raw review/manual schema and does not include uncollected Chat tables. Existing frozen exports are not rewritten; after privacy exclusions build a new version. Physical erasure and purging historical exports require a separate retention decision.

## Routes

All browser writes retain Host/Origin/Fetch-Metadata/CSRF/framing/body limits. No arbitrary endpoint/model path or SDK configuration is accepted.

| Method | Path | Body / result |
|---|---|---|
| GET | `/api/v1/chat/sessions` | latest 200 unarchived session summaries |
| POST | `/api/v1/chat/sessions` | exact fields: provider, model, selection_revision, context_budget, reply_reserve, load_approved (Ollama true, LM Studio false); budget checked against runtime limit; returns session, collect=false |
| GET | `/api/v1/chat/sessions/{uuid}` | complete raw turns, status, revision, collect, busy |
| POST | `…/{uuid}/send` | request_id UUID, revision, selection_revision, text; COMPLETED or CONTEXT_LIMIT + input_tokens, reply_reserve, context_budget, new_session |
| POST | `…/{uuid}/collect` | enabled boolean, revision; no retrospective import |
| POST | `…/{uuid}/stop` | `{}`; stop_requested receipt |
| POST | `…/{uuid}/archive` | revision; retained archived session |
| POST | `/api/v1/chat/hardware` | approved=true, optionally provider, model, selection_revision together; bounded read-only snapshot, recommendation per [Hardware evidence](#hardware-evidence); a runtime failure appears in `warnings` |
| POST | `/api/v1/unsloth-exports` | version; new immutable handoff metadata |
| GET | `/api/v1/unsloth-exports/{hex-id}/{file}` | dataset.jsonl, provenance.jsonl or manifest.json; hashed files checked |

Unknown/extra fields, wrong types, stale revisions and unapproved choices fail closed. All `/api/v1/training/**`, model-adapter verification, `/api/v1/phase3/**` and platform-status routes are removed, with no410 shim or job/log/metric HTTP reader. Dataset eligibility is `/api/v1/dataset-records`; manual creation is `/api/v1/manual-data/{sft|direct|preference}`. Stored private evidence and applied migrations remain intact.

## Backup and rollback

This source change makes no installed update. Before any update, run the owner [Windows acceptance](chat-windows-acceptance.md). After owner-reviewed merge and final-head green CI, stop NajdiLab, create and verify a private backup with the documented [backup procedure](backup-and-restore.md), inspect additive migrations 005 and 006 and update only the reviewed source. Do not edit/delete migration history or overwrite a live DB. Test a copied backup in isolation first.

Migration 006 adds one table, `chat_session_bindings`, and alters nothing. A table rather than `ALTER TABLE` keeps replay idempotent across the loader's commit/ledger crash gap, as 005 does. Sessions created before it keep working: LM Studio ones bind on their next turn; Ollama ones must be restarted, since they never had load approval.

This cleanup is source-only: revert its source changes if needed, with no data/schema rollback. Leave Chat tables, receipts, consent/archive restrictions and historical dataset/export bytes intact. Older source can reopen removed interfaces or unsafe Hermes ingress, so inspect before any rollback launch. Physical erasure and old-export purging remain separate retention decisions. No rollback or installed update is performed by this task.

## 2026-11-02 owner-authorized follow-up

See [UI behavior](chat-ui-fixes.md), [collection/SFT audit](chat-dataset-context-audit.md), and [actual checks, safe local upgrade and rollback](chat-review-workflow-results.md). These supersede earlier descriptions only as specifically recorded there. Context completeness uses existing metadata, not a migration; unknown historical completeness blocks future training selection without changing stored data.
