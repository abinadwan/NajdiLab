# Dataset-first Chat implementation plan

**Goal:** local raw chats through review to external Unsloth, with internal execution retired.
**Architecture:** reuse SQLite/service review/export invariants; add session coordinator, loaded-model inference adapter and small framework-free UI. Keep historical data/contracts.
**Tech stack:** Python 3.11+, SQLite, vanilla JS; optional LM Studio SDK 1.5.0.
**Spec:** [design](../specs/2026-10-31-dataset-chat-design.md).

Global constraints: no main merge/deploy, no installed app/config/service changes, no destructive data/migration changes, Hermes BLOCKED, no direct GGUF, no hidden prompt/tool/RAG, no approximate admission counts, no false test claims.

Review focus: consent revocation during inference; crash/retry receipt integrity; exact loaded model binding; tokenizer/template errors; archived/exported data retention.

- [ ] Task 1 — `tests/test_chat_workspace.py`, `migrations/005_chat_workspace.sql`, `app/chat_workspace.py`, `app/service.py`: RED→GREEN session/create/send/stop/archive/collect/restart/idempotency/transaction tests. Extend ingest with an internally owned connection and optional review creation; preserve public defaults.
- [ ] Task 2 — `app/chat_engine.py`, `app/hardware.py`, integration lease and `tests/test_chat_engine.py`: RED→GREEN exact template admission, count validation, loaded-only capability, no-tool raw completion, unknown Ollama refusal, bounded hardware/no fabricated recommendation.
- [ ] Task 3 — `app/server.py`, `static/chat.js`, `static/chat.css`, `static/app.js`, `static/index.html`, HTTP/Node tests: wire session actions; UI state/recovery/stop/context rollover; retire execution controls and routes, preserve historical reads; test security with disposable synthetic services.
- [ ] Task 4 — Unsloth handoff service/HTTP/UI and tests: eligible records only, messages-format JSONL, no silent replacement of original exports, manifest/provenance/hash, atomic output and rejection of unsupported tool/plain-text objectives.
- [ ] Task 5 — README/CHANGELOG/status/architecture/roadmap/API/rollback/results and source-only policy; run appropriate full suite, docs/JS/compile checks and hosted Windows/Linux CI. Fresh whole-branch review, fix material findings with regression tests, leave independent draft PR unmerged.

Progress/results and any deviations are recorded in [delivery results](../../dataset-chat-results.md). No real engine or hardware stress test is implied by synthetic coverage.
