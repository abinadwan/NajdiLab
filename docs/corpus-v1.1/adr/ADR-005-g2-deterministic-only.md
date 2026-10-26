# ADR-005 — G2 blocks only deterministic defects; meaning, truth and naturalness are human-judged

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
G2 is split into G2-D (deterministic, blocking, precision ≥ 0.95 and recall ≥ 0.90 per code) and G2-H (heuristic, advisory, never blocking). Semantic coherence, factual correctness, naturalness, dialect authenticity beyond rules, helpfulness and safety appropriateness are G3-only. The earlier "≥ 90% of the 192 v1.0 rejections" criterion is withdrawn.

## Consequences
G2 reports must state what they don't cover. G2 is implemented as an extension of `app/dataset_quality.py` (stable finding IDs, severities, Arabic explanations).
