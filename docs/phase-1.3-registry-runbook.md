# Phase 1.3 Dataset Registry — Production Runbook

Status: preparation complete; production execution is **not approved**.

## Prepared artifacts

- Proposed SQL: `plans/phase13/005_dataset_registry.sql` (deliberately outside `migrations/`).
- Registry implementation: `app/dataset_registry.py`.
- Guarded runner: `scripts/phase13_registry.py`.
- Preflight report: `reports/phase13-registry-preflight.json`.
- Preparation/backup report: `reports/phase13-registry-prepare.json`.
- Isolated rehearsal report: `reports/phase13-registry-rehearsal.json`.

The SQL must remain outside the automatic migrations directory until REG-09 is explicitly approved. The current application calls `apply_migrations()` at startup; placing 005 there prematurely could modify production during an unrelated restart.

## Verified preparation commands

Read-only preflight:

```powershell
python .\scripts\phase13_registry.py preflight --output .\reports\phase13-registry-preflight.json
```

Consistent WAL-aware backup plus isolated restore proof:

```powershell
python .\scripts\phase13_registry.py prepare --output .\reports\phase13-registry-prepare.json
```

Isolated rehearsal only:

```powershell
python .\scripts\phase13_registry.py rehearse --database .\backups\<restore-proof.db> --output .\reports\phase13-registry-rehearsal.json
```

## Production execution gate

Do not run this command without a new, explicit user approval for REG-09:

```powershell
python .\scripts\phase13_registry.py execute --backup .\backups\<verified-pre-migration.db> --approval-token REG-09-APPROVED --output .\reports\phase13-registry-production.json
```

The runner refuses production execution when the token or verified backup path is absent. Approval must be current and separate from approval to prepare or test.

## Transaction behavior

1. Re-discover filesystem and legacy SQLite sources.
2. Stop before writes on invalid/missing manifests, missing declared files, missing legacy paths, duplicate IDs/paths, hash differences, state differences, or count differences.
3. Open `BEGIN IMMEDIATE`.
4. Create both additive tables and their index.
5. Upsert nine canonical versions and nine physical locations.
6. Run foreign-key validation.
7. Commit only when all checks succeed; otherwise roll back DDL and rows together.
8. Reapplying identical evidence produces zero row changes.

## Post-execution verification (after approval only)

- `PRAGMA integrity_check` must equal `ok`.
- `PRAGMA foreign_key_check` must return zero rows.
- Both canonical tables must contain exactly nine rows.
- Re-run preflight and require zero conflicts.
- Compare canonical and legacy/read-only catalog results for 9/9 IDs, paths, counts, states, manifest hashes, and content hashes.
- Compare protected SHA-256 inventory before/after.
- Test API and UI before enabling canonical reads.

## Recovery

Before any consumers use the new tables, rollback is additive and can be performed in one explicit transaction by dropping the location table, then the version table, then removing the migration record if one was later added. That operation requires separate approval.

If any consumer has written to or depended on the new tables, do not use table-drop rollback. Stop NajdiLab only with explicit operational approval, restore the verified SQLite snapshot, re-run integrity/FK checks, and then restart only the NajdiLab process. Hermes, Ollama, and OpenClaw must not be stopped or restarted.

Current verified snapshot:

- `backups/phase13-pre-migration-20261008-213159.db`
- Restore proof: `backups/phase13-pre-migration-20261008-213159-restore-proof.db`
- Backup SHA-256: `8895cdeeea3da0e76bc2dae6e5292a3de73f6f98647f79b855d40c48746d6906`
- Restore integrity: `ok`; foreign-key errors: 0.

