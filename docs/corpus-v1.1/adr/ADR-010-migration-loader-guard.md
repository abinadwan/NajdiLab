# ADR-010 — No SQL enters `migrations/` until a loader guard exists

- Status: Accepted (Phase 1 rev. 2, owner approval 2026-10-23) · Date: 2026-10-23

## Context
`apply_migrations()` (`app/db.py:75-90`) runs every unapplied `migrations/*.sql` on each server start (`app/server.py:509`), with no approval, backup or allowlist.

## Decision
Migrations 005, 006, 007 and draft 008 stay blocked. Before any SQL can enter `migrations/`, Phase 1A implements a loader guard: startup verifies only; a hash allowlist; explicit application through a guarded runner with backup, restore proof, rehearsal and token; rollback files unloadable; UI status (`../15-migration-loader-guard.md`).

## Consequences
"Restart = migrate" is eliminated. Each migration still needs its own owner approval (OA-06…OA-09).
