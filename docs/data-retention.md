# Data retention and deletion

**Nothing in NajdiLab physically erases data.** Excluding, ignoring, deleting and archiving remove a record from training selection and from new training files. The record itself stays in the local database, its audit history, earlier exports, the full archive of every new export, and backups. These rules are checked by `tests/test_qa08_retention.py`; chat archiving by `tests/test_chat_workspace.py`.

| Action | Training selection and new training files | Local database | Review audit history | Earlier exports | Full archive in new exports | Backups |
|---|---|---|---|---|---|---|
| Exclude a review | Removed | Kept (status `IGNORED`) | Event added | Unchanged | Included | Included |
| Restore a review | Not selected until a new human decision | Status `PENDING` | Event added | Unchanged | Included | Included |
| Delete a review | Removed | Kept (status `DELETED`, `deleted_at` set, original text kept) | Event added | Unchanged | **Included with its text** | Included |
| Ignore / delete a manual record | Removed | Kept (`ignored_at` / `deleted_at` set); deleting an exported record needs explicit confirmation | Version snapshots kept | Unchanged | Included | Included |
| Archive a chat conversation | Its collected pairs are excluded from future selection | Chat text kept | — | Unchanged | — | Included |

Rules that make this so:

- A review that has audit events cannot be hard-deleted (`review_events` uses `ON DELETE RESTRICT`), and events cannot be changed or deleted.
- Frozen dataset versions and existing export folders are never rewritten.
- `full_archive.json` in each new export intentionally contains every review, including ignored and deleted ones, so a version can be audited later.
- Backups (`scripts/backup.py`) copy the whole database and `exports/`.

## Approved Phase B retention policy (owner decision — 2026-11-02)

The owner approved **logical deletion, exclusion and archiving only for Phase B**, preserving the current audit trail and historical exports. Physical erasure is **explicitly deferred as a separate future feature**, not promised by today's Delete controls. This decision resolves the *scope/policy choice* for QA-08; it does **not** turn skipped or unexecuted acceptance checks into a PASS.

Operational safeguards:
- UI/documentation must not describe current deletion as irreversible or permanent.
- Excluded/deleted content must not enter new training-selection files, but **the local database, audit history, full archives of new exports, past exports and backups can still contain its text**.
- Treat full archives, backups, and exports as potentially sensitive; do not distribute them on the assumption that deleted records were purged.
- Requests for actual erasure need a separately designed, authorized workflow covering database content, immutable audit evidence, frozen versions, generated full archives, backups, and downstream copies, with a verifiable outcome. No destructive migration or purge is approved in Phase B.

## What this means for a deletion request

If someone asks for their content to be removed, deleting it in NajdiLab is **not enough**: the text stays in the database, earlier exports, later full archives and backups. Physical erasure across all of these is not implemented. The owner has deferred implementing erasure to a separate future feature because it must address immutable review events, frozen exports, backups and copies already handed to external training. Until there is an approved and tested removal process, do not promise complete erasure; handle requests with an explicit record of what remains and where.

Related: [backup and restore](backup-and-restore.md), [review and quality](review-and-quality.md), [dataset export](dataset-export.md).
