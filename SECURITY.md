# Security

NajdiLab is a single-user local application. Run it on `127.0.0.1` and keep the
operating-system account and project files private. Do not expose its port with
remote forwarding, a reverse proxy, containers publishing to external interfaces,
or a public tunnel. The HTTP server is not a multi-user authentication service.

## Browser and local API boundary

Every HTTP request is checked before routing, including static files and read-only
API calls. The server accepts exactly one `Host` naming `127.0.0.1` or `localhost`
at its listening port. Explicit `Origin` headers must match that exact HTTP
origin; hostile, opaque (`null`), duplicate, and malformed origins are rejected.
Cross-site and same-site Fetch Metadata requests are rejected. These checks limit
DNS rebinding and cross-origin access to local data; no permissive CORS headers
are sent.

All mutations require `Content-Type: application/json`. Non-ingest mutations also
require `X-NajdiLab-CSRF`, for browser and native clients alike. Obtain its value
from `GET /api/v1/session` and use the returned `csrf_token`. The token is random,
process-local, never persisted, and changes when the server restarts. Reload the
browser or fetch a fresh session after restart. Responses containing tokens use
`Cache-Control: no-store`. Training authorization and other operation-specific
confirmation checks remain additional requirements.

Native programs may omit browser-controlled `Origin` and `Sec-Fetch-*` headers;
they must still use the correct Host, JSON content type, and session token for
non-ingest writes. Do not copy browser headers from a different origin. Never put
a session token in a URL, committed file, issue, or log.

The session token protects request intent. A local program that can connect to
this port can obtain a session and read local API data. Someone controlling the
same OS account can also read or alter project files. These are explicit trust
boundaries, not isolation guarantees between local users or processes.

## Ingestion credentials and migration

`POST /api/v1/hermes-hook` is BLOCKED with HTTP 409 before body reading/parsing or storage, regardless of credentials or legacy mode. Hermes v0.22.5 sender filtering and `enabled:false` are unreliable; do not activate the old webhook configuration. Settings verifies only this receiver block, never external delivery cessation. See the [Hermes safety correction](docs/hermes-integration.md).

`POST /api/v1/turn` fails closed with HTTP 503
unless `NAJDILAB_INGEST_TOKEN` is configured. Set a high-entropy random secret
in the server's environment and restart it. Shell environment variables are used;
`.env` files are not loaded automatically. Never commit the configured secret.

Clients supply exactly one credential method: `Authorization: Bearer <secret>`
or `X-Hermes-Signature-256: sha256=<hex>`, where `<hex>` is the lowercase
HMAC-SHA256 of the exact raw request bytes using the UTF-8 secret. This generic collector authentication must not be used to bypass the blocked Hermes hook. Missing, invalid, duplicate, or mixed credentials
receive HTTP 401 when a secret is configured. Authentication precedes ingestion.
Browser requests also require the session CSRF token.

For migration, update the server environment and sending client together. Verify
a synthetic event before resuming real ingestion. Rotate the secret on both ends
if it has been shared accidentally. If a sender cannot be migrated immediately,
`NAJDILAB_ALLOW_LEGACY_INGEST=1` explicitly permits native requests with no
credentials and prints a startup warning. This weakens ingestion protection;
remove it after migration. Supplied invalid credentials still fail. Host, Origin,
JSON content type, and browser CSRF checks remain enforced in compatibility mode.

The signature authenticates body contents; it does not provide freshness or
replay prevention. Do not assume all ingestion payloads are idempotent. Protect
secrets and avoid replaying events unless the relevant event identity and dedup
behavior have been verified. Payload sizes are bounded before authentication.

## Local runtime integrations

Native application capture is a separate blocked capability, not runtime connectivity. Hermes/Ollama capture is BLOCKED and LM Studio UNSUPPORTED: direct native connect/enable calls return 409 even with valid CSRF and exact approval. All versions/formats remain unverified for capture. Source discovery/path fallback uses metadata only: no source content/config/history/cookies, SQL, snapshots, uploads, private tokens, interception or dynamic port scans. Windows metadata handles request READ_ATTRIBUTES only (plus synchronization), share read/write/delete and kernel reparse refusal on a verified local volume; Linux uses openat2 O_PATH with kernel no-link/no-mount-crossing resolution. Unknown metadata backends/mappings fail closed. This prevents an ancestor replacement from redirecting metadata traversal through a link. No source-side SQLite lock, WAL/SHM write, checkpoint, migration, vacuum or service change is performed. Private selected paths stay process-local and are not reflected in errors/logs. See [research and platform limits](docs/native-capture-research.md) and [guard tests](docs/native-capture-test-results.md). No conversation-text privacy filter or completed native capture is claimed where no source reader exists.

Settings discovery probes only fixed numeric-loopback model-list APIs and metadata on verified local known home-directory markers. No DNS/proxies/redirects, custom URLs, credentials, histories or configuration reads are supported. Connect/select/test/disconnect additionally require explicit approval and CSRF. Synthetic tests are bound to the displayed selection revision to reject cross-tab changes. Response bytes (including HTTP framing) and request time are bounded. Consent is process-local and revoked by restart; disconnect serializes with in-flight tests and does not stop upstream compute/services. See [Integrations](docs/integrations.md) for exact limits and unsupported cases. LM Studio/Ollama do not automatically expose application history.

## Files and data

Keep databases, conversation exports, model artifacts, runtime logs, local
configuration, and backups out of public repositories. Review generated artifacts
for private content before sharing them. Static files are resolved within the
static root; traversal outside it is rejected. Dataset version identifiers have
an allowlist and directory containment checks. Trusted local files and filesystem
permissions remain important: this is not a sandbox for malicious datasets,
model files, or training programs.

Existing read APIs return operational paths and diagnostic details to the trusted
local client. Avoid sharing responses that contain private paths or corpus data.
Do not treat the absence of a browser exploit as permission to publish data.

## Reporting a vulnerability

Do not include personal conversations, datasets, secrets, or private machine paths
in public issues. If the repository provides private vulnerability reporting,
use it. Otherwise ask the maintainer for a private reporting channel without
posting exploit payloads or sensitive evidence publicly. Provide the affected
version, a minimal reproduction using synthetic data, and the expected boundary.

## Public Core Phase5 candidate boundary

The separate allowlisted candidate adds atomic stale-token/flag preservation, contextual privacy gates, single-storage-instance guard, fixed manifest-verified JSONL delivery and bounded coherent backup/new-location restore. It explicitly refuses inherited legacy unauthenticated-ingest override with503 before shared auth/parse/DB. This changes no protected original helper, running integration or production credential setting. Actual Windows/Ubuntu security/browser acceptance and remaining limitations are in [Phase5 verification](docs/public-core-phase5-verification.md). Local single-operator trust, no RBAC/public-network certification, HMAC replay limits, asserted reviewers and migration-loader debt remain; proposed SQL, models and private extensions are not activated.
