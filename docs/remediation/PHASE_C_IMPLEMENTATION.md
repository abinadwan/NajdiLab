# Phase C implementation record — real AI engine acceptance

Status: **PREPARATORY IN_PROGRESS / DRAFT**. Owner authorized beginning Phase C in a **separate pull request** on 2026-11-02 while Phase B PR #19 remains Draft. This is an explicit **sequencing exception for source-only development**, not approval to merge or deploy Phase C early. The Phase C PR targets the Phase B feature branch so its diff does not include Phase B work. After Phase B passes acceptance and merges, retarget Phase C to `main`, inspect the diff and rerun tests. **Do not merge Phase C before Phase B.**

## Six original findings (no added finding IDs)

| ID | Work | State |
|---|---|---|
| QA-02 | Nine skipped real-Ollama tests | BLOCKED on real disposable Ollama and owner approval |
| AI-01 | LM Studio `RESULT_MISMATCH` on `google/gemma-4-e4b` | OPEN; prior owner observation, not reproduced here |
| AI-02 | Identify the failed LM Studio post-generation integrity predicate | SOURCE IMPLEMENTED / PENDING VERIFICATION |
| AI-03 | Actual-model Ollama integration acceptance | BLOCKED on owner-local environment |
| AI-04 | Actual runtime contracts: immutable identity, full token count, cancellation, context overflow | OPEN; source/synthetic assessment only until owner hardware tests |
| AI-05 | Independent privacy and collection acceptance | OPEN; must demonstrate collection OFF by default, explicit consent, no native chat harvesting, restricted pairs never training eligible |

## Increment 1 — content-free LM Studio mismatch diagnostics

Existing `LoadedModel.generate` refused any mismatch if one of four checks failed: instance reference, structured output, streamed text equivalence, or final prompt token count. All four reported the generic `RESULT_MISMATCH`. This increment preserves that **same external error code** and strict refusal, while reporting an **allowlisted check name only** over the bounded helper process wire:

- `INSTANCE_REFERENCE`: post-response model instance reference changed.
- `STRUCTURED_OUTPUT`: model returned structured data, not strictly plain text.
- `STREAM_CONTENT`: final content differs from fragments emitted by the stream.
- `PROMPT_TOKEN_COUNT`: reply statistics disagree with the measured tokenized prompt.

Only a fixed safe explanation is shown to the operator. Never emit actual instance identifiers, model output, prompts, token sequences, SDK exception bodies, or the unsanitized child-process `check` string. Unknown identifiers keep the generic error. No failing result is saved into the chat or training dataset. Existing pre-inference checks are unchanged.

**Source acceptance added:** parameterized fake-SDK checks for all four predicates and privacy; whitelist mapping from worker errors to public generic code; unknown-code rejection; compatibility of the fixed `RESULT_MISMATCH` external code. These are synthetic tests, not reproduction of the real Gemma 4 mismatch. All tests must be run before marking this increment VERIFIED. Run full suite and Core candidate after changes; hosted Windows/Ubuntu remain pending while GitHub Actions allocation is exhausted.

## Gates and exclusions

- No local Windows, WSL, Hermes, Telegram/WhatsApp, Ollama or LM Studio service changes are authorized.
- No model downloads, execution, telemetry export, new network discovery, inference prompts or private data reads.
- Do not flip `NAJDILAB_REQUIRE_FRESH_SIGNATURE`, enable legacy ingress, or alter collection consent policy.
- Hugging Face Direct stays a disabled future preview.
- Real-model/hardware tests are **not** represented as successful until separately authorized and run on disposable/owner-approved instances. Respect the existing 9 real-Ollama skips.
- QA-03 private historical artifacts from Phase B and QA-06 external Hermes sender verification are not waived by opening Phase C.
- Phase B PR #19 remains Draft; Phase C is a separate stacked Draft PR, not a second Phase B PR.

Rollback: revert this Phase C commit before deployment; no schema, persistent data, downloaded model or backup was changed. If retargeting after Phase B merge produces conflicts, reconcile against reviewed `main` and do not force-push or bypass checks.
