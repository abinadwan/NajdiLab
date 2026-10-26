# 15 — Migration Safety: Loader Guard Requirement (PRQ-MIG-01)

Status: **APPROVED DESIGN REQUIREMENT (P1-06, 2026-10-23). Migrations 005, 006, 007 and proposed 008 stay BLOCKED. No code, file location or database was changed.**

## 1. The hazard (verified)

- `app/db.py:75-90` `apply_migrations()` runs every `migrations/*.sql` not yet listed in `schema_migrations`, in `sorted()` filename order, via `executescript`.
- `app/server.py:509` calls it on **every server start**, before serving.
- So: **copying a file into `migrations/` = executing it at the next restart**, with no approval, no backup, no preflight, and (unless the file has its own `BEGIN…COMMIT`) no atomicity. A stray rollback file would run too, and `*.rollback.sql` sorts before its forward file.

## 2. Blocking rule (effective now)

| Migration | Location | Status |
|---|---|---|
| 005 dataset registry | `plans/phase13/` | BLOCKED (OA-07) |
| 006 review events | `plans/phase2/` | BLOCKED (OA-05 then OA-06) |
| 007 model/training registry | `plans/training-readiness/` | BLOCKED, ON HOLD (OA-09) |
| 008 lifecycle (draft in `07-…` §4 only) | not a file | BLOCKED (OA-08) |

No SQL file may enter `migrations/` until PRQ-MIG-01 is met **and** the specific migration has its own approval.

## 3. Loader guard: required properties (for Phase 1A design and implementation, under OA-05)

| # | Property | Rationale |
|---|---|---|
| L1 | **Startup never applies new migrations.** On start, the server only *verifies* that applied migrations match an expected list. If an unapplied file exists, it refuses to start (or starts read-only) and reports it in the UI | Removes "restart = migrate" |
| L2 | **Allowlist manifest with hashes**: a versioned manifest lists each approved migration filename and SHA-256. A file that isn't listed, or whose hash differs, is refused | Stops stray or edited files |
| L3 | **Explicit apply path** only through a guarded runner (pattern: `scripts/phase13_registry.py`): preflight → verified backup (SQLite backup API) + restore proof → rehearsal on the restored copy → approval token → `BEGIN IMMEDIATE` → integrity and FK checks → record | Every apply is deliberate and reversible |
| L4 | **Rollback scripts can't be loaded**: non-`.sql` suffix (e.g. `.rollback.sqltxt`) or kept outside `migrations/`; the loader rejects any `*rollback*` name | Fixes the sort-order hazard |
| L5 | **Recorded evidence**: `schema_migrations` (or a sidecar table added by the guard's own migration) stores file hash, approver and backup hash | Audit trail |
| L6 | **Already-applied 001–004 stay valid** (their hashes are recorded at guard installation) | No disruption to production |
| L7 | **UI surface**: the System page shows the migration status (applied / pending-blocked / unknown file) read-only. Applying is a data-owner action with re-auth (after S6–S8) | UI-first oversight |

## 4. Bootstrapping note
The guard itself is a **code change**, not a migration (L1/L2 run before any SQL). If L5 needs a sidecar table, that table is created by the guarded runner as the first approved migration under the new regime.

## 5. Acceptance tests (Phase 1A, after OA-05)
1. Placing an unlisted `.sql` file in `migrations/` of a fixture project, then starting the server → it doesn't apply the file and reports `MIGRATION_NOT_APPROVED` (DB hash unchanged).
2. A listed file with a modified hash → refused.
3. A file named `*rollback*.sql` → refused.
4. The guarded runner without token or backup → refuses. With both, on a restore-proof copy → applies atomically; integrity ok; re-run changes 0 rows.
5. Production-like fixture with 001–004 → starts normally; no schema change.
