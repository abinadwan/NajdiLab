# Data retention and deletion

**Only chat conversations can be permanently deleted (Chat Experience V2, in development).** Everything else is logical. Excluding, ignoring, deleting and archiving remove a record from training selection and from new training files. The record itself stays in the local database, its audit history, earlier exports, the full archive of every new export, and backups. These rules are checked by `tests/test_qa08_retention.py`; chat archiving by `tests/test_chat_workspace.py`.

| Action | Training selection and new training files | Local database | Review audit history | Earlier exports | Full archive in new exports | Backups |
|---|---|---|---|---|---|---|
| Exclude a review | Removed | Kept (status `IGNORED`) | Event added | Unchanged | Included | Included |
| Restore a review | Not selected until a new human decision | Status `PENDING` | Event added | Unchanged | Included | Included |
| Delete a review | Removed | Kept (status `DELETED`, `deleted_at` set, original text kept) | Event added | Unchanged | **Included with its text** | Included |
| Ignore / delete a manual record | Removed | Kept (`ignored_at` / `deleted_at` set); deleting an exported record needs explicit confirmation | Version snapshots kept | Unchanged | Included | Included |
| Archive a chat conversation | Its collected pairs are excluded from future selection | Chat text kept | — | Unchanged | — | Included |
| **Permanently delete a chat conversation** (V2) | Removed | Chat rows and uncollected/unreviewed review copies deleted; reviewed copies blanked to `[deleted]` | Events kept, they hold no text | **Refused if any exist** | Not included afterwards | **Not changed** (counted and disclosed) |

Rules that make this so:

- A review that has audit events cannot be hard-deleted (`review_events` uses `ON DELETE RESTRICT`), and events cannot be changed or deleted.
- Frozen dataset versions and existing export folders are never rewritten.
- `full_archive.json` in each new export intentionally contains every review, including ignored and deleted ones, so a version can be audited later.
- Backups (`scripts/backup.py`) copy the whole database and `exports/`.

## Permanent chat deletion (Chat Experience V2)

The owner approved developing permanent deletion of chat conversations in this phase. It applies only to NajdiLab chat conversations; reviews, manual data and dataset versions keep the logical rules above.

**Declared scope — what is removed** (one SQLite transaction, all or nothing; code in `app/chat_deletion.py`):

- `chat_sessions`, `chat_session_bindings`, `chat_requests`, `chat_turns` rows of the conversation (all its text and receipts).
- Every review conversation collected from it (`najdilab-chat:<id>:*`). If none of its reviews has an audit event, the conversation, messages, reviews and tags are deleted. If any review has an event, the immutable `review_events` rows cannot be deleted, so the text is overwritten instead: message content, original and corrected responses, notes, titles, tags and metadata become `[deleted]` or empty, the review becomes `DELETED` and excluded.
- The deleting connection uses `secure_delete`, so freed database pages are zeroed, then the WAL is checkpointed and truncated. A test reads the raw database and WAL bytes afterwards and finds no copy of the deleted text. If another reader keeps the WAL busy, the result reports `wal_checkpoint: BUSY`.

**What remains, by design and disclosed in the dialog:**

- `review_events` rows: status, actor, time, reason and a SHA-256 of the old text. The hash cannot be reversed, but it can confirm a guessed exact text. A human-written `reason` could contain quoted text and cannot be changed (immutable); the preview reports how many events remain.
- A content-free tombstone in `chat_deletions` (session id, time, counts, policy). It is immutable.
- **Backups** made before deletion still contain the conversation. NajdiLab counts them and never opens or changes them; the owner deletes or rotates them.
- Copies outside NajdiLab's control (files moved to other devices, external training sets) cannot be deleted or verified.

**Refused (nothing is deleted):** a reply is running; the confirmation is not exactly `DELETE`; the revision is stale; or the conversation's id appears in NajdiLab's own `exports/`, `datasets/` or `reports/` folders (frozen files are never rewritten — archive instead).

**Safety:** tested only on synthetic data (`tests/test_chat_v2.py`: confirmation, stale revision, active turn, exported refusal, rollback after a mid-transaction failure, raw-bytes check, later exports, redaction with retained events, backups untouched). **No real conversation was deleted during development or update.**

**QA-08 impact:** the Phase B decision (logical deletion only) still holds for reviews, manual data and exports. Permanent deletion is a new, separately approved feature for chat conversations only; it does not erase frozen exports, earlier `full_archive.json` files or backups, so the guidance below about not promising complete erasure still applies to those copies.

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
