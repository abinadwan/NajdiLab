# Review, quality and provenance

Completed consented Chat pairs enter PENDING with `training_eligible=0`. Generic authenticated ingestion and manual authoring remain available. Originals stay separate from corrections; source Unicode/whitespace and API enum values are preserved. `training_eligible` is a retained dataset field, not an execution control.

Approve, correct, exclude and restore are explicit service/API actions. Corrections retain metadata, reasons and tags; restrictive privacy/evaluation/exclusion/archive flags control selection. Restore returns review work to pending and does not grant eligibility. Bulk decisions validate all selected records in a transaction and roll back together on failure; existing service contracts determine which transitions are supported.

`review_integrity.py` checks missing sources/reviews, pending or stale decisions, correction/status conflicts, contradictory eligibility and optional event consistency. Confirmed errors block a new export before output directories are created, with HTTP409 `EXPORT_NOT_READY` and actionable sample/reason evidence. Whitespace/case-only drift and absent optional event history remain visible warnings. Quality/dedup/balance/holdout checks are dataset diagnostics; no model evaluation is performed.

## Limits that remain open

Reviewer categories `human`, `import`, `ai_suggestion` are asserted labels, not authenticated named identities or RBAC. Current manual rows can carry eligibility without the fully proposed human approval/version-bound lifecycle; do not claim that future lifecycle has been implemented. `review_events` consumers are optional and its proposed migration is not approved by source cleanup. Without authoritative events, complete cross-decision history cannot be proven (`REVIEW_HISTORY_UNAVAILABLE`). No automatic AI approval or historical reconstruction is supplied.

The legacy dataset table, filesystem inventory and prepared canonical registry can represent different scopes. Legacy undeclared state may be treated as Frozen while prepared registry state is Unknown. A canonical read cutover remains unresolved; current counts cannot be inferred from old nine-version reports.

Deterministic checks detect specified structural defects; they do not certify truth, semantic coherence, natural Najdi, safety, rights or consent. Earlier dialect examples and word lists were non-native drafts, never validated Gold or detector ground truth. Native linguistic review remains necessary. Naturalness has no dialect-marker quota; formal Arabic and technical terms are not defects. The rejected external Corpus v1.0 remains NO-GO and is not imported by cleanup.

Dataset-specific `phase38_dataset`, `phase39_edits`, `phase39a_resolution` and `phase310_freeze` preserve local review/remediation/version evidence. Their names and stored IDs are compatibility data; they do not restore removed model evaluation/execution workflows. Evidence counts and limitations are in [verification](verification-evidence.md).
