# Dataset-first Chat implementation plan

**Goal:** local raw chats through review to external Unsloth, with internal execution retired.
**Architecture:** reuse SQLite/service review/export invariants; add session coordinator, loaded-model inference adapter and small framework-free UI. Keep historical data/contracts.
**Tech stack:** Python 3.11+, SQLite, vanilla JS; optional LM Studio SDK 1.5.0.
**Spec:** [design](../specs/2026-10-31-dataset-chat-design.md).

Global constraints: no main merge/deploy, no installed app/config/service changes, no destructive data/migration changes, Hermes BLOCKED, no direct GGUF, no hidden prompt/tool/RAG, no approximate admission counts, no false test claims.

Review focus: consent revocation during inference; crash/retry receipt integrity; exact loaded model binding; tokenizer/template errors; archived/exported data retention.

- [x] Task 1 — Own complete Chat storage is separate from review capture; reuse internally owned ingest connection with raw-text preservation. Session/send/stop/archive/consent/restart/idempotency/transaction and atomic rollover proofs pass.
- [x] Task 2 — Exact instance-bound LM Studio template admission, count validation, loaded-only/no-tool completion, safe Ollama refusal and bounded unknown hardware recommendation proved. Actual Ollama sending and numeric memory guidance remain incomplete owner requirements.
- [x] Task 3 — Framework-free Chat UI/API, security, overflow/recovery/Stop and retirement controls verified with HTTP, Node and real hosted Windows/Linux browser fixtures.
- [x] Task 4 — External Unsloth conversational prompt/completion JSONL preserves the sole target loss mask. Existing exports remain; handoff verifies privacy-attested frozen inputs/provenance/hashes and publishes atomically. Generic all-assistant messages training was rejected because it would change approved target loss.
- [x] Task 5 — Audit, design, current docs, rollback and source-only policy updated. Fresh review's material findings fixed with regressions. Local/hosted results recorded; independent Draft PR #11 retained unmerged. Results-only followup is not a product-code change.

Progress/results and any deviations are recorded in [delivery results](../../dataset-chat-results.md). No real engine or hardware stress test is implied by synthetic coverage.
