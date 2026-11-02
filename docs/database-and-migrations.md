# Database and migration safety

SQLite stores original conversations/messages, review overlays, manual versions, export metadata and Chat receipts. Dataset files and manifests live separately. Connections use FKs, WAL, synchronous NORMAL and a 15-second busy timeout; supported composite changes use BEGIN IMMEDIATE and rollback on failure. [Schema](database-schema.md) and `app/db.py` are implementation references.

## Startup loader

`apply_migrations` in `app/db.py` runs at startup. Only migrations listed in `migrations/registry.json` run (DB-01). Each entry holds a file name and the SHA-256 of its content, with CRLF normalized to LF so a Windows checkout matches. Before the database is opened, every registered file must exist and match its hash; otherwise startup stops with `MigrationRegistryError`. Any other `.sql` file in the folder — a validly numbered one, a rollback, a helper or a proposal — is never read or executed. Adding a migration therefore needs a reviewed change to both the SQL file and the registry. Ledger rows from earlier history that are not in the registry are kept unchanged.

Each pending migration and its `schema_migrations` row commit in one transaction (DB-02). The script is split into statements with `sqlite3.complete_statement`, the same boundary check the SQLite shell uses, so `;` inside strings, comments and trigger bodies never ends a statement. Accepted form: optional `PRAGMA foreign_keys` statements, then schema statements — optionally inside exactly one leading `BEGIN` and one final `COMMIT` — then optional `PRAGMA foreign_keys` statements. Anything else is refused before any pending migration runs: a `COMMIT`, `END`, `ROLLBACK`, `SAVEPOINT` or `RELEASE` anywhere else (including inline, such as `CREATE TABLE x(id INTEGER); COMMIT;`), `ATTACH`, `DETACH`, `VACUUM`, other `PRAGMA`s, or an incomplete statement. The loader then opens `BEGIN IMMEDIATE` itself, executes each statement, inserts the ledger row as a bound parameter and commits. A failing statement rolls back that migration's schema changes, data and ledger row together; earlier migrations in the same run stay committed with their own ledger rows, and a fixed file can be retried. `foreign_keys` is reset to ON after every migration.

Remaining limits: the registry proves a file is the reviewed one, not that its SQL is correct; review is still required. Python's `executescript` is no longer used for migrations.

Applied 001–004 and additive Chat `005_chat_workspace.sql` / `006_chat_session_binding.sql` remain byte-identical. `007_review_events.sql` creates the immutable `review_events` table and a one-row immutable `review_event_baseline` table. These are distinct from the earlier proposed dataset-registry005, model-registry007 and draft lifecycle008 designs.

## Review event history (007)

Every review status change made through the application writes an immutable event, including re-saving a decision with edited text or restriction flags. `review_events.review_id` uses `ON DELETE RESTRICT`, so a review that has events cannot be hard-deleted; use the soft delete status.

Reviews that existed before 007 have no recoverable history, and none is fabricated. When 007 runs it records the highest existing `reviews.id` (the id column is `AUTOINCREMENT`, so ids are never reused). Export readiness then separates three cases:

- `review.id` at or below the baseline with no events: `REVIEW_HISTORY_UNVERIFIABLE`, a warning. The current decision is still checked by every other rule, so a legacy `PENDING` review still blocks.
- `review.id` above the baseline with no events: `REVIEW_EVENT_MISSING`, a blocking error.
- Any review with events whose sequence, latest status or source fingerprint disagrees: blocking `REVIEW_EVENT_*` conflicts. This applies to legacy reviews once they gain events.

If the baseline row is missing, every review requires events (fails closed). Only conversation reviews are covered; manual data keeps its separate `manual_data_versions` history. The Core profile under `public_source/` deliberately supports migrations 001–004 only and does not ship 007.

## Future schema change requirements

Any later schema change needs a separately reviewed exact script, compatibility scope, verified SQLite online snapshot, restore proof and isolated rehearsal. Rehearsals must cover forward/repeat application, interruption, writer contention, integrity/FKs, existing counts/content and rollback. IF NOT EXISTS alone is not proof of idempotency.

Integrity_check must return ok and foreign_key_check no rows. Compare schema, counts, filenames and content hashes independently; a live SQLite file hash can change after checkpoint. Never mix WAL/SHM from another instance or delete ledger entries to force reruns. Test restoration into a new private location, never over live data. Do not drop `review_events`, `review_event_baseline` or ledger rows to undo 007: that permanently destroys audit history. Once 007 has run, a source revert is not a clean rollback (earlier code blocks legacy reviews and rejects re-saved decisions); recover by restoring the verified pre-upgrade backup into a new location. [Recovery](backup-and-restore.md).
