# 05 — Security Prerequisites (CSRF/Origin, server-side authorization, reviewer identity)

> Historical design baseline from 2026-10-23. The English-readiness branch adds request/ingest protections; see [current security behavior](../../SECURITY.md). The tables below preserve the original observations and proposed S1–S8 scope, not a current implementation claim.
Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23). To be implemented, under separate approval, in Phase 1A (S1–S5) and Phase 2 (S6–S8). Nothing has been changed.**

## 1. Current state (verified 2026-10-23)

| Control | Present? | Evidence |
|---|---|---|
| Loopback-only bind | Yes | `app/server.py:506-508` refuses any host other than `127.0.0.1` |
| Security headers | Yes | `server.py:108-120`: CSP `default-src 'self'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` |
| Body size limit | Yes | `_body`, `server.py:136-150` (2 MB) |
| Content-Type enforcement on writes | **No** | `_body` parses JSON regardless of `Content-Type` |
| Origin / Referer check | **No** | `do_POST` (`:306`), `do_PATCH` (`:471`) and `do_DELETE` (`:489`) dispatch without checks |
| Host header check (DNS-rebinding defence) | **No** | — |
| Authentication / sessions | **No** | Single local user |
| Reviewer identity | Category only | `_reviewer` (`service.py:85-90`) accepts `human`, `ai_suggestion` or `import` |
| Ingest authentication | **No** | `POST /api/v1/hermes-hook` (`:316`) and `/api/v1/turn` (`:314`) accept any local caller |
| Training authorization | Strong | Single-use, 5-minute token bound to job, dataset, staging, model, runtime, adapter, tokenizer and template fingerprints (`runtime_control.py:761-775`) |

## 2. Threats

| ID | Threat | Today |
|---|---|---|
| T1 | **CSRF**: any web page open in the operator's browser sends `POST http://127.0.0.1:8770/api/v1/...` with `Content-Type: text/plain` (a "simple" request, so no CORS preflight). The server parses it and changes state: reviews, manual data, bulk actions, exports, derive/freeze | Exploitable for every write endpoint. Full training is protected by the token |
| T2 | **DNS rebinding**: an attacker domain re-resolves to 127.0.0.1 and reads `/api/v1/*` (conversations, datasets) or writes | No Host check |
| T3 | Local process spoofing ingest | Accepted |
| T4 | No accountability: decisions can't be attributed to a person | Category only |
| T5 | Self-approval of generated data | Not preventable without identity |

## 3. Fixes

### Phase 1A: no schema change, compatible with Hermes as configured today

| ID | Fix | Detail | Compatibility |
|---|---|---|---|
| S1 | **Host allowlist** | Accept only `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}; otherwise 421/403 for all methods | Hermes posts to `127.0.0.1:8770` (`docs/hermes-integration.md`), so it's unaffected |
| S2 | **Origin check on state-changing methods** | POST/PATCH/PUT/DELETE: if an `Origin` (or, failing that, `Referer`) header is present it must equal `http://127.0.0.1:<port>` or `http://localhost:<port>`; otherwise 403 `CROSS_ORIGIN_REJECTED` | Server-side clients (Hermes worker) send no Origin, so they're unaffected |
| S3 | **JSON Content-Type required** on writes | `Content-Type: application/json` required; otherwise 415. This forces a CORS preflight for any cross-origin browser request, and the server sends no CORS headers, so the browser blocks it | The UI already sends JSON (verify in Phase 1A tests) |
| S4 | **CSRF token** (synchronizer) | A per-process random token issued by `GET /api/v1/session` and required as `X-NajdiLab-CSRF` on browser writes. Ingest endpoints are exempt only if S5 is in place, or are temporarily exempt with S1–S3 | UI change only |
| S5 | **Ingest token** (deferred until Hermes config change is authorized) | `X-NajdiLab-Ingest-Token` for `/hermes-hook` and `/turn`, stored outside git (gitignored path) | **Requires a Hermes config change: out of scope until separately approved** |

### Phase 2: needs migration 008

| ID | Fix | Detail |
|---|---|---|
| S6 | **Reviewer profiles** | Table `reviewer_profiles(id, display_name, roles_json, native_najdi, active, pin_hash, created_at)`. Local profiles with a PIN hashed by PBKDF2-HMAC-SHA256 (stdlib, ≥ 200k iterations, per-profile salt). **DF-03** decides PIN vs another mechanism |
| S7 | **Sessions** | `HttpOnly; SameSite=Strict` cookie bound to a profile, 8-hour idle expiry, server-side session map; re-authentication for data-owner actions (freeze, authorize training, run generation batch) |
| S8 | **Server-side authorization matrix** | Enforced in the handler before dispatch (below). The UI only hides buttons; the server decides |

### Authorization matrix (S8)

| Action | Role required | Extra rule |
|---|---|---|
| Create/edit Gold item, submit | author | — |
| Approve/reject/request changes on a manual item | reviewer | Not the item's author. For Silver/Bronze, not the batch starter |
| FULL correction confirmation | reviewer (second) | ≠ the correcting reviewer (DF-02) |
| Conversation review decisions (existing) | reviewer | Actor recorded in `review_events` (006) |
| Start a generation batch | data_owner | Re-auth; G1 pass recorded for the generator version |
| Derive / export / freeze dataset | data_owner | Re-auth for freeze |
| Training job READY / dry run / authorize / start | data_owner | Existing token flow plus re-auth |
| Adapter deployment | data_owner | Re-auth; K2 reconciliation rules (`06-adapter-drift-k2.md`) |
| Read-only views | any profile | — |

## 4. Acceptance tests (to be written in Phase 1A/2)

1. Cross-origin POST (`Origin: http://evil.example`) to every write route → 403. No state change (DB hash unchanged in the fixture).
2. `Content-Type: text/plain` write → 415.
3. `Host: attacker.example` → rejected for GET and POST.
4. A request with no Origin and correct Host (Hermes-like) to `/api/v1/hermes-hook` → accepted (until S5).
5. Browser write without a valid CSRF token → 403.
6. A reviewer approving their own Silver item → 403. An `ai_suggestion` actor approving → 403.
7. Freeze or training authorization without data-owner re-auth → 403.
8. All existing tests still pass, with the UI flows updated to send the token.

## 5. Residual risks
Any local process running as the same Windows user can still read the DB file directly. That's out of scope for web hardening and is recorded in the risk register (K5b).
