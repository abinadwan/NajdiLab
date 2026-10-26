# ADR-009 — Adapter drift is reconciled by verification, never by overwriting

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
Neither adapter copy is replaced in Phase 1. Reconciliation follows `../06-adapter-drift-k2.md`: three-way diff against git HEAD (`6885fe30…`), isolated tests, an owner decision, a git commit, deployment only through the hash-verified `deploy-adapter` path (which backs up the destination), a fresh runtime check, and correcting the status documents from measured hashes.
