# Backup and restore before reinstalling Hermes

Backup date: 2026-10-26 (Asia/Riyadh). Existing private repository:
https://github.com/abinadwan/NajdiLab, branch `main`.
The starting commit was `bcdf4a77f5c8f474530f089ab1f06f0be1c01259`.
This backup preserves that history and the current Windows source changes.

## Two required parts

1. GitHub contains source, tests, static assets, SQL migrations, configuration schemas,
   documentation and secret-free example launch variables.
2. The independent local backup contains private data and runtime artifacts.
   GitHub alone cannot restore an operational instance.

The local backup directory is `C:\Users\Admin\NajdiLab-Backups\2026-10-26-pre-reinstall`.
Treat the entire directory as private. Its ACL restricts access to the Windows owner,
SYSTEM and Administrators. Do not upload its archives or reports.
Archive SHA256 values, member hashes, database table counts, test logs, source inventory,
restore-test results and the final commit URL are in the local backup report and manifests.

## Git exclusions

Excluded from Git: `data/`, `datasets/`, `exports/`, `backups/`, `reports/`,
`training/`, `checkpoints/`, generated caches/test output, logs, model binaries,
credentials and messaging sessions. The scratch fragment
`scripts/najdilab_training_adapter.py.tmp` is retained only in the local archive.
No LFS or large model upload is used. Existing test sentinels are dummy values.
The original author email remains in historical commit metadata to preserve history.
No Hermes/Router development files are added to this repository.

## Restore procedure

1. Verify `SHA256SUMS.txt` and all archive verification JSON files first.
   Clone this repository into a new empty directory and compare its HEAD to the final
   commit in the local report. Never overwrite an existing installation as a test.
2. Extract `archives/windows-project.tar` into a separate private recovery directory.
   Restore `data`, `datasets`, `exports`, `training`, `reports`, `checkpoints`, and
   historical `backups` into the new clone only after comparing existing files.
   The archive contains a consistent SQLite online snapshot; do not combine it with
   live database WAL/SHM files from another instance.
3. Check the recovered database using `PRAGMA integrity_check` and
   `PRAGMA foreign_key_check`; compare table counts to the manifest. Verify Gold
   files and adapters against the per-file SHA256 manifests before use.
4. The separate WSL archive preserves `/home/najdi/najdi-training`, including data,
   models, checkpoints, runs, evaluations, scripts and `.venv`. Extract it on a Linux
   filesystem using tar so symlinks and executable modes survive. Preserve the
   registered `NajdiTrain` distribution if it still exists; do not overwrite it.
   To rebuild on another machine, install the recorded Linux/Python/CUDA prerequisites
   and reproduce package versions from the local environment inventory. A copied venv
   requires compatible system libraries and interpreter paths. The backup is not a
   complete WSL operating-system image. A third archive, `wsl-python-runtime.tar`,
   preserves the external uv Python 3.13.15 interpreter used by the venv. Its manifest
   records the resolved installation prefix. Restore that prefix and recreate the
   original alias `cpython-3.13-linux-x86_64-gnu` before using the venv.
5. Preserve the Windows/WSL adapter versions independently. A pre-existing drift is
   documented in `corpus-v1.1/06-adapter-drift-k2.md`; saving this backup does not
   authorize reconciliation or deployment. Existing READY jobs, runtime checks and
   training authorization evidence must not be treated as fresh after restoration.
6. Use Python 3.11+ for the web application. Set `NAJDILAB_NO_DEMO=1` before the first
   normal launch against restored data. `.env.example` documents shell variables;
   the application does not automatically load `.env`. No API key is required by
   the local web application. Recreate external credentials from their authorized
   stores; no Hermes-wide credentials or messaging sessions are included here.
7. Review `integration-local-only/najdilab-outbound-hook.json` to reapply the passive
   hook in the new Hermes. Source files there are reference evidence only. Update
   absolute paths/autostart configuration if the installation location changes.
8. Run isolated tests before a normal launch. Some historical tests require local
   Gold/holdout/report data, so a code-only clone does not pass the entire suite.
   Consult the local verification report for exact results and existing failures.

Do not delete Hermes based only on a successful push. Both the GitHub verification
and the private archive/restore verification must succeed. This backup task neither
deletes Hermes nor stops/restarts services or authorizes training, migration, model
export, adapter deployment, or automatic execution of restored jobs.
