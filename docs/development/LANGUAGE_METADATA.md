# Language metadata (V2.2.0)

| | |
|---|---|
| Branch | `update-project` (Draft PR #23). Development candidate, not a release. |
| Code | `app/language_taxonomy.py`, `migrations/010_language_metadata.sql`, `app/service.py` (manual data), `app/db.py` (`backup_before_migration`), `static/app.js` (forms, filters), `GET /api/v1/language-taxonomy` |
| Tests | `tests/test_language_taxonomy.py`, `tests/test_migration_010_language.py`, `tests/chat-browser.cjs` (Add Data) |

## 1. Why

The single "language layer" (Najdi / Riyadh, Saudi neutral, MSA, Technical Arabic, Formal Arabic) mixed four different things — a language, a variety, a register and a subject — and assumed every user works in Arabic. Records now carry four independent, optional dimensions:

| Dimension | Starting options | Notes |
|---|---|---|
| Language | Arabic, English, Multilingual | any other language as a custom value |
| Dialect / variety | Arabic: MSA, Najdi, Najdi / Riyadh, Hijazi, Saudi neutral, Gulf, Egyptian, Levantine, Iraqi, Maghrebi · English: American, British | offered only for the chosen language (all for Multilingual); never required |
| Style | Neutral, Conversational, Formal, Academic, Literary, Technical | |
| Domain | General, Technology, Education, Business, Healthcare, Legal | |

Every dimension also takes a short custom value ("Other…", up to 40 letters, digits, spaces and `. ' / ( ) & + -`; markup is refused). New records start with nothing selected — no Najdi or Saudi default. An Arabic dialect is refused for non-Arabic text, and a dialect needs a language.

Metadata describes the data. It is exported as fields of each record and counted in Dataset Health; it is **never** written into training prompts or messages. It is separate from the interface language and from any model response preference.

## 2. Existing records

Every record keeps its `language_layer` unchanged. Migration 010 fills the new fields only where the old value has a certain meaning:

| Legacy layer | language | dialect | style |
|---|---|---|---|
| najdi_riyadh | ar | najdi_riyadh | — |
| saudi_neutral | ar | saudi_neutral | — |
| msa | ar | msa | — |
| technical_arabic | ar | — (not stated) | technical |
| formal_arabic | ar | — (not stated) | formal |
| any other value | — | — | — |

Older clients that send only `language_layer` get the same mapping. The record detail shows the legacy layer next to the new fields. Reviewed chat records never had language metadata; Dataset Health counts them under "missing language metadata" and nothing is guessed for them.

## 3. Migration 010

- `preference_pairs`: three nullable columns added.
- `manual_sft_items`, `direct_language_texts`: rebuilt, because SQLite cannot relax `NOT NULL`/`CHECK` in place, so that `language_layer` becomes optional (the legacy `CHECK` on its values stays). The copy names every column, keeps every id, recreates the indexes and carries the `AUTOINCREMENT` counter over, so the id of a deleted record is never reused and record history stays unambiguous.
- Runs in one transaction with its ledger row, with foreign keys off for the rebuild (SQLite's documented procedure).

Verified on a disposable V2.1.0-shaped database with every legacy layer, an unknown layer and deleted high ids (all rows and values identical, counters kept, integrity and foreign-key checks clean, re-run is a no-op), and on a disposable copy of the installed test database (every table's row count unchanged; only the migration ledger gained a row).

## 4. Backup before any schema change, and recovery

From V2.2.0, when an existing database has pending migrations, NajdiLab first writes a consistent copy with SQLite's backup API to `data/backups/najdilab-before-<first migration>-<UTC time>.db` and checks its integrity; if the copy fails, nothing is migrated. New databases are not copied.

To undo an upgrade:

1. Stop NajdiLab (if NajdiLab Native runs, stop it from the model menu first).
2. Move `data/najdilab.db`, `data/najdilab.db-wal` and `data/najdilab.db-shm` aside.
3. Copy the backup to `data/najdilab.db`.
4. Check out the previous application version (for example `git checkout 2ddd413`) and start it.

Records created after the upgrade exist only in the moved-aside database. Dataset versions, exports, models and runtimes live outside the database and are not affected.

## 5. Not done

- The Review page does not yet let reviewers classify chat records with these dimensions.
- The NajdiLab Core public candidate keeps its core schema (migrations 001–004); there the service writes only the legacy fields.
