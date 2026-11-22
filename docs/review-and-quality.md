# Review, quality and provenance

Completed consented Chat pairs enter PENDING with `training_eligible=0`. Generic authenticated ingestion and manual authoring remain available. Originals stay separate from corrections; source Unicode/whitespace and API enum values are preserved. `training_eligible` is a retained dataset field, not an execution control.

Approve, correct, exclude and restore are explicit service/API actions. Corrections retain metadata, reasons and tags; restrictive privacy/evaluation/exclusion/archive flags control selection. Restore returns review work to pending and does not grant eligibility. Bulk decisions validate all selected records in a transaction and roll back together on failure; existing service contracts determine which transitions are supported.

Review saves preserve omitted flags, tags, reviewer category and notes from the
locked saved row. Explicit flag values must be booleans or integer 0/1; null and
string flags are rejected. An explicit empty tag list clears tags; an omitted
list preserves them. Approval/correction alone does not grant eligibility. Any
privacy, sensitivity, fact-check, evaluation-only or exclusion flag keeps
`training_eligible=0`, even when eligibility is requested.

Single and bulk restore use the same lifecycle-only policy: return to PENDING,
force eligibility off, preserve all restrictions, tags, original text and prior
correction, clear inactive timestamps, and retain the required restoration reason
in `ignored_reason` (also append it to events when that optional table exists).
Restriction fields in a restore request do not remove restrictions. Removing a
restriction requires a separate explicit review save. The queue displays saved
flags/tags; choosing eligibility never unchecks restrictions for the user.

Saves and restores compare `expected_updated_at` inside the write transaction
when supplied. Bulk requests can supply `expected_updated_at_by_id`, an object
mapping every selected review ID (as a string) to its loaded timestamp; one stale
or missing revision rejects the whole operation. Root browser bulk actions send
that map. Revision timestamps advance even if the clock repeats. Legacy callers
without preconditions remain compatible and do not have stale-write protection;
this remediation does not introduce a mandatory-precondition API break.

See [remediation evidence, limitations and source rollback](review-restriction-integrity.md).

`review_integrity.py` checks missing sources/reviews, pending or stale decisions, correction/status conflicts, contradictory eligibility and optional event consistency. Confirmed errors block a new export before output directories are created, with HTTP409 `EXPORT_NOT_READY` and actionable sample/reason evidence. Whitespace/case-only drift and absent optional event history remain visible warnings. Quality/dedup/balance/holdout checks are dataset diagnostics; no model evaluation is performed.

## Limits that remain open

Reviewer categories `human`, `import`, `ai_suggestion` are asserted labels, not authenticated named identities or RBAC. Current manual rows can carry eligibility without the fully proposed human approval/version-bound lifecycle; do not claim that future lifecycle has been implemented. Migration 007 supplies immutable `review_events` and a baseline for reviews that predate that history. The separate reduced Core profile can omit that optional event table. Legacy reviews without authoritative events retain explicit history warnings and cannot acquire fabricated past decisions. No automatic AI approval or historical reconstruction is supplied.

The legacy dataset table, filesystem inventory and prepared canonical registry can represent different scopes. Legacy undeclared state may be treated as Frozen while prepared registry state is Unknown. A canonical read cutover remains unresolved; current counts cannot be inferred from old nine-version reports.

Deterministic checks detect specified structural defects; they do not certify truth, semantic coherence, natural Najdi, safety, rights or consent. Earlier dialect examples and word lists were non-native drafts, never validated Gold or detector ground truth. Native linguistic review remains necessary. Naturalness has no dialect-marker quota; formal Arabic and technical terms are not defects. The rejected external Corpus v1.0 remains NO-GO and is not imported by cleanup.

Dataset-specific `phase38_dataset`, `phase39_edits`, `phase39a_resolution` and `phase310_freeze` preserve local review/remediation/version evidence. Their names and stored IDs are compatibility data; they do not restore removed model evaluation/execution workflows. Evidence counts and limitations are in [verification](verification-evidence.md).
