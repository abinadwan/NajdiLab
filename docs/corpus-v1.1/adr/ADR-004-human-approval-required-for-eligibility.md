# ADR-004 — No generated record becomes training-eligible without explicit human approval

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Context
`_insert_training_item` accepts `training_eligible` from the request (`app/service.py:1449`), and manual items have no review state.

## Decision
Introduce the manual-item review lifecycle (`../03-review-lifecycle.md`). Eligibility is computed only from a human approval bound to the current version and content hash, enforced at four layers: service, DB trigger (008), export gate, and training quality gate. `ai_suggestion` actors can suggest but never approve. Author ≠ approver for generated tiers.

## Consequences
Pre-existing rows become `LEGACY` with values preserved. New rows can never default to `LEGACY` (insert trigger).
