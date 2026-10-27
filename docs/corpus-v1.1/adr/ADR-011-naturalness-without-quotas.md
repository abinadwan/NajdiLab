# ADR-011 — Natural Najdi without dialect quotas

- Status: Accepted (Phase 1 rev. 2, owner approval 2026-10-23) · Date: 2026-10-23

## Context
Corpus v1.0 stuffed fixed dialect phrases into templates and failed human review. The owner directed that the Najdi assistant use natural contemporary Riyadh Najdi without artificial marker quotas or repetitive expressions, while supporting technical terminology and appropriate formal Arabic.

## Decision
No minimum, target or quota for dialect markers anywhere: not in the generator, G2 or G3 rubrics. G2 may flag only *excess or repeated* markers (advisory). MSA is never a G2 defect; its appropriateness is judged by reviewers against the register matrix. Naturalness is a human judgment (G3).

## Consequences
Generator tests must prove no marker insertion for density (K24). Reviewers need native competence (PRQ-LANG-01, OA-11).
