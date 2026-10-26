# ADR-002 — The training objective is conversational SFT for AbuAdwan

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Context
Corpus v1.0 was narrative third-person text for causal LM and failed human review (192/200 rejected). In NajdiLab, `direct_language` assets contribute no gradient (README Phase 3.6; the adapter reports `direct_language: 0`). The existing adapter trains multi-turn `messages` with loss on the final assistant turn.

## Decision
The v1.1 objective is supervised fine-tuning on multi-turn conversations in the existing export format, targeting the behavior defined in `../01-behavior-spec.md`. Narrative and causal-LM data is out of scope for v1.1.

## Consequences
- All assistant turns must meet the behavior spec (earlier turns are context).
- Preference/DPO stays a non-gradient asset until a separate, gated stage is designed.
- **Model-agnostic** (rev. 2): data is stored template-free; the model comes from the registry; the existing tokenizer validation, chat-template hash binding and response-only mask checks decide compatibility (`../01-behavior-spec.md` §1.1). Gemma 4 E2B IT is the initial eligible model; any other model needs owner approval (OA-03).
