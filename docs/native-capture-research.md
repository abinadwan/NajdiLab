# Native conversation capture research — 2026-10-31

**Result: no native application collector is enabled in this release.** Hermes and Ollama Desktop are BLOCKED; LM Studio is UNSUPPORTED. A synthetic model response, a detected database, a quiet file or a plausible assistant row is not a completed native-turn capture PASS. Installed versions/schema and owner acceptance remain NOT TESTED. No installed application source, configuration, service or conversation was inspected during this investigation.

Reviewed [PR #8](https://github.com/abinadwan/NajdiLab/pull/8) at `b747c492bd5d48f2eff4ba47cc5bc042b32d813a` and [Issue #9](https://github.com/abinadwan/NajdiLab/issues/9). PR #8 provides runtime discovery/model tests and a closed Hermes receiver, not native capture. Issue #9's earlier routed-chat proposals are superseded by the current request for original-application capture; this work adds no routed chat, proxy, interception or app modification.

## Capability and mechanism matrix

| Application | Investigated native source | Current native capture | Exact missing proof |
|---|---|---|---|
| Hermes Agent | `~/.hermes/state.db`; native terminal admission result/committed-row receipts; existing APIs/RPC | BLOCKED — no enabled reader | Consistent live acquisition without source-side writes/coordination/activation is not demonstrated; API results are not a complete passive native-pair feed |
| LM Studio | `%USERPROFILE%/.lmstudio/conversations` JSON; documented REST/stateful APIs | UNSUPPORTED — no enabled reader | No validated versioned native disk format with final-completion/deletion/privacy semantics; official docs warn against relying on its structure |
| Ollama Desktop | `%LOCALAPPDATA%/Ollama/db.sqlite`; native desktop history routes/events; runtime API | BLOCKED — no enabled reader | Persisted partial/interrupted output is not distinguishable from successful completion; completion event belongs to the initiating request; native history access needs a private in-memory token |

These are release capability decisions, not a claim that every future version or acquisition technique is impossible. Detection does not certify version/schema, and a newer version is not presumed compatible. Windows default paths are metadata probes only; no content is opened, hashed, copied, parsed or queried. On Linux, Ollama's server/CLI must not be misidentified as its desktop history database; the reviewed desktop path implementation provides Windows/macOS paths only.

## Hermes Agent — five approaches

Official tag **v0.22.5**, commit [`bf0203a794a07aac3ff764972ab9087baa4e4f4e`](https://github.com/NousResearch/hermes-agent/tree/bf0203a794a07aac3ff764972ab9087baa4e4f4e). This is a researched release, not the owner's verified installation.

| Approach | Evidence and disposition |
|---|---|
| Read-only APIs | [`GET /v1/runs/{run_id}` projection](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/gateway/platforms/api_server_authority_runs.py#L52-L97) is scoped to known API-principal requests. It does not return arbitrary native user text with committed-row receipts. Transcript browsing alone cannot prove successful completion |
| Existing events/RPC | [`prompt.receipt`](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/gateway/session_controls.py#L795-L807) needs known session/admission identities and authorization. Session authorization can restore sessions; no passive completed-admission enumeration was demonstrated. Plugin registration/outbound hook activation would violate the zero-edit constraint and is not used |
| Local database | [`SCHEMA_VERSION = 32`](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_state_common.py#L284-L289); version is in `schema_version`, not `PRAGMA user_version`. Source documentation still describes an earlier schema. Schema number alone is insufficient |
| Conversation files | Older JSONL/transcript history is not a separately verified atomic completed-turn interface for the pinned current runtime. No legacy-file collector is inferred from directory presence |
| Version-compatible polling | Logical completion evidence exists, but its acquisition boundary remains unresolved under strict untouched-source requirements; no timer/debounce/row-ID heuristic is enabled |

A plain assistant row can be a failed-turn notice ([failure persistence](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/conversation_loop.py#L1889-L1931)); a final answer can be flushed before finalization ([final-response persistence](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/turn_final_response.py#L360-L371)). Those rows alone cannot authorize capture.

The promising future path is substantive: [`settle_session_input`](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_state_runtime.py#L239-L268) atomically stores a terminal admission outcome and retained result in `state_meta` under `gateway.admission.result.v1.<admission_id>`. A result can retain `completed`, failure flags, `final_response` and `persisted_turn` receipts. [`persisted_turn_receipt.py`](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/agent/persisted_turn_receipt.py#L43-L64) specifies exact committed user/final row identities. A future supported reader would require true JSON booleans for both completion predicates, source identity/generation, canonical text equality, live/deletion state, timestamp validation, no reasoning promotion, and a strict new-only baseline. It must project only allowed pair fields, never retained history/reasoning/tool/API sidecars.

**Acquisition is still a gate.** Ordinary live read-only SQLite access can participate in WAL/SHM coordination. An immutable live read is not proof of a consistent changing database. Sequential raw DB/WAL copies, even with stable sizes/hashes and structural integrity checks, are not an established atomic snapshot. SQLite's own [active-transaction copy warning](https://sqlite.org/howtocorrupt.html#_backup_or_restore_while_a_transaction_is_active) and [WAL concurrency model](https://sqlite.org/wal.html#concurrency) explain why. No source connection, backup API, checkpoint, vacuum, SHM creation, raw snapshot copy or privileged volume snapshot is attempted here. Some [dashboard store access](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/hermes_cli/web_server_sessions.py#L330-L388) can reconcile missing schema, so a GET label is not sufficient proof of zero side effects.

Preserve PR #8's unconditional `/api/v1/hermes-hook` refusal. The broken outbound `fields`/`enabled:false` assumptions are not reused. No Hermes Gateway, WhatsApp Bridge, Baileys session, plugin, hook, environment or running process is touched.

## LM Studio — five approaches

Official documentation inspected on 2026-10-31: [Manage chats](https://lmstudio.ai/docs/app/basics/chat), [REST API](https://lmstudio.ai/docs/developer/rest), [Stateful chats](https://lmstudio.ai/docs/developer/rest/stateful-chats).

| Approach | Evidence and disposition |
|---|---|
| Read-only APIs | Documented GETs list models/download status. Inference POSTs and caller-created stateful response chains do not establish access to conversations in the native desktop UI |
| Existing events | Streaming events belong to API inference requests; no documented cross-client native-completion subscription was established |
| Local database | No documented supported native conversation database contract was identified; do not invent one |
| Conversation files | Native JSON location is documented, but the vendor explicitly advises against relying on its structure. No source-written versioned fixture/completion/deletion contract was validated |
| Version-compatible polling | No approved format/version allowlist exists. File timestamps, parseable JSON and a settling interval cannot certify completed successful turns or safe exclusions |

Native capture therefore remains UNSUPPORTED, including unknown installed versions. This does not assert that JSON cannot be inspected technically; it states that a safe completion-only parser was not established. No sample guessed from a community exporter is presented as a production contract. No native chat/config file is read to infer its format. Runtime discovery and synthetic model tests remain available independently.

## Ollama Desktop — five approaches

Official release **v0.40.13**, commit [`04088e7c9d41cba5d33bafbf788d87a465c79d5b`](https://github.com/ollama/ollama/tree/04088e7c9d41cba5d33bafbf788d87a465c79d5b). Relevant source matches researched main commit `f9323416f0c3f84d82f6c4a7bde75b717448bd44`; neither identifies the owner's installed version.

| Approach | Evidence and disposition |
|---|---|
| Runtime APIs | Runtime model/status APIs do not expose native desktop history. `/api/chat` starts inference with caller-supplied messages, not observation of another client |
| Native desktop APIs | Actual [`GET /api/v1/chats` and `GET /api/v1/chat/{id}` routes](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/ui/ui.go#L285-L306) exist. Production binds an [ephemeral loopback port and private token](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/cmd/app/app.go#L186-L202); token is injected into the native WebView, not a public bootstrap interface. NajdiLab does not scan ports, extract cookies or bypass authentication. Even authorized snapshots retain the completion ambiguity |
| External events | Native completion is JSONL on the initiating POST response, not an independently subscribable shared event feed. Owning/intercepting that request would violate scope. The [frontend request parser](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/ui/app/src/api.ts#L341-L399) confirms this transport |
| Database/files | [Database path](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/internal/onboarding/app_state.go#L24-L39): Windows `%LOCALAPPDATA%/Ollama/db.sqlite`, macOS `~/Library/Application Support/Ollama/db.sqlite`. Current schema **19** lives in [`database.go`](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/store/database.go#L17), with `settings.schema_version`. The separate `schema.sql` is a frozen version-2 migration test input, not current production schema |
| Version-compatible polling | Known schema still lacks durable success/error/cancellation proof and rewrites message identities; strict completion-only polling remains BLOCKED. Unknown schemas are never parsed |

[`NewMessage`](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/store/store.go#L66-L85) defaults a missing Stream option to false. During [chunk persistence](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/ui/ui.go#L1212-L1286), assistant rows can already have that value. Errors are returned to the initiating client without a durable terminal error state; partial content remains. The [success event](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/ui/ui.go#L1291-L1327) is transient. Quiet files and false stream fields are therefore insufficient.

[`saveChat`](https://github.com/ollama/ollama/blob/04088e7c9d41cba5d33bafbf788d87a465c79d5b/app/store/database.go#L754-L811) deletes/reinserts all message rows. Sends, completion and rename may change IDs; `id > cursor` would duplicate history. Deleted chats have no tombstone feed, and reasoning/tools/attachments occupy separate fields/tables. No source store object is instantiated: upstream initialization can migrate/configure/checkpoint. Request-debug logging is opt-in, captures request bodies rather than final completions, would change app configuration, and is not used.

## Security disposition and future admission gate

Current source inspection is metadata-only. Windows uses a pinned local volume object with `NtCreateFile` metadata access and `OBJ_DONT_REPARSE`; Linux uses `openat2` metadata handles with kernel no-link/no-mount-crossing resolution. Unknown backends/remote paths/link traversal fail closed. See [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes), [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile) and [QueryDosDeviceW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-querydosdevicew). No content-read/write access or source SQLite transaction is requested. Locality and link restrictions are enforced again for manual fallback. Permission errors are sanitized; private paths are never reflected or logged in diagnostic responses.

A supported collector may be added only after independent evidence proves consistent zero-change acquisition, supported version/schema, completed user/final pair selection, no system/developer/reasoning/tools/credentials/attachments, deleted/incomplete rejection, new-only baseline, idempotent pending-review persistence, restart/race/deletion handling and synchronized stop/disconnect. Capture remains OFF until those tests move a real synthetic native turn into the existing queue. Owner acceptance is a separate later gate, never inferred from fixtures or CI.

Linux metadata requires a supported x86_64/aarch64 Linux openat2 kernel (5.6+); local mount crossings, including a separately mounted home/temp directory or bind mount, are deliberately refused by RESOLVE_NO_XDEV. Unsupported kernels/ABIs/platforms and Windows device mappings not identified as a fixed HarddiskVolume fail closed with no weaker stat fallback. These conservative metadata limitations do not enable native capture. See [openat2 resolution rules](https://man7.org/linux/man-pages/man2/openat2.2.html).
