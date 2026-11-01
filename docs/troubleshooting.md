# Troubleshooting

Use the intended checkout's supported Python and a free loopback port. Inspect launcher errors; do not globally kill Python or unrelated local engine processes. A different port alone does not isolate database paths. Empty dataset pages are expected without authorized local records; use synthetic disposable data for tests, never invented historical artifacts.

For rejected browser writes, reload the intended origin/session, check JSON/framing/CSRF and ingest credentials. CSRF is not reviewer authentication. Hermes409 is deliberate; do not route unsafe events around it. [Security](../SECURITY.md), [integrations](integrations.md).

Chat blocks unknown token/context/model identity behavior instead of truncating. Inspect its machine code and [engine contract](chat-workspace.md). Hardware suggestions are unverified; real installed-model acceptance is separate. Missing LM Studio model must be resolved in that application by its operator. No model/training setup screen is supplied.

Export409 requires resolving confirmed review/privacy/mask/conflict/leakage blockers. Do not weaken gates or replace frozen files. Build a new privacy-attested version for [Unsloth export](dataset-export.md). Warnings do not certify correctness or consent.

For database failure, stop additional writes, preserve evidence and rehearse [recovery](backup-and-restore.md) privately. Check integrity/FKs on an isolated copy. Never delete WAL/SHM, ledger rows or tables to clear an error; startup migration auto-application remains [documented debt](database-and-migrations.md).

Missing private fixtures are explicit skips, not passes. Run only relevant tests in disposable storage and report actual failures/limitations. Removed training/model-evaluation/platform-status routes return missing-route responses; replace dataset callers with the [current API](api-reference.md).
