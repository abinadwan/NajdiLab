# NajdiLab Core API scope

All routes are loopback-only with shared Host/Origin/Fetch Metadata checks. Native POST /turn requires bearer/HMAC credentials. POST /hermes-hook is BLOCKED with 409 HERMES_UNSAFE_SOURCE before body reading/parsing/storage, regardless of credentials/legacy mode. Hermes v0.22.5 sender fields filtering and enabled:false cannot be trusted; external disconnect remains unverified. Do not route unsafe Hermes events through /turn as a workaround. Other mutations require JSON and X-NajdiLab-CSRF from GET /session. Requests are capped at 2 MiB. .env is not auto-loaded. No public-network, multi-user identity or HMAC replay-freshness guarantee.

Prefix below: /api/v1. Numeric review/conversation IDs and bounded local version identifiers are validated; no arbitrary path input is accepted.

| Method | Supported paths | Purpose |
|---|---|---|
| GET | /session, /health, /config | Process session, profile and safe configuration |
| GET | /conversations, /conversations/{id} | Search/model/channel filter and full context |
| GET | /reviews?scope=all, /reviews/{id} | Candidate read-only review list/detail; scope all/pending/reviewed/eligible/excluded/evaluation, search; list limit 500 |
| GET | /review-queue, /reviewed | Reused core inspection; reviewed default excludes inactive rows, use candidate scopes for those |
| GET | /dataset-records, /analytics | Eligibility/statistics inspection; this does not run training |
| GET | /exports, /exports/readiness, /exports/dedup-report | Local metadata, actionable gates and duplicates; include_demo=0 or1 |
| GET | /dataset-versions, /dataset-versions/{version} | Registered local versions, files, counts, manifest and hashes |
| GET | /dataset-versions/{version}/{health,quality-findings,balance,eval-sets,release-validation} | Read-only verified-byte diagnostics, actual holdout and dataset checks; no publication clearance |
| GET | /dataset-versions/{version}/files/{filename} | Attachment for manifest-authorized sft.jsonl, multi_turn.jsonl, direct_language.jsonl, preference_pairs.jsonl or evaluation_holdout.jsonl only |
| POST | /turn | Credentialed generic completed-turn ingestion; no external Hermes operation |
| POST | /hermes-hook | BLOCKED 409 before body reading; no sender privacy or disconnect guarantee |
| POST | /conversations, /messages | Explicit core conversation/message creation |
| POST | /reviews/{id}, /reviews/{id}/{approve,correct,exclude,restore,ignore,delete} | Mandatory optimistic revision and atomic candidate policy |
| POST | /exports | Explicit boolean include_demo, existing eligibility/split/mask/dedup gates plus candidate privacy/context checks |

Review mutation body requires nonempty string expected_updated_at. Correction requires a correction status and nonempty string corrected_response. Optional changed flags must be booleans (or 0/1), not strings/null. Omitted flags/notes/tags/reviewer are preserved. Reviewer assertion is human/import/ai_suggestion; it is not RBAC identity. Privacy, evaluation, exclusion and fact-check restrictions force training eligibility off. Full event-history schema is not activated.

Saved overlays cannot be discarded through approval. Exclude keeps an existing correction and marks it excluded; restore preserves restrictions and is pending/ineligible. A restored pending correction must be resolved explicitly with the intended flags before re-excluding. Ignore/delete of a retained correction refuse and direct the user to Exclude. These conservative semantics are deliberately not a drop-in private-application API promise.

Missing revision: 428. Stale revision: 409 REVIEW_CONFLICT with zero writes. Invalid fields/JSON: 400; wrong media type: 415; path/file denied: 403; unknown core routes/IDs: 404; integrity mismatch: 409. Removed execution/extension paths return ordinary404; no extension interface is packaged. Unsupported methods perform no mutation. No model execution or extension loader.

Version source is managed candidate-local exports only. Registered manifest equality, exact filename inventory, size/count/SHA and regular-file checks apply before diagnosis/delivery. Only selected JSONL files download; full_archive.json, dedup reports, manifest downloads, DBs, backups, secrets and model files are denied. Data is private by default regardless of these checks.

Only GET and POST are supported. Other methods return405 METHOD_UNAVAILABLE with Allow: GET, POST after request-boundary checks; HEAD has no response body. A forbidden Host/Origin or invalid mutation CSRF is still rejected before routing.

Candidate-only native ingestion fails closed with503 LEGACY_INGEST_DISABLED when NAJDILAB_ALLOW_LEGACY_INGEST=1 is inherited, with or without credentials and before parsing/DB writes. Remove that override and use the documented credential contract. Shared original compatibility code/production settings are unchanged.
