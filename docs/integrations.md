# Settings → Integrations

## Native application capture is not enabled

The [native-source assessment](native-capture-research.md) adds explicit metadata/capability diagnostics. Hermes and Ollama Desktop native capture are BLOCKED; LM Studio native capture is UNSUPPORTED. All stay DISCONNECTED/OFF; installed versions/formats and owner acceptance remain unverified. No source content is read or imported, and no native capture PASS is claimed. Runtime connect/model tests below retain their independent scope and do not grant collection access. See the [16-case Phase A matrix](native-capture-test-results.md) and [Windows acceptance gate](native-capture-windows-acceptance.md).

GET snapshots include `native_capture`: capability/reason, source status/location, `version: NOT_VERIFIED`, `format_verification: NOT_TESTED`, native connection, enabled=false, last check/action, last capture=null, last error, local disconnect verification. `source_location` is DEFAULT/CUSTOM, never a private path. Discovery performs bounded no-follow metadata checks only. Unknown backends/mapped/reparse paths fail closed. No content opens, SQL or schema inference occur; metadata-only OS handles are distinct from content/database access.

The existing CSRF/Host/Origin/JSON boundary also protects `POST /api/v1/integrations/{id}/native/{path|connect|enable|disable|disconnect}`. Payload is exact `{ "approved": true }`, plus only `path` for the path action. Missing/nonboolean approval is 403, unknown action/source 404, connect/enable 409 NATIVE_CAPTURE_BLOCKED or NATIVE_CAPTURE_UNSUPPORTED. Unexpected fields are 400. Path fallback accepts an absolute local expected filename/directory only when default detection failed; it never enables capture, uploads a file or verifies its format. Disable/disconnect acknowledge local OFF and preserve existing queue items; runtime disconnect also verifies native OFF. State/path choices reset at process restart. No collection worker/cursor exists.

## Existing runtime functionality (PR #8)

Open Settings to run a bounded read-only discovery. This release supports two local model-runtime APIs and a blocked Hermes conversation-source connector. No service is installed, started, stopped, configured or downloaded. No training registry, job or dataset is changed.

| Connector | Discovery | Approved behavior | Limitations |
|---|---|---|---|
| LM Studio | `http://127.0.0.1:1234/v1/models`, `.lmstudio` directory marker | Connect, select an available model, synthetic `/v1/chat/completions` test, local disconnect | No automatic application history; authentication-required APIs unsupported |
| Ollama | `http://127.0.0.1:11434/api/tags`, `.ollama` directory marker | Connect, select a listed model, synthetic `/api/generate` test, local disconnect | No automatic application history, pulls, unloads or process management |
| Hermes Agent | `.hermes` directory marker only | Verify local receiver block | Collection/connect/test BLOCKED; external sender disconnect UNVERIFIED |

Markers are metadata hints under the launching user's home, not an installation/version guarantee. Missing marker and available API can coexist. Custom homes, WSL installations, IPv6-only servers, custom ports, remote services and credential-required APIs are intentionally unsupported. Nothing recursively searches a disk, imports an installed client, or reads config/history/secret files. Symlink/reparse and explicit UNC paths are refused. Windows markers require a fixed local drive (mapped/remote/unknown drives are refused); Linux markers require an allowlisted local filesystem in bounded kernel mount metadata. Marker discovery is skipped on other or unverified filesystems before directory metadata access. No path is returned to the UI.

## Consent and state

Opening Settings discovers, but does not connect or generate. `Scan again` repeats discovery with a 10-second cache. A server GET snapshot never probes. Connect refreshes models; select refreshes and validates the model; test refreshes again to reject stale selection. All four actions have separate human confirmations and require exact JSON `approved: true` plus the existing process CSRF token. Synthetic-test approval includes the snapshot selection_revision; another tab changing selection or consent invalidates it before any generation. A flag represents operator intent, not identity or proof of a physical click; same-user native clients can obtain CSRF as before.

The manager stores consent/model selection and timestamps in memory only. All tabs of one server share that state. Server restart revokes consent. There is no new migration or private config file. `CONNECTED` means local permission was granted, not a persistent upstream session or a health guarantee. Availability is separate: `NOT_CHECKED`, `AVAILABLE`, `NO_MODELS`, `ERROR`, or `BLOCKED`. Last check, last success, last error and last synthetic test are shown independently; failure clears stale models/selection. Empty lists permit connect but disable generation until a listed model is selected.

A test sends exactly `Reply with OK.` with a 16-token output request, temperature zero and streaming disabled, to the selected runtime. It may load that model and use local compute. No user text, headers from the incoming request, credentials or stored conversations are forwarded. Text returned by the runtime is checked for a completed nonempty response and discarded, not stored or displayed. PASS proves completed synthetic generation, not instruction accuracy, model identity, performance or training readiness. A local API can still lie about its identity; consent does not authenticate a local service.

Disconnect waits for an in-flight bounded operation, revokes local test access and clears models/selection. After its response, tests are refused until another approved connect. It does not cancel upstream compute already accepted, stop/unload a service, remove stored data, or claim external Hermes delivery ceased. The UI distinguishes verified local revocation from `UNVERIFIED` external Hermes sender state; see [Hermes safety correction](hermes-integration.md).

## Network and privacy boundaries

The fixed registry owns ports and paths. The transport opens numeric IPv4 sockets to `127.0.0.1` only: no DNS, URL overrides, proxy discovery, redirects, credentials or cookies. No API accepts custom endpoints, headers, prompts or file paths. Model identifiers are bounded validated data inside JSON, never paths/URLs. Response bodies are limited to 256 KiB, total HTTP bytes including headers/chunk framing/trailers to 320 KiB; model lists to 1,000; identifiers to 256 ASCII protocol characters. A socket shutdown deadline bounds requests to 3 seconds for listing and 15 seconds for generation; a test can include both (18 seconds total). Responses with unsupported framing/encoding/schema fail closed. Upstream errors/body/header values are not logged or reflected; stable errors include `AUTH_REQUIRED`, `UNREACHABLE`, `TIMEOUT`, `REDIRECT_BLOCKED`, `HTTP_ERROR`, `INVALID_RESPONSE`, `RESPONSE_TOO_LARGE`, `MODEL_UNAVAILABLE`.

Discovery and actions retain Host, Origin, Fetch Metadata, JSON and CSRF rules. No CORS, browser-direct runtime calls, telemetry or third-party dependencies are added. This is still a trusted single-user local application, not OS-user isolation or remote administration. Models/metadata are untrusted; browser rendering escapes them. Model names are visible local API metadata; never embed credentials in model IDs.

## API

- `GET /api/v1/integrations`: passive `{ok, consent_scope: "server_process", items}` snapshot.
- `POST /api/v1/integrations/discover`: empty object only; read-only probes, no connection consent.
- `POST /api/v1/integrations/{hermes|lmstudio|ollama}/{connect|disconnect}`: `{ "approved": true }`.
- `POST /api/v1/integrations/{id}/test`: `{ "approved": true, "selection_revision": <integer-from-snapshot> }`. Rejects stale approval with 409 `STALE_APPROVAL`.
- `POST /api/v1/integrations/{id}/select`: `{ "approved": true, "model": "<listed-id>" }`.

Successful actions return a complete snapshot. Upstream failures return HTTP 200 with `availability: ERROR` and structured `last_error`; this is an observable connection result, not a transport success claim. Invalid fields/selection use 400, missing consent 403, unknown actions 404, disconnected/model-required/Hermes-blocked actions 409. Browser security may reject earlier. There is no generic generation/history collection endpoint.

## Ownership and extension

`app/integrations.py` owns the registry, bounded transport and locked consent/state; `server.py` delegates after request security. `static/integrations.js` reuses `api`, escaping, date formatting and Settings routing; its CSS uses existing theme variables. Keep training runtimes separate. Add a connector at this responsible layer with a bounded protocol parser, explicit capabilities/consent and fixture-only security tests. Do not add arbitrary endpoints or enable conversation collection by reusing a runtime label.

## Verification and remaining gates

Tests use temporary homes and ephemeral fake APIs only. They exercise consent, synthetic wire payloads, auth/error/redirect/oversized/malformed responses, stale selection, proxy/DNS refusal, deadlines, disconnect serialization, restart, CSRF/Origin and Hermes refusal before body reads. Controller tests cover cancellation, confirmation, escaping and load errors. No real runtime/Hermes acceptance or model download is claimed. Actual Windows service compatibility and operator acceptance remain a post-merge, separately consented check.

See [design](superpowers/specs/2026-10-31-integrations-design.md), [plan](superpowers/plans/2026-10-31-integrations.md), [Windows update/rollback](integrations-windows-update.md) and the PR validation record. The Core source-only profile receives the same Hermes receiver block and reviewed source classification/hash updates so its separate CI remains valid. It deliberately does not gain inference integrations or model execution. Candidate verification is not publication/license approval.
