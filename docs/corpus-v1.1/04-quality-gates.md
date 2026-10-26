# 04 — Quality Gates G1–G4 (revised G2)

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23) (rev. 2: no dialect quotas; provisional word lists are advisory until native validation; traceability in `12-traceability-matrix.md`).**

The gates are independent. Each has its own owner, inputs, versioned configuration and report. A later gate never changes an earlier gate's result. A gate pass is bound to a version: generator version for G1, rule-set version for G2, review batch for G3, dataset and job fingerprints for G4.

## G1: Generator validation (the tool, not the data)

| Item | Definition |
|---|---|
| Owner | Engineering. Approved by the data owner |
| Runs | Before any generation batch can be started from the UI. The Generation page refuses to run a generator version without a recorded G1 pass |
| Checks | Unit tests for every variation operator; typed-lexicon consistency (every entry has gender, number, definiteness, part of speech, preposition flag and topic compatibility); agreement-engine tests per group type × layer; determinism (same seed → identical output hashes); fallback counters reported, never silent; **the gate must be able to fail** (seeded defect batches produce FAIL) |
| Regression fixtures | Read-only copies of Corpus v1.0 evidence (hash-verified against `najdi-corpus-v1/governance/v1.0/ORIGINAL_FILES.sha256`) |
| Pass | All tests green; zero Corpus v1.0 defect patterns reproducible by the generator (property tests); determinism proven |

## G2: Automated linguistic validation (revised)

G2 exists to cut human review load and block **mechanically provable** defects. **G2 must not claim to measure meaning, truth or naturalness.** Those belong to G3.

### G2-D: deterministic defects (blocking)

A finding is G2-D only if a rule can decide it from the text alone with near-zero ambiguity and a human can verify it in seconds.

| Code (proposed) | Defect | Example (from Corpus v1.0 evidence) |
|---|---|---|
| `LING_PREP_STACK` | Stacked prepositions | «في عند الباب», «إلى على طاولة» |
| `LING_AGREEMENT_COLLECTIVE` | Collective noun with a masculine verb in a fixed template position | «اجتمع مجموعة» |
| `LING_CASE_AFTER_PREP` | Dual or sound-plural nominative after a preposition or in a construct | «عند شخصان», «وصول شخصان» |
| `LING_VERB_AFTER_PREP` | Preposition followed directly by an imperfect verb | «ساعدهم على يحددون» |
| `LING_FOREIGN_DIALECT_STRONG` | Strong Egyptian, Levantine or Maghrebi markers (≥2, or 1 strong outside quotation marks) in a Najdi-layer assistant turn | «إزاي … دلوقتي» |
| `LING_CARICATURE_REPEAT` | The same courtesy formula repeated within one turn | «يا طويل العمر» ×2 |
| `LING_PHONETIC_SPELLING` | Nonstandard dialect spelling (e.g. چ) | — |
| `LING_EXACT_SENTENCE_REPEAT` | An identical sentence repeated within a record | — |
| `LING_SLOT_VALUE_REPEAT` | Same generator slot value more than 2 times in a record (generated tiers only) | «رائحة قهوة» ×4 |
| `LING_META_TEXT` | Template, prompt or AI-meta leakage | «بصفتي نموذج» |
| `LING_EMPTY_OR_TRUNCATED_TARGET` | Empty or cut-off assistant target | — |
| `LING_ROLE_LABEL_IN_TEXT` | `user:` / `assistant:` labels inside content | — |
| `LING_TEMPLATE_TOKEN_IN_CONTENT` | Model chat-template or special tokens stored in content (model independence, BR-02) | — |

**Provisional-list rule.** Codes that rely on dialect word lists (`LING_FOREIGN_DIALECT_STRONG`, `LING_CARICATURE_REPEAT`, `LING_PHONETIC_SPELLING`) run in **advisory mode** until PRQ-LANG-01 (native validation of the lists) and the precision/recall targets below are met. Only then may they block.

### G2-H: heuristic signals (advisory, never blocking)

These route items to review and are shown to reviewers. They can't pass or fail an item.

| Code (proposed) | Signal |
|---|---|
| `SIG_MSA_DENSITY_IN_NAJDI` | MSA case endings and bureaucratic connectors in **casual** Najdi-context turns only. MSA is correct in technical, sensitive and formal contexts (BR-14) |
| `SIG_DIALECT_MARKER_EXCESS` | **Upper side only**: unusually dense or repeated dialect markers (caricature risk). **There's no minimum and no quota; too few markers is never flagged** (BR-10) |
| `SIG_COURTESY_DENSITY` | Courtesy formulas piling up before the answer |
| `SIG_PREAMBLE` | Opening filler before answering |
| `SIG_PERSONA_GENDER_INCONSISTENT` | Self-reference gender inconsistent with the persona policy (morphology heuristic) |
| `SIG_ADDRESS_GENDER_SWITCH` | User-addressing gender changes without a user signal |
| `SIG_REGISTER_FLIP` | Reply register changes between consecutive turns without a user or context cause |
| `SIG_HIJAZI_CLUSTER` | إيش/دحين/أبغى clustering in Najdi mode |
| `SIG_TEMPLATE_CONCENTRATION` | Delexicalized sentence skeleton shared by more than X% of the batch or dataset |
| `SIG_LENGTH_OUTLIER` | Target length outside the task-type band |
| `SIG_NEAR_DUPLICATE` | Near-duplicate prompt or target (existing `NEAR_DUPLICATE_PROMPT` pattern) |
| `SIG_REGISTER_MISMATCH` | Reply register differs from `language_layer` / `user_register` metadata |

### Human-only dimensions (G3; G2 must never score these)

Semantic coherence and scenario fit · factual correctness · naturalness and native-likeness · dialect authenticity beyond the deterministic rules · helpfulness · safety appropriateness · tool-behavior correctness beyond schema validity.

### G2 acceptance criteria (revised)

| Criterion | Target | How measured |
|---|---|---|
| G2-D precision | ≥ 0.95 per code | Human confirmation of a stratified sample of G2-D findings (at least 30 per code, or all if fewer) |
| G2-D recall | ≥ 0.90 per code | Seeded-defect suite (≥ 20 seeded instances per code) **plus** the subset of Corpus v1.0 rejections that a human annotator labels as containing that deterministic defect |
| G2-D false blocks on approved Gold | 0 | Run against all approved Gold and existing frozen training records (read-only) |
| G2-H | No pass/fail threshold | Report distribution; track the correlation with G3 rejection over the pilot |
| Scope honesty | 100% | Every G2 report states which dimensions it does **not** cover |

**Correction to the earlier criterion.** "Catch ≥ 90% of the 192 v1.0 rejections" is **withdrawn**. Many of those rejections are semantic (scenario mismatch, incoherence, unnaturalness), and only G3 can decide those. The replacement is per-code recall on the deterministic-defect-labelled subset.

### G2 configuration
Rule sets are versioned files under NajdiLab configuration (location chosen in Phase 2). The rule-set version is frozen before a G3 sample is drawn, so rules can't be tuned to a known sample.

## G3: Human review

| Item | Definition |
|---|---|
| Owner | Named native reviewers; linguistic lead adjudicates |
| Scope | 100% of Gold (peer review); for Silver and Bronze, 100% in the pilot and a stratified sample at scale (sampling rule to be approved after the pilot) |
| Workflow | `03-review-lifecycle.md` |
| Rubric | Reuse dimensions from `phase38_dataset.py:153` (`factual_correctness, instruction_following, dialect_quality, natural_arabic, concision, context_continuity, tool_correctness, hallucination_risk, repetition_risk`) and add `scenario_fit`, `register_adherence`, `safety_appropriateness` |
| Defect tags | Existing `review_tags` vocabulary (`001_initial.sql`) plus proposed `agreement_error, template_repetition, scenario_mismatch, register_mismatch, caricature, persona_inconsistency` (vocabulary change in 008, which is blocked) |
| Double annotation | ≥ 15% of each batch (minimum 30 items in the pilot) assigned to two reviewers blind to each other |
| Blinding | Reviewers see G2-D findings (they're facts) but not G2-H scores by default; tier is hidden where feasible |
| Pass (pilot, per tier) | Gold ≥ 57/60 approved (incl. minor correction); Silver ≥ 54/60; Bronze ≥ 51/60 or the tier is dropped; DIALECT-type rejections ≤ 3/60; no single defect tag > 3/60; Cohen's κ (accept/reject) ≥ 0.6 |

## G4: Training readiness

| Item | Definition |
|---|---|
| Owner | Data owner |
| Checks (existing) | Dataset Health READY; release validation VALID; eval leakage CLEAN; loss masks valid; export gate READY; existing training quality gate, preflight, execution gate, dry run |
| Checks (new) | Zero generated items without a matching approval; zero G2-D blockers; G3 thresholds met for every batch present; template-level train/eval leakage check (skeleton overlap); dataset manifest records tier counts and approval coverage |
| Output | Existing READY job → existing single-use authorization. **Training still requires an explicit human action** |
