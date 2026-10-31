# Local HTTP API

## Current scope override (2026-10-31)

See [Chat and Unsloth routes](chat-workspace.md#routes). Training namespace writes now return **410 TRAINING_EXTERNAL_ONLY before body parsing**; old mutation branch documentation below is historical. Only job/attempt/log/metric history and dataset/quality reads remain in that namespace. Startup no longer initializes training/runtime registries. Applied schema remains intact; Chat adds migrations 005 and 006.

New frozen exports include `privacy_policy=no_flagged_or_excluded_context_v1`. Privacy-tainted full context blocks export without trimming. The new Unsloth endpoint requires this attestation and creates conversational prompt/completion JSONL with completion-only external loss, separate from old export contracts. No merge/deploy/training action is provided.

## Retained API reference and historical compatibility

Base URL: http://127.0.0.1:8770 (or selected port). This is a trusted local-operator API, not a public/multi-user service. [Complete implemented route inventory](api-routes.md) is generated from routing source; no planned endpoints are included. Regex groups represent path parameters. Success wrappers and domain dispatch names link to actual handlers. [service](../app/service.py), [dataset platform](../app/dataset_platform.py), [training](../app/training_control.py), [runtime](../app/runtime_control.py), [review integrity](../app/review_integrity.py) and phase modules own payload validation and returned records.

## Common wire contract

JSON objects use UTF-8; fields/API enums remain stable, including legacy Arabic Phase 3.9 decision values. Query values are strings, last duplicate value selected by current parser. Integer path IDs identify existing records; dataset/runtime identifiers use the allowlisted route patterns. No file-upload/multipart route is implemented. A path field in a runtime/model payload is not a general upload API and needs local operator trust.

All methods first validate Host (loopback and listening port), Origin and Fetch Metadata. Foreign/null Origin, cross-site, duplicate security headers and ambiguous framing are rejected. Mutations require application/json and bounded bodies (2 MiB). No permissive CORS is enabled. Cookies are not an identity system here.

| Operation | Required authorization |
|---|---|
| GET /api/v1/session | Accepted local request; returns ok and csrf_token; process-memory token changes on restart |
| GET routes | Request boundary checks; local trusted-client access, no per-user RBAC |
| POST /turn | Configured NAJDILAB_INGEST_TOKEN with bearer OR raw-body HMAC; browser requests also need CSRF |
| POST /hermes-hook | BLOCKED 409 before body reading, even with credentials/legacy mode; existing request boundaries run first |
| POST /integrations actions | CSRF plus exact approved=true, test additionally binds selection_revision; discovery accepts empty object only |
| Other POST/PATCH/DELETE | X-NajdiLab-CSRF from session, including native scripts; training approvals remain additional |
| Training/download/export/recovery actions | Domain validation, fingerprints and action-specific confirmation/authorization where implemented; never infer permission merely from a token or HTTP 200 |

No configured Ingest secret yields 503. Invalid/missing configured credentials yield 401. Boundary/CSRF rejection is generally 403; invalid JSON/body framing 400; media type 415; oversized body 400 in the current handler. Domain ValidationError is generally 400, not-found routes 404, dataset/training/integrity errors carry their defined status/code (often 409). Do not assume a uniform error schema: handler errors use ok=false/error with optional code; domain serializers may also include message/details/readiness. Inspect the linked route and machine-readable code, not localized prose. Internal errors return generic text while private local logs retain traceback details.

Legacy NAJDILAB_ALLOW_LEGACY_INGEST=1 is an explicit warned native-only migration exception, not the safe default. HMAC authenticates exact bytes but has no freshness/replay guarantee. CSRF proves request intent, not reviewer identity. See [security](../SECURITY.md) and [Hermes migration](hermes-integration.md).

## Payload and response families

| Family | Request / response contract |
|---|---|
| Health/session/config | GET, no JSON body; health returns ok/service/version/database (local path, do not publish); session returns csrf_token; config exposes controlled vocabularies |
| Conversations/messages | GET filters search/model/channel; numeric detail route returns original messages/reviews. Creation passes JSON to create_conversation/create_message; required fields/defaults are enforced by service, not renamed for English |
| Turn Ingest | conversation_id, user_message, assistant_response required; source_message_id optional dedup key; optional provider/model/channel/provenance metadata. Success includes conversation/message/review IDs, PENDING review_status and duplicate flag under handler's ok wrapper |
| Hermes hook | Intentionally refused before body reading/storage; HERMES_UNSAFE_SOURCE. Historical internal parser is not an enabled HTTP integration |
| Settings integrations | Passive snapshot, bounded read-only discovery, approved runtime connection/selection/synthetic test/local disconnect; see [wire contract and states](integrations.md) |
| Reviews/bulk | Numeric review ID, controlled action enum and full corrected_response where correction required; reviewer metadata/flags per service; transactions preserve originals. Bulk validates all before commit |
| Manual data | SFT/direct/preference JSON with type-specific fields/flags; PATCH/DELETE version/archive/export guards; version/history reads. See service create/update/manual validators |
| Exports/datasets | Query version/filter options; derive/overlap/freeze JSON; responses include manifests, fingerprints, findings or readiness blockers. Failure must not silently replace frozen content |
| Models/runtime | Explicit model identity/revision/path and runtime configuration; prepare/acquire/validate/check/stage/deploy/worker actions are separate. Do not call write actions as health probes |
| Training | Dataset/model/runtime/config snapshot and exact job/attempt identifiers; DRAFT/READY, dry-run, Smoke/Full authorization/start, recovery/resume/cancel have distinct contracts in runtime/training control. Approval token/confirmations are not interchangeable |
| Evaluation/Phase3/38/39 | Locked evidence IDs, human decision/note payloads and verification/freeze readiness; original holdout and legacy decision values preserved. Historical endpoints may require excluded private artifacts |

For full field-level constraints, use the inventory's handler and domain source rather than inventing a portable schema from absent private state. This repository does not claim a generated OpenAPI schema or stable versioning/deprecation policy beyond the documented compatibility rules.

## Synthetic examples in a disposable instance

Run this only against your own empty test checkout and chosen free port. Read health and confirm database identity before writes:

```python
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
base = 'http://127.0.0.1:' + os.environ.get('NAJDILAB_PORT', '8770')
with urlopen(base + '/api/v1/health') as response:
    health = json.load(response)
assert health['ok'] and health['service'] == 'NajdiLab'
assert Path(health['database']).resolve() == (Path.cwd() / 'data/najdilab.db').resolve()
with urlopen(base + '/api/v1/session') as response:
    csrf = json.load(response)['csrf_token']
payload = {'conversation_id': 'synthetic-docs-1',
           'source_message_id': 'synthetic-turn-1',
           'user_message': 'Synthetic greeting', 'assistant_response': 'Hello.'}
headers = {'Content-Type': 'application/json',
           'Authorization': 'Bearer ' + os.environ['NAJDILAB_INGEST_TOKEN']}
request = Request(base + '/api/v1/turn', data=json.dumps(payload).encode(),
                  headers=headers, method='POST')
with urlopen(request) as response:
    result = json.load(response)
assert result['ok']
# Other writes use headers={'Content-Type':'application/json', 'X-NajdiLab-CSRF':csrf}.
```

Turn idempotency applies when source_message_id repeats for the same conversation: the existing assistant/review is returned with duplicate=true. Without that key, repeated requests can append data. Do not retry mutations blindly after timeouts; inspect state first. Other actions have their own idempotency/version/authorization rules; no universal Idempotency-Key header is implemented. Scripts/collector_client.py binds the bundled write-capable test tools to this checkout's health/database before credentials are sent.
