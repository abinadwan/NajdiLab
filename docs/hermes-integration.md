# Passive Hermes integration — NajdiLab v1.1

The integration copies completed turns through Hermes `post_llm_call` events. The turn path builds a small payload and enqueues it; a background daemon performs HTTP requests. Failure emits a warning, without changing the response or restarting Hermes. This is an integration contract; the external Hermes implementation and its dependencies are not bundled here.

## Configuration

Configure `hooks.outbound` in the external Hermes `config.yaml`:

```yaml
- name: najdilab-passive
  enabled: true
  url: http://127.0.0.1:8770/api/v1/hermes-hook
  events: [post_llm_call]
  timeout: 1
  secret: <private-shared-secret>
  fields:
    - turn_id
    - user_message
    - assistant_response
    - model
    - provider
    - platform
    - conversation_key_hash
    - system_prompt_version
    - generation_settings
    - acceptance_test
```

`<private-shared-secret>` is a documentation placeholder, not a usable default. Configure the same high-entropy value as the NajdiLab process variable `NAJDILAB_INGEST_TOKEN`, using private deployment configuration. Do not commit either value. The existing external deployment is unchanged by this branch.

To stop collection, set `enabled: false` and reload/restart the external gateway through its normal operational process. This requires no NajdiLab data deletion. See [SECURITY.md](../SECURITY.md) for the current ingest protection boundary before connecting a client.

## Privacy and fields

- `conversation_key_hash` is SHA-256 of an internal conversation key; do not send phone numbers, messaging IDs or the raw key. A hash is pseudonymous metadata, not guaranteed anonymization.
- `system_prompt_version` contains a hash only; system prompt text stays in Hermes.
- `generation_settings` allows only `temperature`, `top_p`, `top_k`, `seed` and `context_length`.
- Do not send headers, API keys, cookies, full conversation history, or tool calls/results.
- NajdiLab preserves the original response and creates a `PENDING` review with `training_eligible=false`.
- User and assistant text can still contain private material. Review consent, retention and training rights separately.

## Continuity and idempotency

The conversation hash is a stable source identity. `turn_id` becomes `source_message_id`; resending the same event returns the existing record rather than duplicating messages or reviews.

## Failure behavior

Collection is best effort and fail open for the external user response. When NajdiLab is unavailable or slow, Hermes continues delivery. Timeouts/retries belong to the background worker; a bounded queue drops excess events with a warning rather than blocking the turn path.

## Endpoints

`POST /api/v1/hermes-hook` accepts the filtered lifecycle payload and creates the conversation, user message, assistant message and review in one transaction. `POST /api/v1/turn` remains the generic local collector endpoint. Configure the actual selected port in both systems.

## Authentication and controlled migration

The default is fail closed: absent/empty `NAJDILAB_INGEST_TOKEN` produces HTTP 503 on both ingest routes. A configured secret requires one valid credential scheme:

- Native client: `Authorization: Bearer <same-secret>`.
- Hermes outbound hook with `secret` configured: `X-Hermes-Signature-256: sha256=<digest>`, where the digest is lowercase hexadecimal HMAC-SHA256 of the exact raw UTF-8 request body, using the secret's UTF-8 bytes as key. Sign the bytes actually sent; reformatting JSON changes the signature.

Missing/invalid/duplicate/mixed credentials produce 401 when a secret is configured. HMAC proves possession of the secret and body integrity; it provides no timestamp/nonce replay defense. Existing turn-id idempotency is not a general replay-prevention mechanism.

Before deployment, prepare the shared secret in private storage, configure the server launch environment and the external hook, then perform a controlled restart/reload through each system's authorized operational process. Verify a synthetic authorized turn is accepted and unauthenticated ingestion is refused, without exposing real conversations or the secret in logs. Keep the old deployment recoverable until compatibility is proved. This guide does not authorize changing the current external installation.

`NAJDILAB_ALLOW_LEGACY_INGEST=1` deliberately allows native ingestion without credentials and emits a startup warning. It is an explicit migration exception, not the default; do not use it to avoid configuring a secret. Bad supplied credentials still fail. Browser requests retain Origin/Host/Content-Type and CSRF checks. All non-ingest writes by scripts need the session CSRF header described in [SECURITY.md](../SECURITY.md).

## Optional integration acceptance utility

`scripts/acceptance_v11.py` is a write-capable synthetic integration check, not a normal startup check. Use only a disposable installation and compatible collector; it modifies demo review/export state in that installation. Set `NAJDILAB_ACCEPTANCE_WRITE=1`, provide `NAJDILAB_INGEST_TOKEN`, and set `NAJDILAB_HERMES_ROOT` to a compatible external Hermes checkout if it is not adjacent. Both webhook test targets use the configured shared secret. This preparation did not execute the live integration utility; raw HMAC compatibility was independently checked against the Hermes implementation. The simple `scripts/ingest_test.py` requires the shared secret before any network attempt.
