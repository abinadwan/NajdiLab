# Backup and restore

Source history and private operational state are separate recovery requirements. A source-only clone does not contain the database, Gold/holdout datasets, runtime/model registry, weights, adapters, checkpoints or audit reports. Keep backups and their manifests private; do not publish installation identities, archive names, credentials or storage locations.

## Built-in data backup

From the intended local checkout:

```bash
python scripts/backup.py
```

The Windows and shell wrappers are `scripts/backup.ps1` and `scripts/backup.sh`. The script writes a new timestamped ZIP under local `backups/`. It uses SQLite's online backup API for a consistent database snapshot and includes files under `exports/`. **It does not back up the entire application or ML environment:** `datasets/`, `training/`, `reports/`, checkpoints, model weights, external scripts, interpreter installations and credentials require a separately planned private backup. Exports copied during concurrent mutation are not a globally atomic archive; frozen exports must remain immutable and be hash-verified.

For full recovery, preserve an authorized source revision plus separate inventories of all required state. Record per-file SHA-256 hashes, database table counts, schema migration state, selected model revisions, package versions and restore-test results in a private manifest. Verify scope rather than assuming every directory is included. Restrict archive access and protect any credentials separately in authorized secret storage.

## Isolated restore rehearsal

1. Verify archive and member hashes against the private manifest. Clone the recorded source revision into a new empty directory; never test restoration by overwriting a live installation.
2. Inspect archive member paths and reject absolute paths or traversal before extraction. Restore the database snapshot and immutable export files into the new private recovery checkout. Restore additional datasets, reports and runtime artifacts from their separately verified sources only after comparing existing files.
3. Do not mix a consistent database snapshot with WAL/SHM files from another running instance. Run `PRAGMA integrity_check` (must return `ok`) and `PRAGMA foreign_key_check` (must return no rows) on the restored copy, and compare counts/schema state with the manifest.
4. Verify every declared Gold, holdout, model and adapter hash. Missing files or mismatched fingerprints block use. Preserve Windows and WSL adapter versions independently; an archive does not authorize reconciliation of known adapter drift.
5. Recover Linux artifacts onto a Linux filesystem with tools that preserve permissions and symlinks. A copied virtual environment may depend on an external interpreter, system libraries and original paths. Record those requirements or recreate an isolated environment from verified versions; a project archive is not a full WSL operating-system image.
6. Recreate authorized secrets from secret storage; rotate/reconfigure the ingest secret through [the integration guide](hermes-integration.md). Do not restore transient session/CSRF values as credentials. Runtime checks, READY evidence and training authorizations must be regenerated after restore.
7. Before launch, compare source migrations to the restored schema and set `NAJDILAB_NO_DEMO=1`. Startup automatically applies SQL already in `migrations/`; planned migrations remain separately gated. Reconfigure local paths and external collector/autostart references for the new installation.
8. Run appropriate tests in isolation and record missing private fixtures separately. Start only the restored local instance after review, check health and read-only catalog state, and verify no workload begins automatically.

A successful push or valid ZIP alone does not prove recovery. Require verified source, complete private artifact inventory and a successful isolated restore rehearsal before decommissioning an installation. Preserve existing instances until recovery is proved. This guide grants no migration, training, deployment, export, service-control or deletion approval.
