# Training correctness: Unsloth export, masks, diagnostics and readiness (V2.2.0)

| | |
|---|---|
| Branch | `update-project` (Draft PR #23). Development candidate, not a release. |
| Code | `app/unsloth_export.py` (profiles), `scripts/verify_unsloth_studio.py` (token-level check), `app/service.py` (`create_export` diagnostics), `app/dataset_platform.py` (`dataset_health` readiness) |
| Tests | `tests/test_unsloth_export.py`, `tests/test_verify_unsloth_studio.py`, `tests/test_dataset_diagnostics_lifecycle.py` |

## 1. The problem that was observed

The first Qwen2.5-0.5B experiment exported a conversational prompt/completion file and loaded it directly in Unsloth Studio. Studio's token preview showed earlier assistant answers — including answers the reviewer had corrected — selected for training.

**Cause (from Studio's own code, Unsloth 2026.11.2 / TRL 0.23.1):** for chat-shaped rows, "Train on completions" uses `train_on_responses_only` with the model's turn markers (for Qwen, `<|im_start|>user` and `<|im_start|>assistant`). Every assistant turn in the rendered conversation becomes a target. The prompt/completion layout is correct for programmatic TRL with `completion_only_loss=True`, which supervises only `completion`, but Studio renders `prompt` and `completion` as one conversation.

## 2. Export profiles

Each reviewed record has exactly one approved target, its last assistant message (`target_message_index`, one-hot `message_loss_mask`). The profiles differ only in how the trainer finds it:

| Profile | File layout | What the trainer supervises | Use with |
|---|---|---|---|
| **Unsloth Studio — SFT (chat)** `studio_chat` (default) | `{"messages":[user, assistant]}` with exactly one assistant message | the approved answer; single-turn records are exported unchanged, earlier turns of a multi-turn record are written as a transcript (`User: …` / `Assistant: …`) inside the user turn | Unsloth Studio, "Train on completions" on, packing off |
| **Unsloth Studio — SFT (Alpaca)** `studio_alpaca` | `instruction` (last user message), `input` (earlier turns), `output` (approved answer) | `output` only (after `### Response:`) | Unsloth Studio; note that the Alpaca prompt differs from the model's chat template used at inference |
| **Unsloth / TRL in Python** `trl_prompt_completion` | `prompt` (all earlier messages), `completion` (approved answer) | `completion` only, **if** `completion_only_loss=True` | programmatic TRL/Unsloth only; never Unsloth Studio |

Templates are not interchangeable: Alpaca, ChatML/`messages`, ShareGPT, conversational prompt/completion and a model's native chat template each tell the trainer something different. NajdiLab does not apply a chat template itself; Studio applies the training model's template (for Qwen2.5 this includes its default system prompt, as llama.cpp does at inference).

The manifest (schema 2) records the profile, format, trainer settings, context rendering, single/multi-turn counts, independent source conversations, a smoke-test warning below three sources, and `verification.token_level: not run by NajdiLab`.

## 3. Token-level verification

`scripts/verify_unsloth_studio.py` runs with the Python inside the user's Unsloth Studio install. For **every** record it runs Studio's token-preview path (dataset formatting, chat template and "train on completions" masking used for Studio training) with the training model's real tokenizer, then requires one contiguous trained span that decodes to exactly the approved answer, and reports truncation. It imports Studio from the user's installation (AGPL-3.0) and copies none of its code; its compile cache goes to a temporary folder.

### Results

Training model tokenizer `unsloth/Qwen2.5-0.5B-Instruct` (cached, offline), max sequence length 2048, Unsloth Studio with unsloth 2026.11.2, trl 0.23.1, transformers 5.5.0, on 2026-11-04.

**Synthetic fixture** (privacy-safe, shaped like the experiment: 10 records, growing multi-turn rows whose earlier assistant turns are the model's original, partly wrong answers):

| Profile | Studio format | Verdict | Trained / masked tokens |
|---|---|---|---|
| studio_chat | chatml_messages | PASS 10/10 | 108 / 614 |
| studio_alpaca | alpaca | PASS 10/10 | 108 / 667 |
| prompt/completion loaded in Studio | chatml_conversations | FAIL 6/10 (earlier answers trained) | 204 / 568 |

**The owner's real `gold-v001`** (10 approved records, 8 multi-turn, 2 single-turn, 2 source conversations), on the installed test copy; reports contain token counts and hashes only:

| Handoff | Studio format | Verdict | Trained / masked tokens |
|---|---|---|---|
| original experiment export (prompt/completion) | chatml_conversations | **FAIL 8/10** | 1,650 / 828 — 1,096 trained tokens were earlier assistant answers |
| studio_chat | chatml_messages | **PASS 10/10** | 554 / 1,758 |
| studio_alpaca | alpaca | **PASS 10/10** | 554 / 1,802 |

Regression references from the manual Alpaca conversion (26, 52 and 224 trained tokens in three Studio previews) are reproduced exactly by `studio_alpaca` records 7, 10 and 1. Totals differ only by the context layout.

`tests/test_verify_unsloth_studio.py::test_unsloth_studio_trains_only_the_approved_answer_for_studio_profiles` repeats the synthetic check when `NAJDILAB_UNSLOTH_STUDIO_PYTHON` points at Studio's Python (skipped otherwise).

### What this does and does not prove

- Proven for this Studio version and tokenizer: which tokens Studio trains for each profile.
- Not proven: that training on these records improves the model. The experiment's three steps showed no measurable change and had no evaluation set.
- Not run: an actual Studio training job after this change; another model family or tokenizer (re-run the verifier with that model).

## 4. Diagnostics lifecycle

**Cause of the `gold-v001` → `gold-v001-derived` detour:** `create_export` published each new version as `Frozen` without diagnostics; Dataset Health requires current diagnostics for Draft and Frozen versions; regeneration is refused for Frozen versions (they are immutable). Only a derived Draft could obtain them.

- New versions: diagnostics (`loss-mask-validation.json`, `balancing_report.json`) are generated in the staging folder, bound to the version name, the training-file fingerprint and the artifact hashes, before the version is published as Frozen.
- Older Frozen versions without stored diagnostics: Dataset Health computes them read-only from a private copy of the hash-verified files and labels them *computed now, not stored*; the version is never written. If the files no longer match the manifest hashes, the version is invalid.
- Stored diagnostics that no longer match the files remain an error.

On the installed copy, `gold-v001` now reads VALID (diagnostics computed on read, loss masks 10/10) without a derived copy; its 18 files were unchanged before and after.

## 5. Readiness states

`GET /api/v1/dataset-versions/<v>/health` → `readiness`:

| State | Values | Meaning |
|---|---|---|
| Structural validity | `VALID`, `INVALID` | structure, unique targets, loss masks, file hashes and diagnostics; says nothing about quality |
| Training compatibility | `STRUCTURE_CHECKED`, `BLOCKED` | the formatting and supervision checks NajdiLab can run; token level is checked outside NajdiLab with the verifier |
| Evaluation readiness | `NO_EVALUATION_DATA`, `LEAKAGE_DETECTED`, `INDEPENDENT_SAMPLES_AVAILABLE` | whether independent evaluation samples exist; zero samples is never evaluation-ready |

No numeric threshold is presented as proof of quality. `gold-v001` reads VALID / STRUCTURE_CHECKED / NO_EVALUATION_DATA with 2 independent training sources.
