# Phase 2–4 Current-State Audit

Date: 2026-10-09. Scope: read-only schema, service, export, dataset-platform, UI-route, and test inspection. No production rows or protected artifacts were modified.

## DATA-01 — Relationships and sample lifecycle

### Current authoritative relationships

1. `conversations.id` → `messages.conversation_id` with cascade delete.
2. One assistant `messages.id` → at most one `reviews.message_id` (`UNIQUE`).
3. `review_tags.review_id` → `reviews.id` with cascade delete.
4. Manual SFT, direct-language, and preference samples are separate first-class tables rather than review rows.
5. `manual_data_versions` records versions for manual records, and `manual_data_export_history` links manual records to legacy `dataset_versions` releases.
6. Export reconstruction replaces only the selected assistant target with `corrected_response` when present; `original_response` remains separate.

### Current lifecycle

- Review statuses: `PENDING`, `FULL_CORRECTION`, `DIALECT_CORRECTION`, `CONTENT_CORRECTION`, `APPROVED`, `IGNORED`, `DELETED`.
- `IGNORED` and `DELETED` are soft states and cannot be training-eligible by database checks.
- Training selection is allowlist-based: approved/corrected, not excluded, not evaluation-only, not archived/deleted/ignored.
- Existing API/UI actions cover approve, correct, ignore, and soft delete. No explicit restore/unignore transition was found.
- The current review row is updated in place. There is no append-only `review_events`/review-history table, so DATA-05 remains a real gap.

### Production consistency evidence

- Reviews: 42 approved, 97 content corrections, 63 dialect corrections, 138 full corrections, 141 deleted, 6 pending.
- Review tags: 862.
- Orphan reviews: 0.
- Corrected decisions without corrected text: 0.
- Pending reviews marked trainable: 0.
- Ignored/deleted reviews marked trainable: 0.

### Phase 2 gaps

- Define and enforce an explicit transition matrix, especially restore behavior.
- Add immutable review-event history with actor, timestamp, prior/new state, correction type, tags, and reason.
- Add stale/inconsistent review detection based on source/correction fingerprints.
- Add an explicit required-review export gate; current eligibility filters exclude unsafe rows but do not express a release-level unresolved-review policy.
- Extend safe bulk operations to review rows with atomic preconditions and audit events.

## QUAL-01 — Cleaning, validation, and duplicate logic

### Reusable implementation

- Deterministic normalization and exact-target fingerprints.
- Priority-based exact-duplicate removal during export with a detailed resolution report.
- Near-duplicate reporting based on normalized context+target similarity; near duplicates remain in training.
- Deterministic conversation-isolated holdout and exact train/eval target-overlap validation.
- JSONL structural validation, target-index and response-only loss-mask validation.
- Manifest counts and SHA-256 generation.
- Dataset health checks for exact duplicates, invalid targets/masks, stale diagnostics, and leakage.
- Phase 3.8 contains a specialized contamination/near-duplicate review queue, but it is not yet a general platform-wide quality finding registry.

### Phase 3 gaps

- No durable, first-class quality-finding entity with evidence, status, actor, and resolution.
- No general conflicting-correction/contradictory-target detector across all sources.
- Malformed and missing records are checked in several pipelines but not surfaced through one unified queue.
- Synthetic-looking or unnatural Arabic checks are diagnostic/phrase-oriented, not a calibrated explainable detector.
- Quality actions are split across dataset-specific flows; retain/correct/exclude/intentional is not one audited workflow.

## VER-01 — Build and release process

### Reusable implementation

- `create_export` stages output in a temporary directory, validates it, writes JSONL and manifest, then registers the version.
- Exact duplicate removal and deterministic holdout happen before release.
- Manifest stores counts, hashes, filter evidence, exclusions, and dedup/holdout facts.
- Dataset platform supports creating a derived Draft from a Frozen source, overlap-analysis dry-runs, stale-plan fingerprints, diagnostics, and freeze validation.
- Frozen versions reject the known mutation operations, and tests verify older exports remain byte-identical after later review changes.

### Phase 4 platform gaps

- Lifecycle currently collapses undeclared legacy state to Frozen in `dataset_platform._state`; canonical registry correctly uses `Unknown`. These semantics must be unified before canonical API cutover.
- There is no explicit `Validated` transition persisted in the current dataset manifests/API.
- Filesystem immutability is enforced by application behavior, not an authoritative release record plus filesystem protection.
- The legacy export flow and newer derived-dataset flow are separate paths and need one release service.
- Reproducibility is tested for splits and selected operations, but there is no end-to-end two-build byte-identical acceptance test for the complete release.
- Readiness blockers are available in health details but are not yet one authoritative release gate tied to the canonical registry.

## Dependency conclusion

The next safe implementation slice is DATA-02/DATA-05 together: introduce an additive review-event model and explicit transition policy on isolated fixtures first. DATA-08, the general quality queue, and the unified release pipeline should depend on that audit foundation. Production SQLite changes for either the registry or review-event schema still require their own explicit approvals.

