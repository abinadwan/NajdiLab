# Database schema

The database is `data/najdilab.db`. Connections enable `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` and `busy_timeout=15000`.

| Table | Purpose | Key constraints |
|---|---|---|
| `schema_migrations` | Applied migration ledger | Unique version |
| `conversations` | Model-independent conversation header | Unique `external_conversation_id`; explicit `demo` |
| `messages` | Individual turns | Allowed roles; unique conversation ordering; foreign keys |
| `reviews` | Separate decision/correction overlay | One per assistant message; source preserved by service rules |
| `review_tags` | Multiple error tags | Controlled vocabulary and composite key |
| `review_events` | Immutable review status history (migration 007) | Unique `(review_id, sequence)`; update/delete triggers abort; `ON DELETE RESTRICT` to `reviews` |
| `review_event_baseline` | Highest review id that predates event history | Single immutable row |
| `manual_sft_items` | Manually authored dialogues | Provenance and privacy/training gates |
| `direct_language_texts` | Text without user/assistant roles | Language layer and source type |
| `preference_pairs` | Rejected/preferred responses | JSON context and preserved provenance |
| `manual_data_versions` | Snapshot for each manual edit | Unique `(item_type, item_id, version_number)`; restricted `changed_by` |
| `manual_data_export_history` | Manual-item membership in Gold versions | Unique item/version relationship |
| `comparison_records` | Future model comparisons | Candidate group and judge result |
| `dataset_versions` | Export registry | Unique version name and stored manifest |
| `settings` | Local settings foundation | JSON key/value |

Proposed registry tables under `plans/` are not evidence of production activation. Review event rules and legacy handling are in [the migration review](database-and-migrations.md).

## Original content

`messages.content` holds the source text. Review creation copies the response into `reviews.original_response`. Review edits change only `corrected_response`; `APPROVED` requires a null correction, while correction states require the complete replacement response.

## Training and privacy

Independent flags include `training_eligible`, `archived`, `exclude_from_training`, `evaluation_only`, `contains_sensitive_data`, `contains_personal_data` and `needs_fact_check`. Training requires explicit eligibility. Archival, exclusion and evaluation flags block training export without deleting the row. Manual items also carry `version_number`, `parent_item_id` and `updated_at`.

## Manual versions

Each SFT, direct-language or preference edit increments `version_number` and stores a complete snapshot, changed fields, note and actor in `manual_data_versions`. Cloning makes a separate item linked through `parent_item_id`.

## Context reconstruction

Export reads the conversation in order through the reviewed response's `turn_index`. Only the export copy substitutes the final assistant content with its correction, if present. The original database text stays unchanged.
