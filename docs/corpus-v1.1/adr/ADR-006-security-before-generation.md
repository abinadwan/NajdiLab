# ADR-006 — Security prerequisites ship before any generation or new review workflow

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
Phase 1A delivers the Host allowlist, Origin checks, JSON Content-Type enforcement and a CSRF token (S1–S4) without schema changes. Phase 2 delivers reviewer profiles, sessions and the server-side authorization matrix (S6–S8) with migration 008. The ingest token (S5) waits for authorization to change Hermes configuration.

## Consequences
Named-reviewer accountability, which G3 requires, is unavailable until S6–S8 land, so the pilot can't start before Phase 2.
