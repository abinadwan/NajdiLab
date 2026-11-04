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
`Cache-Control: no-store`. Operation-specific consent and validation remain additional requirements.

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

### Freshness and replay (QA-07)

A body-only signature (`X-Hermes-Signature-256` over the raw body) and a bearer
token authenticate the sender but do not prove freshness: a captured request can be
replayed. Replays of a turn that carries `source_message_id` are deduplicated; other
replays create a duplicate turn and a new PENDING review.

Senders that can be updated should use a **timestamped signature**: send
`X-NajdiLab-Timestamp: <unix seconds>` and sign `"<timestamp>.<raw body>"` with
HMAC-SHA256 in `X-Hermes-Signature-256: sha256=<hex>`. The server refuses a
timestamp more than 300 seconds from its clock (401 `STALE_SIGNATURE`) and a
signature it has already accepted within that window (409 `INGEST_REPLAY`); sign
each attempt, including retries, with a new timestamp. The replay record is kept in
memory only: after a restart, a captured request is still refused once its
timestamp leaves the window. Only valid signatures are recorded.

Body-only signatures and bearer tokens keep working so existing senders do not
break. Set `NAJDILAB_REQUIRE_FRESH_SIGNATURE=1` once every sender uses timestamps;
the server then refuses body-only signatures, bearer tokens and the credential-less
legacy mode (401 `FRESH_SIGNATURE_REQUIRED`). Keep server and sender clocks
synchronized. Payload sizes are bounded before authentication.

## Local runtime integrations

Settings discovery probes only fixed numeric-loopback model-list APIs and metadata on verified local known home-directory markers. No DNS/proxies/redirects, custom URLs, credentials, histories or configuration reads are supported. Connect/select/test/disconnect additionally require explicit approval and CSRF. Synthetic tests are bound to the displayed selection revision to reject cross-tab changes. Response bytes (including HTTP framing) and request time are bounded. Consent is process-local and revoked by restart; disconnect serializes with in-flight tests and does not stop upstream compute/services. See [Integrations](docs/integrations.md) for exact limits and unsupported cases. LM Studio/Ollama do not automatically expose application history.

## Hugging Face Direct (model library)

One of two outbound paths: explicit, CSRF-protected requests to `huggingface.co` (search, revision-pinned details, bounded header reads, downloads). HTTPS only; every redirect hop must stay on `huggingface.co`, `*.huggingface.co` or `*.hf.co` at port 443; no user-supplied URLs, credentials, cookies or tokens; gated and private repositories are refused. Trending and recommendations add only list pages (`/api/models`, cursor validated), repository details and base-model tags, each after a button press; hardware facts used for recommendations stay local. Only `.gguf` files are fetched (never repository code, configuration or packages), into `data/models/huggingface/` only, after a storage preflight with a safety reserve, with live free-space monitoring, and are usable only after their published size and SHA-256 match. NajdiLab Native refuses unverified managed files, and nothing loads without a separate approval. Chat text, datasets and hardware details are never sent. Details and threat table: [Hugging Face Direct](docs/development/HUGGING_FACE_DIRECT.md#10-security-boundaries).

## Managed llama.cpp runtime

The other outbound path: an explicitly approved installation of the **pinned** llama.cpp build, from `github.com` and then only GitHub's asset hosts (`release-assets.githubusercontent.com`, `objects.githubusercontent.com`) over HTTPS at port 443, at most three redirects, no credentials. Every archive must match its pinned size and SHA-256 before it is opened; extraction refuses absolute paths, `..`, unexpected names, devices, hard links and escaping symlinks, and writes into a fresh staging folder. The build becomes active only after `--version` reports the pinned build and commit, `--list-devices` shows its backend's device and a tiny locally generated model computes on that device. Before each Native start the files' sizes and times and the server's SHA-256 are re-checked. The GPU/driver read is local, needs approval and is never sent. Install, rollback and uninstall are refused while Native runs; processes bind 127.0.0.1 with a random key and are stopped only through NajdiLab's own handle. An owner-supplied `NAJDILAB_NATIVE_SERVER` is never changed. Details: [Managed runtime](docs/development/MANAGED_RUNTIME.md#3-safety-rules).

## Files and data

Keep databases, conversation exports, model artifacts, runtime logs, local
configuration, and backups out of public repositories. Review generated artifacts
for private content before sharing them. Static files are resolved within the
static root; traversal outside it is rejected. Dataset version identifiers have
an allowlist and directory containment checks. Trusted local files and filesystem
permissions remain important: trusted source/data provenance is still required.

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

The separate allowlisted candidate adds atomic stale-token/flag preservation, contextual privacy gates, single-storage-instance guard, fixed manifest-verified JSONL delivery and bounded coherent backup/new-location restore. It explicitly refuses inherited legacy unauthenticated-ingest override with503 before shared auth/parse/DB. This does not operate a running integration or alter production credentials. Actual Windows/Ubuntu security/browser acceptance and remaining limitations are in [dated verification evidence](docs/verification-evidence.md). Local single-operator trust, no RBAC/public-network certification, HMAC replay limits, asserted reviewers and migration-loader debt remain; no proposed SQL or model execution is activated; the deleted extension interface is not an enablement path.
