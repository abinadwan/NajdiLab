# Phase 5 issue register

Statuses require observed regression evidence before VERIFIED_CLOSED. Historical RED results remain in [execution](public-core-phase5-execution.md) and [verification](public-core-phase5-verification.md). No ownership/license/history approval is inferred from engineering success.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-01 | Critical/P0 | Correction UI omits flags; shared service defaults clear privacy/evaluation/exclusion and may enable eligibility | Candidate transaction + preserve omitted fields; regression pending | FIXED |
| P5-02 | Critical/P0 | Optional stale token and timestamp reuse permit silent overwrite | Mandatory token + transaction + fresh revision; two-client regression pending | FIXED |
| P5-03 | High/P0 | Minimal UI lacks context, saved readback and explicit eligibility | Contextual candidate UI and real browser acceptance pending | OPEN |
| P5-04 | High/P0 | Missing actionable readiness/version inspection and constrained artifact handoff | Candidate-only wrappers/UI and adversarial filesystem tests pending | OPEN |
| P5-05 | Release gate | Historical Git privacy, ownership, license and exact rights remain uncleared | B07 exact manifest/provenance/owner decision package | BLOCKED |

New findings and review outcomes are appended during implementation; no finding is closed merely because code changes.

| P5-06 | High/P0 | New lifecycle SQL initially omitted required timestamps | Fresh exclude/ignore/delete/restore HTTP regression RED then PASS; independent recheck | VERIFIED_CLOSED |
| P5-07 | High | Reviewer assertion mapping and lifecycle reasons initially lost | Preserve/map reviewer, persist reason; HTTP regression RED then PASS; independent recheck | VERIFIED_CLOSED |
| P5-08 | Critical/P0 | Generic save/approval could discard retained correction | All-action no-discard regression RED then PASS; independent recheck | VERIFIED_CLOSED |

Goal1 backend defects P5-01/P5-02 are FIXED with passing privacy/race tests; complete UI closure awaits Goal2 browser evidence. Same-status edits use existing schema without unapproved review-event migrations. Ordinary-decision reason is a lifecycle-only API field, not a complete event-history guarantee.
