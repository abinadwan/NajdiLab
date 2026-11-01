# Chat Workspace operations and API

Start from Settings → Integrations: discover, explicitly connect, select a model. Chat lists connected providers/models. New conversation fixes provider/model, admission budget and reply reserve. NajdiLab never loads a model or changes an engine service/configuration. The installed engine must already expose its API and loaded model. If it does not, Chat stays unavailable; this release does not add setup steps inside third-party apps.

LM Studio Chat needs optional `requirements-chat.txt` installed in **NajdiLab's own environment** during an approved update. Core review/export still requires only Python's standard library. SDK 1.5.0 is pinned because its internal instance-reference protocol helpers are used to avoid symbolic-identifier races. Different versions fail closed. Connection discovery/tests use the existing bounded REST connector. Chat alone uses the SDK API on the same fixed numeric loopback port, no credentials/proxy forwarding or automatic discovery. SDK I/O runs in a dedicated child with a 90-second total deadline; only that child may be terminated, never the engine service.

Only user/assistant plain text is sent. No NajdiLab system/developer prompt, tools, RAG, retrieved memory, preset, sampling override or rewritten response. The model's normal engine template is applied for counting and inference. Unknown/empty tokenization, changed instance/template/count, oversized/invalid/structured/tool/reasoning output, incomplete stop reasons, errors and cancellation produce no saved training pair. Reasoning models with mixed reasoning fragments are currently refused instead of silently edited. This is a limitation requiring actual engine acceptance; no promise that every model will work.

`context_budget` is a logical admission limit within the already loaded context; it does not reconfigure engine allocation or guarantee GPU memory. Before inference, exact templated input + reply reserve must be <= budget <= loaded context. Equality is allowed. At overflow the current session is closed, saved and a new empty, collection-OFF session opens. The draft stays visible for a separate user action; it is never automatically sent, trimmed or summarized. An unknown limit blocks sending rather than triggering a speculative inference probe.

Ollama Chat is visibly blocked pending exact public preflight. Its native `/api/chat` is an inference API, not a history feed; its connectivity result cannot establish the new context invariant. No native LM Studio/Ollama chats are collected, and Hermes ingress remains BLOCKED.

## Storage, consent and privacy

`chat_sessions`, `chat_requests`, `chat_turns` store completed raw local text pairs and delivery receipts separately from review conversations. History is reconstructed only from complete receipt-backed turns; the legacy `/messages` ingestion path cannot inject roles into Chat history. No drafts/partial outputs enter SQLite. Failed/interrupted receipts contain a request UUID, payload hash, status and timestamp, without raw draft text.

Collection is a separate explicit boolean, OFF by default and after server restart. Each choice creates a new consent epoch; OFF→ON cannot re-authorize an older in-flight turn. Continuous ON turns are copied as complete pairs to one review segment with provider/model/request/session provenance. Earlier OFF history is not copied. Review context is the consented segment; if its first turn follows earlier saved chat, its title warns that earlier context is excluded. Collected pairs and their receipt commit in one transaction using the existing ingest service; raw whitespace/Unicode is preserved. PENDING and training_eligible=0 remain authoritative until explicit human review.

One process owns each Chat DB using an OS file lock. One turn per session and revision-bound UUID receipts reject stale/overlapping requests. Completed retries return the same result; failed/interrupted requests require an explicit new request. Restart marks old RUNNING receipts INTERRUPTED. Stop/revoke/archive can act while inference is in progress, before commit. Integration disconnect waits for active leased work, then guarantees no later inference/capture under that permission; it never stops the runtime. Upstream cancellation is best effort; local persistence remains forbidden after Stop.

Archive cancels active work and excludes linked reviews from future training; a DB trigger prevents re-eligibility of archived Chat. Text/receipts/historical exports remain. This is **not physical erasure**. Own backup archives contain all local Chat text because they back up the database; keep backups private. Dataset `full_archive.json` preserves its existing raw review/manual schema and does not include uncollected Chat tables. Existing frozen exports are not rewritten; after privacy exclusions build a new version. Physical erasure and purging historical exports require a separate retention decision.

## Routes

All browser writes retain Host/Origin/Fetch-Metadata/CSRF/framing/body limits. No arbitrary endpoint/model path or SDK configuration is accepted.

| Method | Path | Body / result |
|---|---|---|
| GET | `/api/v1/chat/sessions` | latest 200 unarchived session summaries |
| POST | `/api/v1/chat/sessions` | exact fields: provider, model, selection_revision, context_budget, reply_reserve; returns session, collect=false |
| GET | `/api/v1/chat/sessions/{uuid}` | complete raw turns, status, revision, collect, busy |
| POST | `…/{uuid}/send` | request_id UUID, revision, selection_revision, text; COMPLETED or CONTEXT_LIMIT + new_session |
| POST | `…/{uuid}/collect` | enabled boolean, revision; no retrospective import |
| POST | `…/{uuid}/stop` | `{}`; stop_requested receipt |
| POST | `…/{uuid}/archive` | revision; retained archived session |
| POST | `/api/v1/chat/hardware` | approved=true; bounded read-only snapshot, recommendation unknown |
| POST | `/api/v1/unsloth-exports` | version; new immutable handoff metadata |
| GET | `/api/v1/unsloth-exports/{hex-id}/{file}` | dataset.jsonl, provenance.jsonl or manifest.json; hashed files checked |

Unknown/extra fields, wrong types, stale revisions and unapproved choices fail closed. Training namespace writes return 410 `TRAINING_EXTERNAL_ONLY` **before body parsing**. GET job/attempt/log/metric history and dataset/quality reads remain; execution-gate/worker/probing/model-download/runtime mutation paths are retired. Historical imports remain for source compatibility, not a supported training interface.

## Backup and rollback

This PR makes no installed update. After owner-reviewed merge and final-head green CI, stop NajdiLab, create and verify a private backup with the documented [backup procedure](backup-and-restore.md), inspect additive migration 005 and update only the reviewed source. Do not edit/delete migration history or overwrite a live DB. Test a copied backup in isolation first.

Rollback source to the reviewed parent `d992b0a`, leaving migration 005 and its data intact. Parent code ignores Chat tables; do not drop them or replace the DB to make rollback look clean. Keep the archive trigger and ensure archived Chat reviews remain excluded if using old code. Parent source restores deprecated training UI/APIs, so offline review/disable execution must precede any rollback launch; reverting earlier than PR #8 could reopen unsafe Hermes ingress. Rollback is owner-operated, not performed by this task.
