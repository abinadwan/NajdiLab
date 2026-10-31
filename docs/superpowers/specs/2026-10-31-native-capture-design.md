# Native application capture safety assessment and design

Owner request: native Hermes, LM Studio and Ollama conversations only when a demonstrably safe read-only mechanism exists. No third-party app/config/database/service/traffic changes, code injection, plugin installation, manual exports or routed-chat substitution. Main merge and installed-machine update are not authorized.

## Existing implementation and branch ownership

Reviewed PR #8 at `b747c492bd5d48f2eff4ba47cc5bc042b32d813a` and Issue #9. PR #8 is still open, not merged; main is `ebfa1fce1dc9ef6a755cfcb46530e8e1088b5594`. Reuse its fixed loopback runtime discovery, model selection/test, Host/Origin/CSRF and fail-closed Hermes receiver. No existing native collector, cursor, scheduler or native capture consent exists. Work is on `feat/native-conversation-capture`, stacked on PR #8; its new PR targets the PR #8 branch to avoid duplicating that diff. No merge of either branch is authorized.

Issue #9 contains earlier routed-chat proposals. The current owner request requires capture from original applications and forbids substituting NajdiLab-routed chat. Therefore this change adds no chat/gateway/proxy feature.

## Decisions from independent source investigation

Three approaches were considered: official pre-existing read-only APIs/events, version-gated native storage observation, and modifying/intercepting/routing third-party apps. The third is forbidden. Storage presence and valid-looking user/assistant rows are insufficient evidence of completed turns. Neither a settling delay nor a model-generation test proves native capture.

- **Hermes v0.22.5 / schema 32:** native terminal admission results and `persisted_turn` receipts offer promising completed-pair evidence. A plain assistant row does not: failure notices and crash windows can leave plausible rows. The source must also be acquired consistently without prohibited source-side changes. Ordinary read-only WAL connections, immutable live reads and raw DB/WAL copies are not automatically proven to satisfy that boundary. Existing native API/RPC ownership, discovery and side effects must be established independently. Until an end-to-end method is verified, native capture remains BLOCKED; do not discard the promising ledger or claim universal impossibility.
- **LM Studio:** official documentation warns against relying on native conversation JSON structure. The documented API covers inference/model management and caller-created stateful chats, not retrieval of native desktop history. No pinned disk format/completion/deletion contract is validated. Native capture UNSUPPORTED for this release.
- **Ollama Desktop v0.40.13 / schema 19:** content is persisted during streaming while `stream` may already be false; success is a transient frontend event, and errors/cancellations lack an equivalent durable status. Message IDs are rewritten on chat save/rename. Snapshot polling cannot distinguish completed successful output from incomplete output reliably. Native capture BLOCKED.

Unknown installed versions/formats fail closed. Research versions must never be presented as the owner's installed version. No installed app source, conversation data or database is opened during development; owner compatibility/acceptance is NOT TESTED.

## Smallest safe implementation

Expose per-app native capability, exact blocker, metadata-only source detection, installed version NOT_VERIFIED, native connection DISCONNECTED, collection OFF, last capture empty, error and local disconnect verification in Settings. Keep runtime permission and native capture permission separate. Add explicit native connect/enable API gates that refuse unsupported capabilities even with `approved: true`; never add a fake successful connection or scheduler. Disable the enable control visibly with an explanation. Disable/disconnect may acknowledge local OFF without altering any existing NajdiLab records or external app.

Discovery checks only metadata at known source paths: `.hermes/state.db`, `.lmstudio/conversations`, and Windows `%LOCALAPPDATA%/Ollama/db.sqlite` (macOS documented equivalent). Never open source DB/WAL/SHM/conversation/config contents or use source SQLite, hashes or copies, enumerate chat files, load application code, run source SQL, or call unverified Hermes APIs. Reuse locality/link rejection. Unsupported desktop platforms are explicit. If automatic source detection fails, a separately approved UI path selection may inspect metadata only at the expected source filename/directory. Reject relative/URI/UNC/device/traversal/network/reparse/symlink paths and unexpected basenames; do not echo private paths/errors in responses or logs. Manual path selection does not grant capture consent or certify schema/version.

No migration, persistent capture consent, cursor, source snapshot copy, deduplication scheme or privacy filter is invented for a nonexistent supported collector. Existing review/ingest transactions remain intact. Restart resets local diagnostic choices and permissions; no recovery/backfill occurs. A future supported reader requires its own version/schema, atomic acquisition, completed-pair privacy, new-only baseline/cursor, idempotent queue persistence, race/deletion/restart and disable/disconnect proofs before capability can change.

## Proof and delivery

Use only synthetic files/databases and isolated fake runtime APIs. Tests prove passive snapshots, content-free discovery, strict consent, blocked enable/connect under plausible/unknown/corrupt source data, safe path fallback, missing/inaccessible sources, concurrent source replacement, restart/OFF/disconnect, source immutability and unchanged own review data. These are guard/diagnostic PASS results, never native capture PASS. Completed-pair extraction, deduplication and native queue persistence remain BLOCKED/NOT TESTED where no collector exists. Include a complete per-app Phase A matrix.

Run existing Python/controller/docs/packaging checks and Windows/Linux CI. Preserve explicit Core classifications and Hermes receiver block. Document primary-source pins, limitations, acceptance (all native steps BLOCKED unless a supported collector is added), backups and rollback. Open a separate stacked PR, leave Issue #9 open and owner acceptance NOT TESTED. No deployment or local installed pull.

## Research and review resolution

Hermes native GET/RPC investigation did not establish a zero-side-effect completed-native-pair feed. The terminal ledger is retained as a promising future source, but no atomic, source-untouched acquisition route is demonstrated. Ollama native history endpoints do exist behind its ephemeral-port/private-token desktop boundary; they expose the same ambiguous snapshots. Its done event is per initiating POST, not a shared subscription. No token extraction/scanning/interception is used. All three native capabilities remain blocked/unsupported.

Review found full-path ancestor lstat races. Resolved by metadata-only kernel reparse refusal on pinned Windows local-volume objects and Linux openat2 O_PATH with no-link/no-mount-crossing resolution. Unknown backends fail closed. Metadata handles request no content read/write and no source SQLite lock; no content/SQL snapshot code is added. Synthetic parent replacement regression covers this boundary.
