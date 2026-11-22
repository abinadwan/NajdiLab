# Hermes collection — BLOCKED

Since Phase B, Settings no longer shows Hermes; the integrations API can still report the existence of the known `.hermes` directory using metadata. It does not inspect config, secrets, sessions, history, system prompts, tools, or the Hermes version. Detection is not compatibility verification.

## Safety correction (2026-10-31)

The former guide assumed that `hooks.outbound[].fields` filtered outgoing events and that `enabled:false` stopped delivery. Those assumptions are unsafe for Hermes v0.22.5: the fields allowlist may not be applied and disabled targets may continue sending. **The previous webhook configuration and disconnect instructions are withdrawn. Do not activate them.** Newer/unidentified versions are not presumed fixed.

Receiver-side redaction cannot prevent private data from leaving Hermes. HMAC authenticates a body; it cannot make an overbroad body private. Therefore this release does not configure, connect, or live-test Hermes collection. The integrations API reports `BLOCKED` with `HERMES_UNSAFE_SOURCE`, and attempts to connect/select/test return HTTP 409; Settings shows only the Ollama and LM Studio runtimes.

`POST /api/v1/hermes-hook` now returns HTTP 409 `HERMES_UNSAFE_SOURCE` before reading, parsing, authenticating or storing the body. Host/Origin/framing protections still run first. Valid credentials and `NAJDILAB_ALLOW_LEGACY_INGEST=1` cannot enable this endpoint. The connection closes without draining the body. This is an intentional security compatibility change; existing rows and internal historical parsing/idempotency tests remain intact. `/api/v1/turn` remains a separately authenticated generic collector, **not a bypass for unsafe Hermes delivery**.

## Disconnect verification

“Verify receiver block” confirms only this NajdiLab receiver is closed. The UI/API always reports external sender disconnect `UNVERIFIED`. It cannot prove that Hermes stopped transmitting, removed an outbound target, drained a queue, or stopped another deployment. No external configuration or service is changed.

If an older installation already has an outbound hook, its operator must inspect that configuration privately and arrange removal of the target through its supported reload/restart procedure. Do not rely on `enabled:false`. Do not stop another service casually or publish the configuration/credential. This PR does not execute that operational change. Blocking the receiver does not retract data already transmitted or delete stored records.

### Local evidence about the external sender (QA-06)

NajdiLab cannot inspect or change an installed Hermes, so it cannot prove the sender stopped. It can show whether anything still tries to deliver: `GET /api/v1/hermes-hook/refusals` returns `{"refused": n, "last_refused_at": time or null, "since": process start, "receiver": "BLOCKED"}`. The count covers refused POSTs to `/api/v1/hermes-hook` since this server process started; nothing from those requests (headers, body, address) is stored, and the refusal still happens before the body is read.

To build evidence after removing a Hermes outbound target: keep NajdiLab running through the period in which Hermes would normally send, then read the endpoint. `refused: 0` over that period is local evidence that nothing delivered to this receiver; it is not proof that Hermes stopped sending elsewhere, and a restart resets the count. A non-zero count with a recent `last_refused_at` means a sender is still configured to deliver here.

## Conditions for future enablement

A separately reviewed sender-side bridge must construct a fresh minimal completed-turn payload **before enqueueing/network I/O**. Permit only explicitly consented user/assistant text and necessary pseudonymous identifiers; reject arbitrary keys. Exclude full history, raw system prompts, tools/calls/results, headers, cookies, credentials and raw source identities. Conversation text can itself contain secrets: obtain consent and prove the agreed fail-closed detection/redaction policy rather than claiming arbitrary prose is safe. If privacy verification is unavailable, collect nothing.

Prove raw-wire behavior using synthetic secret/history/system/tool sentinels, unexpected keys, malformed events, retries, queue overflow and errors. Database-only redaction is insufficient. Version-pin the verified sender. Prove disconnect by removing the actual outbound target, applying the supported reload, invalidating queued deliveries, and a bounded synthetic positive/negative observation that deliveries cease. Define ownership and rollback without data loss. No success label is justified until these proofs exist.

## Retired utility

`scripts/acceptance_v11.py` exits `BLOCKED` before external imports, network or writes, even if its former opt-in is set. Its previous database-only privacy PASS was not a sender-side privacy guarantee. Use the fixture-only [integration tests](../tests/test_integrations_http.py), [request security tests](../tests/test_http_security.py) and [integration guide](integrations.md). No installed Hermes instance is needed or contacted.
