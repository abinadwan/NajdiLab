# 12 — Traceability Matrix: Behavior Requirements → Validation

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23), rev. 2.**

## Validation methods

| Code | Method | Can block? | What it can establish |
|---|---|---|---|
| **D** | G2-D deterministic detector (`04-quality-gates.md`) | Yes | A specific, mechanically decidable defect is **present**. Never that the text is correct, natural or true |
| **H** | G2-H advisory signal | No; it routes to review | A statistical hint worth a human look |
| **S** | Existing structural or platform check (`dataset_quality`, loss masks, model registry, tokenizer and template validation, capability registry, export gate) | Yes | Format, provenance, masking and leakage integrity |
| **R** | G3 human review: rubric dimension and/or defect tag | Yes (via review decision) | Meaning, truth, naturalness, appropriateness: **human judgment only** |
| **P** | Process control (review lifecycle, roles, authorization) | Yes | Who approved what, and when |

**Non-claim.** No automated check in this design establishes semantic correctness, factual accuracy, naturalness, dialect authenticity or helpfulness. Passing D/H/S means only "no known mechanical defect found". Every training-eligible record additionally needs an **R** approval by a human (`03-review-lifecycle.md`).

## Matrix

| ID | Requirement (`01-behavior-spec.md`) | D | H | S | R (rubric / defect tag) | P |
|---|---|---|---|---|---|---|
| BR-01 | All assistant turns meet the spec, not only the target | `LING_*` run on every assistant turn | All signals per turn | — | Reviewer sees the full conversation; rubric applies to all turns | Approval covers the whole record version |
| BR-02 | Model independence | `LING_ROLE_LABEL_IN_TEXT`; new `LING_TEMPLATE_TOKEN_IN_CONTENT` (special or control tokens in stored content) | — | Registry validation; tokenizer and chat-template hash binding; exact response-only mask under the selected template (existing adapter validate and dry run) | — | Model change needs owner approval (OA-03) |
| BR-03 | Self-reference masculine first person (P1-04) | — | `SIG_PERSONA_GENDER_INCONSISTENT` (morphology heuristic) | — | `register_adherence`; tag `persona_inconsistency` (proposed) | — |
| BR-04 | User addressing policy (P1-04) | — | `SIG_ADDRESS_GENDER_SWITCH` (heuristic) | — | `context_continuity`; tag `wrong_context` (existing) | — |
| BR-05 | Warm, direct; no sycophancy or courtesy chains | `LING_CARICATURE_REPEAT` (same formula twice in a turn) | `SIG_COURTESY_DENSITY` | — | `natural_arabic`, `concision`; tag `too_verbose` (existing) | — |
| BR-06 | Honest uncertainty; no invented tool results or citations | — | — | Native tool-use validation and authoritative tool-result contract (existing Phase 3.7) | `factual_correctness`, `hallucination_risk`, `tool_correctness`; tags `hallucination`, `factual_error` (existing) | — |
| BR-10 | Natural Riyadh Najdi; **no marker quota** | — (no minimum is ever checked) | `SIG_DIALECT_MARKER_EXCESS` (upper side only), `SIG_TEMPLATE_CONCENTRATION` | — | `dialect_quality`, `natural_arabic`; tags `dialect_issue`, `unnatural_arabic` (existing), `caricature` (proposed) | Native reviewer required for Najdi-layer approval (DF-01 default) |
| BR-11 | No Egyptian, Levantine or Maghrebi forms in Najdi turns | `LING_FOREIGN_DIALECT_STRONG` (strong markers; provisional list, PRQ-LANG-01) | `SIG_HIJAZI_CLUSTER` | — | `dialect_quality`; tag `dialect_issue` | — |
| BR-12 | No MSA case-ending register in casual Najdi turns; no caricature; no phonetic spelling | `LING_PHONETIC_SPELLING`, `LING_CARICATURE_REPEAT` | `SIG_MSA_DENSITY_IN_NAJDI` (casual contexts only) | — | `register_adherence`; tag `register_mismatch` (proposed) | — |
| BR-13 | Standard orthography; terms and code untouched | `LING_PHONETIC_SPELLING`; code-fence and replacement-character checks (existing `SUSPICIOUS_FORMATTING`) | — | — | `natural_arabic`; tag `format_failure` (existing) | — |
| BR-14 | Technical terms and formal Arabic supported where appropriate | — (MSA is never a G2-D defect) | — | — | `register_adherence` (judged against the §4 matrix) | — |
| BR-20 | Register matrix (user register × context) | — | `SIG_REGISTER_MISMATCH` (reply register ≠ metadata `language_layer` / `user_register`) | Metadata validation: `language_layer` ∈ allowed set (existing `service.py:50`) | `register_adherence`; tag `register_mismatch` | — |
| BR-21 | Explicit language request wins and persists | — | `SIG_REGISTER_MISMATCH` after a detected request phrase (heuristic) | — | `instruction_following`, `context_continuity`; tag `ignored_user_instruction` (existing) | — |
| BR-22 | No register flip-flopping without cause | — | `SIG_REGISTER_FLIP` | — | `context_continuity` | — |
| BR-23 | Rewrite tasks follow the requested register | — | — | — | `instruction_following` | — |
| BR-30 | Answer first; no preamble | — | `SIG_PREAMBLE` (opening-phrase heuristic) | — | `concision`, `instruction_following` | — |
| BR-31 | Concise by default | `LING_EMPTY_OR_TRUNCATED_TARGET` (lower bound only) | `SIG_LENGTH_OUTLIER` (per task type) | — | `concision`; tags `too_verbose`, `too_short` (existing) | — |
| BR-32 | Keep constraints across turns; don't re-offer rejected options | — | — | — | `context_continuity`; tags `forgot_previous_constraint`, `repeated_rejected_option` (existing) | — |
| BR-33 | No repetition within a reply | `LING_EXACT_SENTENCE_REPEAT`, `LING_SLOT_VALUE_REPEAT` (generated tiers) | `SIG_NEAR_DUPLICATE` | Existing `EXACT_DUPLICATE` across records | `repetition_risk`; tag `template_repetition` (proposed) | — |
| BR-34 | Factual discipline | — | — | — | `factual_correctness`, `hallucination_risk`; tags `factual_error`, `hallucination`; flag `needs_fact_check` (existing column) | Items with `needs_fact_check` can't be approved until resolved (proposal) |
| BR-35 | Tools only within the registry; no claimed execution without a result | — | — | Capability registry, schema and native-mask validation (existing) | `tool_correctness` | — |
| BR-36 | Clarify when ambiguity is costly | — | — | — | `instruction_following` | — |
| BR-37 | Safety: brief refusal in the same register | `LING_META_TEXT` (AI-meta phrasing) | — | Privacy flags (`contains_sensitive_data`, `contains_personal_data`) block eligibility (existing) | Rubric `safety_appropriateness` (proposed) | — |
| BR-40 | Task taxonomy, domain and quality focus recorded | — | — | Metadata validation against the controlled vocabularies (Phase 5) | `scenario_fit` (proposed); tag `scenario_mismatch` (proposed) | Coverage report per quality-focus key (existing v009 pattern) |

## Coverage check

Every BR-xx has at least one **R** or **S** entry. Requirements whose only automated support is **H** (BR-03, -04, -20…-22, -30) depend entirely on human review for pass/fail. Requirements with **no** automated support (BR-14, BR-23, BR-32, BR-34, BR-36) are human-only by design.

## Notes
- All G2 word lists (BR-11, BR-12) are provisional until PRQ-LANG-01. Until validated, detectors built on them run in **advisory mode only**, even if classed G2-D, and become blocking only after native sign-off and the precision/recall targets in `04-quality-gates.md` are met.
- New tags and rubric dimensions marked "proposed" need the `review_tags` vocabulary rebuild in migration 008 (blocked; `15-migration-loader-guard.md`).
