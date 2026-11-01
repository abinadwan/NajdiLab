# Database and migration safety

SQLite stores original conversations/messages, review overlays, manual versions, export metadata and Chat receipts. Dataset files and manifests live separately. Connections use FKs, WAL, synchronous NORMAL and a 15-second busy timeout; supported composite changes use BEGIN IMMEDIATE and rollback on failure. [Schema](database-schema.md) and `app/db.py` are implementation references.

## Startup loader

`apply_migrations` in `app/db.py` runs at startup. It considers only files named `NNN_lowercase_words.sql` and skips any name containing `rollback`, `revert`, `undo`, `down`, `helper`, `seed` or `fixture`, so `007_rollback.sql` or `rollback_001.sql` never runs (DB-01).

Each pending migration and its `schema_migrations` row commit in one transaction (DB-02). Two forms are supported: a script with no transaction statements (wrapped in `BEGIN IMMEDIATE … COMMIT`, with leading `PRAGMA` lines kept outside), or a script with exactly one `BEGIN` and one `COMMIT` and only `PRAGMA` lines or comments outside them (the ledger row goes in just before its `COMMIT`). Trigger bodies (`BEGIN … END;`) are not treated as transactions. Any other form — two transaction pairs, statements after `COMMIT`, `ROLLBACK`, `SAVEPOINT` — is refused before any pending migration runs. A failing statement rolls back that migration's schema changes and its ledger row together, and a fixed file can then be retried.

Remaining limits: this is still a name ledger with a keyword blocklist, not a hash or approval allowlist, so a forward-named file that should not run will run. Shipped migration hashes are pinned in `docs/cleanup-inventory.json` and enforced by tests, not at startup. Never copy proposal SQL into `migrations/`.

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
