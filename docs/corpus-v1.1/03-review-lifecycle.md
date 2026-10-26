# 03 — Manual-Item Review Lifecycle (closes the G3 gap)

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23). No schema or code change has been made; implementation needs separate approval (Phase 2, OA-08).**

## 1. Problem (verified)

- Manual items (`manual_sft_items`, `direct_language_texts`, `preference_pairs`) have **no review status**. `_insert_training_item` accepts `training_eligible` from the request (`app/service.py:1449`: `eligible = 0 if evaluation_only or exclude else _bool(data.get("training_eligible"))`), and `_validate_manual_payload` lets updates set it (`service.py:1190-1257`).
- `manual_data_versions.changed_by` only allows `human` or `system` (`003_manual_data_manager.sql`). There is no actor identity.
- Conversation reviews do have a lifecycle (`app/review_lifecycle.py:15-23`), but it doesn't apply to manual items. Its immutable event table (`plans/phase2/006_review_events.sql`) isn't applied, and it references `reviews(id)` only.

So today a generated record could be inserted as trainable without any human seeing it.

## 2. Design goals

1. **No generated record becomes training-eligible without explicit human approval** of its exact current content.
2. Existing data is preserved: legacy rows keep their current values and are reported, not rewritten.
3. The design mirrors the existing conversation-review semantics so reviewers see one mental model.
4. It's enforced in depth: service layer, database trigger, export gate, and training quality gate.

## 3. States

| State | Meaning | Trainable? |
|---|---|---|
| `DRAFT` | Being authored or just generated, not yet submitted | No |
| `PENDING_REVIEW` | Submitted. Generated items (Silver/Bronze) enter here directly | No |
| `CHANGES_REQUESTED` | Reviewer returned it with reasons and defect tags | No |
| `APPROVED` | A human reviewer approved **this version** (bound to `version_number` + content SHA-256) | Only if all eligibility conditions in §5 hold |
| `REJECTED` | Final rejection with defect tags. Kept for audit and for negative examples | No |
| `IGNORED` / `DELETED` | Existing soft states (`ignored_at`, `deleted_at` columns from migration 004) | No |
| `LEGACY` | Rows that existed before migration 008. Values untouched | Unchanged from today, but flagged in the UI and the export report (§7) |

## 4. Transitions

| From → To | Actor role | Required inputs | Effect |
|---|---|---|---|
| (create) → `DRAFT` | author | content, taxonomy | Version 1 snapshot |
| (generate) → `PENDING_REVIEW` | system, on behalf of the data owner who started the batch | `generation_batch_id` | Version 1 snapshot. Eligibility is forced to 0 |
| `DRAFT` → `PENDING_REVIEW` | author | — | Submit event |
| `PENDING_REVIEW` → `APPROVED` | reviewer (≠ author for Silver/Bronze; ≠ author for Gold if DF-01 requires peer review) | version_number, content_sha256 echo (optimistic check), rubric scores | Approval event bound to the version hash |
| `PENDING_REVIEW` → `APPROVED` with correction | reviewer | corrected content, correction type (`DIALECT`, `CONTENT`, `FULL`, mirroring review statuses), defect tags | Creates version N+1 authored by the reviewer, then an approval of N+1. **A second reviewer must confirm FULL corrections** (proposal; DF-02) |
| `PENDING_REVIEW` → `CHANGES_REQUESTED` | reviewer | reason, defect tags | — |
| `CHANGES_REQUESTED` → `PENDING_REVIEW` | author | new version | — |
| `PENDING_REVIEW` → `REJECTED` | reviewer | reason, ≥1 defect tag | Final |
| `APPROVED` → `PENDING_REVIEW` | system | — | **Automatic on any content edit** (the approval no longer matches the hash) |
| any active → `IGNORED`/`DELETED` | reviewer or data owner | reason | Existing soft semantics |
| `IGNORED`/`DELETED` → `PENDING_REVIEW` | reviewer or data owner | reason | Restore, mirroring `review_lifecycle.py` |
| `REJECTED` → (none) | — | — | Terminal. Re-use means clone → new item (`clone_manual_data`, `service.py:1314`) |
| `LEGACY` → `PENDING_REVIEW` | data owner | reason | Optional opt-in to bring a legacy row under the lifecycle |

Machine actors (`ai_suggestion`) may **suggest** a decision. A suggestion is stored as advisory metadata and never performs a transition to `APPROVED`.

## 5. Eligibility invariant

`training_eligible = 1` is allowed for a non-legacy manual item **only if all** of these hold:

1. state = `APPROVED`;
2. a matching approval event exists where `version_number` = the current version, `content_sha256` = SHA-256 of the current canonical content, actor role = reviewer, actor kind = human;
3. for `origin IN ('synthetic_variant','llm_draft')`: approver ≠ author or batch starter;
4. `evaluation_only = 0`, `exclude_from_training = 0`, `archived = 0`, `ignored_at IS NULL`, `deleted_at IS NULL`;
5. `contains_sensitive_data = 0` and `contains_personal_data = 0`;
6. no open G2-D blocking finding for this version.

Any write that would violate this is refused.

## 6. Enforcement layers

| Layer | Mechanism | Where |
|---|---|---|
| L1 Service | `_insert_training_item` and `update_manual_data` drop client-supplied `training_eligible` for non-legacy items. Eligibility is computed only by the approval transition | `app/service.py` (Phase 2 change) |
| L2 Database | Migration 008 trigger: `BEFORE INSERT/UPDATE OF training_eligible` → `RAISE(ABORT)` unless invariant items 1–3 hold (checks `manual_item_events`). This is the backstop against any future code path | `008` (proposal, `07-migration-review-005-007.md`) |
| L3 Export gate | `review_integrity` gains codes `MANUAL_ITEM_UNAPPROVED`, `APPROVAL_HASH_MISMATCH`, `SELF_APPROVAL`. Blocks before any file is written (existing HTTP 409 pattern) | `app/review_integrity.py` (Phase 2 change) |
| L4 Training gate | The training quality gate rejects any dataset whose manifest counts generated items without approval evidence | `app/training_control.py` (Phase 2 change) |

## 7. Legacy and existing data

Current DB counts (read-only, 2026-10-23): 7 `manual_sft_items`, 13 `direct_language_texts`, 11 `preference_pairs`; 30 `system` and 12 `human` version snapshots.

- Migration 008 sets `review_state='LEGACY'` for existing rows **without touching any other column**. Their `training_eligible` values are preserved.
- Frozen datasets that already contain these rows are unaffected: they're immutable and outside the lifecycle.
- The UI shows a legacy banner and count. The data owner may opt rows into review individually.

## 8. Events

The proposed `manual_item_events` table (append-only, UPDATE/DELETE triggers abort, mirroring 006) has these columns:
`id, item_type, item_id, sequence, from_state, to_state, version_number, content_sha256, actor_profile_id, actor_kind (human|system|ai_suggestion), actor_role, reason, correction_type, defect_tags_json, rubric_json, created_at`, with `UNIQUE(item_type,item_id,sequence)`.

## 9. UI

- `/review/candidates`: a queue filtered by batch, tier, task type, domain and G2 findings. Blind to the G2 score by default (`04-quality-gates.md`).
- Item view: content, version diff, G2 findings, rubric (reusing the dimensions in `phase38_dataset.py:153` and `phase3_review.py:18`), defect tags (extended `review_tags` vocabulary), decision buttons.
- Every decision shows the actor and requires the item's current version. Stale approvals are refused with an explanation.

## 10. Acceptance criteria (for implementation in Phase 2)

1. Creating or updating a generated item with `training_eligible=1` is refused by L1 **and** by L2 (tested by direct SQL in a fixture DB).
2. Approval bound to version N; editing to N+1 resets to `PENDING_REVIEW` and clears eligibility.
3. Self-approval of Silver/Bronze is refused (HTTP 403).
4. `ai_suggestion` actors can't transition to `APPROVED`.
5. The export gate returns 409 with `MANUAL_ITEM_UNAPPROVED` when such an item is selected.
6. Every row in the migrated fixture keeps its pre-migration values (column-by-column comparison); legacy count = pre-migration count.
7. The event table refuses UPDATE and DELETE.
8. Inserting a new manual item with `review_state='LEGACY'` (explicitly or by default) is refused, and no row can return to `LEGACY`.
