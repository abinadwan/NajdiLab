# Database and migration development

[Schema](database-schema.md) and [loader](../app/db.py) are the implementation references. State lives under data/najdilab.db. Connections enable FKs, WAL, synchronous NORMAL and 15-second busy timeout. Composite mutations use BEGIN IMMEDIATE and rollback on exception where implemented. Corrections overlay originals; frozen Gold stays immutable.

## Existing loader and limits

Startup apply_migrations creates schema_migrations, sorts migrations/*.sql lexically, executes absent filenames and records each afterward. It is a filename ledger, not a checksum/approval system. executescript plus subsequent ledger insertion are **not one guaranteed atomic migration+ledger transaction**. An interrupted/non-idempotent script can leave partial state. The future guarded loader is not implemented.

001–004 are existing startup migrations. `migrations/005_chat_workspace.sql` and `migrations/006_chat_session_binding.sql` are additive Chat migrations on the feature branch ([Chat rollback](chat-workspace.md#backup-and-rollback)). The separately numbered **005/006/007/008 under `plans/` remain blocked**, never onboarding steps. 007 risks a competing registry; 008 is lifecycle design. See [migration review](corpus-v1.1/07-migration-review-005-007.md) and [guard specification](corpus-v1.1/15-migration-loader-guard.md). Do not edit applied SQL or move blocked proposals into migrations.

## Separately authorized migration process

1. Review exact compatibility/transaction scope. Parameterize values; allowlist dynamic identifiers; never interpolate user SQL.
2. Create a consistent online snapshot plus external artifact hash/count/schema baseline; rehearse restore privately.
3. Implement guarded execution under its own approval, bound to source/script hashes; fail on wrong DB/schema or missing restore proof.
4. Test forward/repeated application, mid-script failure, writer contention, integrity/FKs, original/Gold preservation and rollback in isolation. IF NOT EXISTS alone is not idempotency.
5. Resolve K12 and relevant OA/PRQ gates before production. Never delete ledger rows to force reruns.

Integrity_check must be ok; foreign_key_check empty. Compare tables/indexes/triggers, counts and applied filenames; verify content hashes separately. Active SQLite file hashes can change with checkpoints. Never mix another instance's WAL/SHM.

A source revert cannot undo schema changes. Restore a verified snapshot into a separate installation and reconcile newer writes only with approval; preserve failed state privately. No down migration or restore-over-live is authorized here.
