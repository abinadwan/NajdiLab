# Local HTTP API

Base URL is `http://127.0.0.1:8770` or the selected loopback port. [Generated route inventory](api-routes.md) is authoritative for implemented paths. This is a trusted local-operator API; no multi-user identity/RBAC or public-hosting support is claimed.

Host/Origin/Fetch Metadata checks run before dispatch. Foreign/null/cross-site or duplicate security headers and ambiguous framing are refused. Mutations require bounded application/json (2 MiB) and `X-NajdiLab-CSRF` from `GET /api/v1/session`. Native `POST /api/v1/turn` instead needs configured bearer OR raw-body HMAC; browser ingest also needs CSRF. Hermes hook returns409 `HERMES_UNSAFE_SOURCE` before reading the body regardless of credentials/legacy mode. No configured ingest secret gives503; invalid/missing configured credentials401. Body-only HMAC and bearer tokens have no replay freshness; the optional timestamped signature (`X-NajdiLab-Timestamp`, see [SECURITY](../SECURITY.md#freshness-and-replay-qa-07)) refuses stale and replayed requests, and `NAJDILAB_REQUIRE_FRESH_SIGNATURE=1` makes it mandatory. CSRF is not reviewer identity.

JSON preserves Unicode and compatibility enums, including dataset-specific review decisions. Invalid framing/JSON/body size generally returns400, media type415, boundary/CSRF403, missing routes404, and confirmed export/integrity conflicts409 with their machine-readable code. Domain response shapes can include message/details/readiness; do not interpret localized prose as a stable schema.

Record lists are paged (UX-20): `GET /api/v1/conversations`, `/api/v1/reviewed`, `/api/v1/manual-data` and `/api/v1/chat/sessions` accept `limit` (1–500, default 100) and `offset` (0 or more), and return `items` plus `page` = `{total, limit, offset, returned, has_more, max_limit}`. An out-of-range or non-integer value returns 400; nothing is silently clamped or truncated. Ordering has an id tie-breaker, so pages do not repeat or skip records while the data is unchanged; records added or removed between requests can shift later pages. For manual data, `summary` and `facets` always describe the full filtered set, not only the current page.

| Family | Contract |
|---|---|
| Health/session/config | Read local identity, process session token and controlled vocabularies; never share database paths/tokens |
| Chat | Complete-turn UUID receipts, revisions, separate consent, stop/archive and exact context admission; [routes](chat-workspace.md#routes) |
| Integrations/hardware | Explicit session-only consent and bounded local evidence; [contract](integrations.md) |
| Conversations/turn ingestion | Originals and PENDING review; `source_message_id` deduplicates within one conversation |
| Reviews | Explicit approve/correct/exclude/restore and supported atomic bulk actions; [review](review-and-quality.md) |
| Dataset eligibility | `GET /api/v1/dataset-records`; retained eligibility field names do not imply execution |
| Manual authoring | `POST /api/v1/manual-data/sft`, `/direct`, `/preference`; existing update/version/archive/history routes per inventory |
| Dataset versions | Build/derive/overlap/freeze and read-only quality/holdout/dedup/balance/catalog; immutable earlier bytes |
| External Unsloth export | `POST /api/v1/unsloth-exports`, verified immutable selected-file download; [contract](dataset-export.md) |
| Dataset remediation | Phase38/39/resolution/freeze review evidence remains, subject to privacy and actual available records |

All `/api/v1/training/**`, `/api/v1/evaluation/verify-adapter`, `/api/v1/phase3/**` and platform-status endpoints are removed. Old training-dataset/manual training-data paths are replaced by the dataset paths above. There is no410 execution shim or historical job/log/metric HTTP interface. Stored private evidence is retained independently of route availability.

No multipart/upload, arbitrary endpoint/model path, universal Idempotency-Key or generated OpenAPI contract is promised. Check state before retrying a timed-out write; idempotency is operation-specific. Native turn payload requires `conversation_id`, `user_message`, `assistant_response`; optional `source_message_id` provides deduplication. Use only independent synthetic data and confirm the intended checkout's health/database before any test write. [Security](../SECURITY.md).
