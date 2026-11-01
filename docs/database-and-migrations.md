# Database and migration safety

SQLite stores original conversations/messages, review overlays, manual versions, export metadata and Chat receipts. Dataset files and manifests live separately. Connections use FKs, WAL, synchronous NORMAL and a 15-second busy timeout; supported composite changes use BEGIN IMMEDIATE and rollback on failure. [Schema](database-schema.md) and `app/db.py` are implementation references.

## Startup loader caveat

The existing loader sorts every `migrations/*.sql`, executes filenames absent from `schema_migrations`, then records them. This is a filename ledger, not a hash/approval allowlist. `executescript` and ledger insertion are not one guaranteed atomic transaction: interruption after schema commit can leave the ledger behind. Startup still applies unapplied SQL; no guarded startup-only verifier has been implemented. Copying a proposal or rollback SQL into that directory can execute it on the next restart. A `.rollback.sql` can sort before its forward script.

Applied 001–004 and additive Chat `005_chat_workspace.sql` / `006_chat_session_binding.sql` remain intact. Chat migrations use replay-safe additions for the schema/ledger crash gap. These are distinct from separately numbered proposed dataset-registry005, review-events006, model-registry007 and draft lifecycle008 from earlier designs. Cleanup does not apply, edit or renumber migrations, move proposals into startup, or remove existing tables/ledger rows. Removal of obsolete source proposals does not alter their already-existing private evidence.

## Future schema change requirements

Any later schema change needs a separately reviewed exact script, compatibility scope, verified SQLite online snapshot, restore proof and isolated rehearsal. A future guard would need approved filenames/hashes, refusal of unknown or rollback files, an explicit apply path and recorded source/backup evidence; these properties are requirements, not current behavior.

Rehearsals must cover forward/repeat application, interruption, writer contention, integrity/FKs, existing counts/content and rollback. IF NOT EXISTS alone is not proof of idempotency. The prepared dataset registry used BEGIN IMMEDIATE for DDL+backfill and rejected duplicate IDs/paths, stale hashes/counts/state and missing manifests before writes. Its old nine-version observation is not a current production target. The unactivated review-event design has no complete production runner and covers conversation reviews, not all manual history; restrictive FKs can also prevent hard deletion. The removed model-registry proposal had no consumers and would have created a competing empty source of truth.

Integrity_check must return ok and foreign_key_check no rows. Compare schema, counts, filenames and content hashes independently; a live SQLite file hash can change after checkpoint. Never mix WAL/SHM from another instance or delete ledger entries to force reruns. Test restoration into a new private location, never over live data. This source-only cleanup requires no data rollback; a source revert must still be reviewed before launch because earlier source may reintroduce removed interfaces or unsafe Hermes ingress. [Recovery](backup-and-restore.md).
