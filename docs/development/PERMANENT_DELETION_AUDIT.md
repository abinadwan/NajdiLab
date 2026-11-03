# Permanent chat deletion — audit

| | |
|---|---|
| Date | 2026-11-03 |
| Code | `app/chat_deletion.py`, `ChatWorkspace.delete_preview/delete` in `app/chat_workspace.py`, delete dialog in `static/chat.js` |
| Data used | Synthetic conversations in temporary databases only. **No real conversation, dataset, export or backup was deleted or opened.** |
| Policy | [data retention](../data-retention.md#permanent-chat-deletion-chat-experience-v2) |

**What the feature guarantees:** after a successful deletion, NajdiLab's own database file and journal no longer contain the conversation's text, title or replies, and later exports cannot include it. **What it does not guarantee:** removal from backups, from files already exported, from copies on other devices or programs, or from the free-text reasons on immutable audit events. It is not universal physical erasure, and the UI does not say so.

## Store-by-store result

| Store | After deletion | How verified |
|---|---|---|
| `chat_sessions` (incl. titles), `chat_session_bindings`, `chat_requests`, `chat_turns` | Rows deleted | Row counts; raw-byte scan |
| Collected review copies without audit events (`conversations`, `messages`, `reviews`, `review_tags`) | Deleted (cascade) | Row counts; raw-byte scan |
| Collected review copies **with** audit events | Text, corrections, notes, titles, tags, metadata and source ids overwritten (`[deleted]` / empty); review `DELETED`, excluded | Field check; raw-byte scan |
| `review_events` | **Kept** (immutable by trigger): status, actor, time, `source_sha256`/`correction_sha256`, **free-text `reason`** | Counted in preview/result (`review_event_reasons_retained`) |
| `chat_deletions` tombstone | Session id, time, counts, policy — no text | Immutable trigger tested |
| Search indexes / caches | None exist (no FTS tables; no in-process content cache). Search runs `LIKE` over live rows only. | Schema and source review |
| Freed database pages and slack | Zeroed: the deleting connection uses `PRAGMA secure_delete=ON` | Raw-byte scan after renames, updates and page sharing with 25 neighbours; control run **without** `secure_delete` leaves traces (TITLE 1, BODY 3), with it 0 |
| WAL (`najdilab.db-wal`) | Checkpointed and truncated; if another reader blocks it, the result is `BUSY`, the UI says so, and the next start retries | `test_concurrent_reader…` (BUSY reported; clean after restart) |
| Server request log | Paths and session ids only; search query strings are now omitted (F7) | `test_request_log_never_contains_query_text` |
| Error messages | Fixed strings; no row values | Source review |
| In-memory consent state | Dropped for the session | Source review |
| Frozen datasets, existing exports, earlier `full_archive.json` | **Not changed.** Deletion is **refused** when the conversation id appears in NajdiLab's `exports/`, `datasets/` or `reports/` | `test_delete_is_refused_while_exported…` |
| Exports created **after** deletion | Do not contain the conversation | `test_delete_removes_chat…` (export check) |
| Backups (`backups/najdilab-backup-*.zip`) | **Not opened or changed**; counted in the preview and dialog | `test_backups_are_counted_never_changed` |
| Copies outside NajdiLab (other devices, external training) | Out of reach; stated in the dialog | — |

## Fields that could still identify content

| Field | Risk | Handling |
|---|---|---|
| `review_events.reason` | A reviewer may have typed text that quotes the chat. Immutable. | Preview counts these and the dialog warns the user to check them. **Residual.** |
| `review_events.source_sha256`, `correction_sha256` | SHA-256 of the old reply; cannot be reversed, but can confirm a guessed exact text. | Disclosed. **Residual.** |
| `chat_deletions.session_id` | A random UUID; no content. | — |
| Counts (turns, requests) | Size of the conversation only. | Accepted. |
| `conversations.external_conversation_id` of redacted copies | Replaced with `deleted:<random>`; the session id no longer links them. | Field check. |

## Test matrix (all synthetic, `tests/test_chat_v2.py` unless noted)

| Case | Result |
|---|---|
| Exact `DELETE` confirmation; `delete`, empty, `yes`, `null` refused | PASS |
| Stale revision refused, nothing changed | PASS |
| Active generation → `CHAT_BUSY`, nothing changed | PASS |
| Mid-transaction failure (trigger aborts) → full rollback, no tombstone | PASS |
| Concurrent reader holding a snapshot → rows gone, `wal_checkpoint: BUSY` reported, clean after restart | PASS |
| WAL checkpoint failure other than BUSY | Reported as `FAILED` by code path; **NOT TESTED** (cannot be provoked portably) |
| Previous backup present → counted, bytes unchanged | PASS |
| Exported conversation → `DELETE_BLOCKED_EXPORTED`, nothing changed | PASS |
| Repeated deletion → `CHAT_NOT_FOUND`, one tombstone | PASS |
| Restart after deletion → absent from list and lookups; startup checkpoint `TRUNCATED` | PASS |
| Future dataset export → no deleted text in any file | PASS |
| Raw database + WAL bytes contain no deleted text, including titles renamed several times | PASS |
| Reviewed copy with events → blanked, events kept, hashes only | PASS |
| Reviewer reasons on events → counted and disclosed | PASS |
| UI: typed confirmation is case-sensitive, preview lists what is deleted/kept, deletion removes the chat (`chat-browser.cjs`) | PASS |
| Windows (NTFS, antivirus file locks) | **NOT TESTED** |

## Dialog wording (English; Arabic in the catalog)

Deleted: "Messages to delete", "Review copies to delete", "Reviewed copies to blank out". Kept: "Audit events kept (no text, only status, time and a fingerprint)", "Reviewer reasons that cannot be removed" (when present). Not reachable: "Backups made earlier may still contain this conversation until you delete those backup files yourself." and "Copies already moved to other devices or programs cannot be deleted by NajdiLab." Refusals explain why and suggest archiving. After deletion, if the journal could not be cleaned, the notice says so.

## Remaining limits

- Backups and earlier exports must be handled by the owner; NajdiLab never rewrites them.
- Immutable audit reasons and hashes remain.
- Disk-level remnants (SSD wear levelling, filesystem journals, OS caches) are outside SQLite's control.
- Windows behavior not tested.
