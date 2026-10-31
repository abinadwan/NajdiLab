# Settings integrations design

Status: implementation specification under the owner's explicit execution request, 2026-10-31. Merge and installation remain unapproved.

## Intent and existing behavior

Expose local service discovery and controlled synthetic inference in Settings without changing external installations, training, or collected data. The existing server owns Host/Origin/CSRF and JSON framing; `service.py` owns ingestion; training/runtime registries are training controls, not local inference connectors. Reuse the browser `api()` helper and English, theme-aware UI.

## Approach and constraints

Use a small connector registry and a server-owned, locked integration manager. Reusing the training runtime registry would mix inference consent with training authorization. External plugins or frameworks would add dependencies without solving a current requirement. Keep Python standard library and Vanilla JS.

Discovery is read-only: only numeric `127.0.0.1:1234/v1/models` (LM Studio), `127.0.0.1:11434/api/tags` (Ollama), and metadata checks on the known home directories `.hermes`, `.lmstudio`, `.ollama`. No recursive search, executable invocation, config/history reads, DNS, proxies, redirects, credentials, configurable URLs, or network filesystem traversal. Installation markers are hints, not proof of service health or version.

The snapshot distinguishes installation evidence, reachability, consent/connection, available models, selection, last check/success/error, and local disconnect verification. Connection and selection are process-local; restart revokes consent. No schema migration or persistent private state is needed. Discovery never authorizes generation. Connect, select, test and disconnect require an explicit UI confirmation and `approved: true` checked server-side in addition to CSRF. A test sends only the fixed synthetic prompt `Reply with OK.` to a freshly revalidated selected model, with bounded output; it stores no conversation or model output. A model disappearing invalidates selection. Disconnect serializes with any in-flight test, revokes local access and clears selection; it does not stop/unload the external service.

## Hermes safety boundary

Hermes is a conversation source, not an inference runtime. Hermes v0.22.5 may ignore outbound `fields` and continue sending with `enabled:false`. Receiver-side filtering cannot prevent disclosure at the sender. Therefore automatic collection, connect, and live tests are BLOCKED in this release for all unverified Hermes versions. The HTTP `/api/v1/hermes-hook` endpoint returns 409 before reading/parsing/storing the body, even with legacy ingest enabled or valid credentials. Existing generic `/api/v1/turn` remains a separately authenticated manual collector and is not a workaround for unsafe Hermes hooks. Existing database rows and internal historical parser fixtures are preserved.

Hermes disconnect verifies only that this receiver is blocked. It must always report external sender disconnect UNVERIFIED; no false claim that delivery stopped. Never edit Hermes configuration, activate a webhook, read system/tool/history, stop a service, or rotate a user's secrets. Restoring collection requires a separately reviewed sender-side minimal-payload bridge and negative/positive tests proving raw wire privacy and removal of the outbound hook plus reload/drain verification.

## Proof and operational boundary

Use temporary fixture paths and ephemeral mock HTTP services only, including malformed/large/slow/redirect/auth responses, hostile payloads, consent, stale models, cross-origin/CSRF, disconnect races, restart, and blocked Hermes ingestion. Run the existing suite and generated-doc checks, report private-fixture skips and environment limitations. Add browser behavior checks with synthetic services only. Open a PR, leave main unchanged. Document safe post-merge Windows update, backup/migration checks and rollback without deletion; do not execute them on the user's installation.
