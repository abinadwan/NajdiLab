# DATA-07 / DATA-08 — Review Integrity and Export Readiness

Date: 2026-10-09 (Asia/Riyadh)

## Result

Both acceptance criteria are verified. The implementation is read-only with respect to review persistence and runs before any new export directory or file is created. It does not modify existing frozen datasets.

## Detection contract

Confirmed `ERROR` findings block new builds and exports and contain a stable code, sample ID, Arabic reason, severity, confirmation flag, blocking flag, and safe diagnostic details. Rules cover:

- assistant messages missing a review;
- reviews missing their source, original response, or reviewer provenance;
- pending decisions;
- semantic source drift (stale review);
- correction/status, training eligibility, and train/evaluation conflicts;
- missing or inconsistent immutable events when the optional event table exists;
- missing database/schema/export sources and zero exportable records.

Whitespace/case-only source drift and absence of the not-yet-approved immutable event table are ambiguous `WARNING` findings. They remain visible but do not become confirmed blockers automatically.

Original messages, current decisions, reviewer provenance, and historical event rows are only read. No automatic winner, correction, deletion, or historical rewrite occurs.

## Export gate

- `create_export` evaluates readiness before creating the target directory.
- `GET /api/v1/review-integrity` and `GET /api/v1/exports/readiness` return the structured result.
- A blocked `POST /api/v1/exports` returns HTTP 409, code `EXPORT_NOT_READY`, and the full readiness payload.
- The dashboard shows up to three actionable sample/reason pairs and stops the client request when blocked; the server remains the authoritative gate.
- Existing frozen releases are neither re-evaluated nor rewritten.

## Isolated verification

Fixtures cover approved, pending, conflicting flags, semantic stale state, ambiguous format drift, missing review, missing database/schema, event sequence/status/source conflicts, transaction rollback, pre-write refusal, frozen-release hash preservation, UI wiring, and HTTP 409 details.

- Focused suite: `13 passed in 0.87s`.
- Complete suite: `207 passed, 8 subtests passed in 9.89s`.

## Production read-only observation

- SQLite integrity: `ok`; journal mode: WAL.
- Applied migrations: 001–004 only.
- `review_events`: absent; no production migration was performed.
- Non-demo readiness: `READY`, 0 confirmed blockers, 1 ambiguous warning (`REVIEW_HISTORY_UNAVAILABLE`).
- Exportable non-demo count: 151, reported without changing any row.

## Remaining limitations and blockers

- Full historical-sequence proof is unavailable until DATA-02/DATA-05 and the proposed review-event migration receive explicit production approval.
- The currently running NajdiLab process was not restarted; the new endpoints/code become active on the next separately authorized normal deployment/restart.
- REG-09 remains prohibited and blocked pending explicit approval.

## Recommended next work

Prepare DATA-03, DATA-04, and DATA-06 against isolated fixtures, then implement DATA-09 atomic bulk review behavior. Keep review-event persistence and REG-09 outside production until separately approved.
