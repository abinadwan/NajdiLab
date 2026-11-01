# NajdiLab

Local model conversations → human review and correction → validated, versioned datasets → external Unsloth training.

NajdiLab is a dataset preparation platform, not a trainer or a model runtime. LM Studio and Ollama remain externally managed. **Internal training, WSL workers, model download/merge/GGUF/deployment controls are retired.** Existing data, historical jobs/logs, prior exports and applied migrations are preserved.

## Current development scope

This feature branch is based on main `d992b0a` (PR #8). PR #10 is closed, draft and unmerged; none of its changes are merged here. Issue #9 remains open. This work does not authorize merging main, installing an update, changing third-party applications, publishing source or running training.

- **Chat Workspace:** simple text-only multi-turn conversations created inside NajdiLab; no NajdiLab system/developer prompts, tools, RAG, external memory or response rewriting. Complete raw history is retained and sent unchanged through the normal engine template.
- **Exact context admission:** input template/token count + reserved reply must fit the selected budget and loaded context. Overflow closes/preserves the chat and opens an empty one, without silent truncation, summarization or draft replay.
- **Separate collection:** OFF by default/restart. Only newly completed consented pairs enter PENDING review, never training-approved automatically. Saved Chat history is separate; native application chats are not harvested. **Hermes stays BLOCKED.**
- **Review and dataset quality:** immutable originals, manual edits/version history, explicit human eligibility, privacy/exclusion checks, dedup, balance, holdout/leakage validation and immutable dataset versions.
- **External Unsloth handoff:** conversational prompt/completion JSONL, provenance and hashes. Completion contains only the approved final target; external Unsloth/TRL must use completion_only_loss=True, packing=False, and reject overlength records. No trainer is invoked.

## Explicit limits — not a completed dual-engine acceptance

**LM Studio:** implemented against optional pinned Python SDK 1.5.0 and tested with synthetic engine transports. Exact count and prediction bind an existing loaded instance reference; unknown SDK/API behavior fails closed. It never loads/reconfigures a model. Real engine/model compatibility and the owner's Windows acceptance are **NOT TESTED**.

**Ollama:** discovery/selection/approved connectivity tests remain. Chat sending is **BLOCKED** because an exact supported public template-token preflight is not yet verified. This branch does not pretend a character-ratio estimate proves context safety.

**Hardware:** explicit read-only RAM/GPU memory snapshot; **no numeric safe context recommendation** when KV/cache placement/resident weights/overhead/concurrent allocation evidence is missing. No 64K guarantee or allocation stress test.

Saved text and raw review archives can contain private information. Collection consent is not text anonymization. Archive retains data and old exports while excluding linked reviews from future selection; physical erasure is deferred for a separately reviewed retention decision. New Unsloth handoffs require the new context privacy attestation; preserve historical exports and build a fresh reviewed version instead of rewriting them.

## Run and develop

Core: Python 3.11+, SQLite 3.24+, modern browser, standard library only. Follow [installation](docs/installation.md) and [developer setup](docs/developer-setup.md). Windows launch: `run.ps1` or `run.cmd`; Linux: `sh run.sh`. Default loopback URL: http://127.0.0.1:8770. No network/public/multi-user deployment is supported.

For Chat, the optional `requirements-chat.txt` belongs in NajdiLab's own environment during an approved update. It does not install anything into LM Studio/Ollama. No owner environment has been updated by this PR. [Chat behavior, API, consent, compatibility and rollback](docs/chat-workspace.md).

Development checks:

```text
python -m pip install -r requirements-dev.txt -r requirements-chat.txt
python -m pytest -q tests -rs
node --test tests/chat-ui.test.cjs tests/integrations-ui.test.cjs
python scripts/check_docs.py
```

Tests use synthetic data and disposable servers. Missing private historical artifacts are explicit skips. Final-head Windows/Linux CI and real owner acceptance are separate gates; see [actual results](docs/dataset-chat-results.md), not old screenshots or historical counts.

## Architecture and project roadmap

```mermaid
flowchart LR
  I[Settings: approved local runtime] --> C[Raw Chat / exact context admission]
  C --> S[(Own saved complete conversations)]
  C -->|Separate opt-in; complete pairs only| R[Pending human review]
  R --> H[Corrections and explicit eligibility]
  H --> Q[Privacy / dedup / quality / holdout]
  Q --> V[Immutable dataset version]
  V --> U[Prompt-completion JSONL + provenance]
  U --> E[External Unsloth, operated separately]
```

- [Read-only audit and KEEP/REMOVE/DEPRECATE decisions](docs/scope-audit-2026-10-31.md)
- [Current phased roadmap](docs/roadmap.md) · [architecture](docs/architecture.md) · [API](docs/api-reference.md)
- [Dataset/review lifecycle](docs/data-03-04-06-09-review-management.md) · [export integrity](docs/data-07-08-review-integrity-export-readiness.md)
- [Security](SECURITY.md) · [backup/restore](docs/backup-and-restore.md) · [current status](PROJECT_STATUS.md)
- [Historical screenshots](docs/screenshots.md) and older training/phase guides are retained as evidence; they do not describe the current active UI/scope.

## Source and distribution

This is the private repository. No active redistribution license or publication approval is granted by this change. The separate Public Core source-only candidate remains an independently reviewed scope; see [release decision](docs/public-release-decision.md), [source boundaries](docs/public-private-boundary.md) and [attribution](docs/third-party-attributions.md). New Chat/handoff files are explicitly excluded from that candidate. Reused shared service/privacy/install files are repinned only with candidate regression verification; that is not publication approval.
