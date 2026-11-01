# NajdiLab scope audit — 2026-10-31

## Read-only baseline and authority

Owner's current request supersedes older training roadmaps: **local model conversations → human review/correction → validated, versioned datasets → external Unsloth export**. No direct GGUF runtime, training execution, native application history harvesting or changes to installed services.

Reviewed `main` at `d992b0ac3139acd55602482fad007bb04a84855f` (merged PR #8). GitHub PR #10 is **closed, draft, unmerged**, head `2870eae7987ca959d53a7f9bd688c62cabcb2575`, targeting `feat/settings-integrations`. Issue #9 remains open. This independent branch starts at main; it neither merges nor cherry-picks #10. Its native-source diagnostics are not present or implied here.

Read-only review covered app modules, static views/controllers, HTTP dispatch/security, tests, four active migrations, proposed migrations in plans, public-source policy/build, scripts, README/status and architecture/corpus/training roadmaps. No installed NajdiLab database, original-app chats, weights, credentials, configurations or live services were opened. The clean checkout has **no data/, datasets/, exports/, training/ or reports/**; these are ignored operator assets, not evidence of empty installed data. Historical data-bearing Phase 3 modules remain protected; this task does not approve redistribution.

## Current behavior and invariants

`server.py` dispatches browser writes after Host/Origin/CSRF/framing checks. `service.ingest_turn` creates a conversation, paired user/assistant messages and PENDING review in one SQLite transaction. Source message IDs make ingestion idempotent. This currently couples transcript storage to collection. Reviews and manual versions preserve originals; approved eligible records alone reach exports, with privacy/evaluation exclusion, deduplication, holdout, manifests/hashes and atomic directory publication. These are reused.

`integrations.py` owns fixed loopback addresses, read-only discovery, explicit connection/model selection and process-local consent. Runtime tests do inference only after approval. Hermes HTTP ingress refuses before reading its body. Runtime access does not expose native application history.

`training_control.py` owns configuration/model/job registries. `runtime_control.py` owns WSL probes, staging, worker/start/resume and deployment. Startup initializes these registries and some GET paths create defaults. Those side effects conflict with the new scope. Training APIs must be retired at the server boundary and historical reads must not initialize anything. The legacy implementations and historical artifacts need a staged retirement, not destructive deletion.

## KEEP / REMOVE / DEPRECATE

| Area | Decision | Reason and consequence |
|---|---|---|
| Chat Workspace, Settings → LM Studio/Ollama | KEEP/extend | Reuse approved fixed connectors; only NajdiLab-owned sessions; text-only raw model interaction. |
| Review queue, conversations, corrections, reviewed records | KEEP | Human approval and immutable source text are the dataset trust boundary. Saving a chat must not imply collection. |
| Manual SFT/direct/preference data, versions and lifecycle | KEEP | Existing human authoring/editing remains useful; no mass conversion or data removal. |
| Dataset health, validation, balancing, leakage/holdout, dedup | KEEP | Quality and evaluation separation remain required for external training. |
| Export center, version manifests/hashes, JSONL | KEEP/extend | Preserve export contracts; add a separate explicit Unsloth messages-format handoff without changing existing files. |
| Training setup/jobs UI, model download, WSL/worker/deploy controls | REMOVE from active product | External Unsloth owns training; stale deep links become an explanatory retirement view. |
| Training mutation APIs and executable trainer scripts | DEPRECATE with explicit refusal | Return structured 410; do not silently redirect or invoke external training. Legacy pure validation/read helpers and history remain for compatibility/research. |
| Training historical reads | DEPRECATE, read-only retention | Preserve job/attempt/log/metric data, no initializer or runtime probe on read. No deletion or migration rewrite. |
| Benchmark/adapter historical review views | DEPRECATE from navigation | Preserve archived evidence and existing read/data-review contracts; do not promote them as current workflow. |
| Applied migrations 001–004 | KEEP byte-for-byte | New additive chat tables only; no destructive rollback SQL. Proposed 005–007 in plans stay unapplied. |
| Hermes ingestion / original-app capture | KEEP BLOCKED / deferred | No safe native collection contract established; this change cannot close Issue #9. |
| Tool/RAG/agent/external-memory generation, GGUF execution | REMOVE from active scope | No generation of hidden prompts, tool calls, rewrites or model runtime management. Existing protected historical datasets remain intact. |
| Public Core candidate | KEEP isolated | Root feature does not silently expand its release or source manifest; new root files explicitly excluded from its policy. |

## Context and hardware findings

Model maximum context is not loaded context, free VRAM is not KV capacity, disk weight size is not loaded memory. No 64K or GPU-safe recommendation follows from GPU name alone. Official LM Studio SDK documents `apply_prompt_template`, `tokenize`, `get_context_length` and loaded model handles; these can provide an exact admission check without loading/changing a model. REST OpenAI compatibility alone lacks that preflight. Ollama exposes `/api/show`, `/api/ps` and `truncate:false` in current versions, but no verified public exact template-token-count preflight was established. Unknown metadata/counts must block sending, not fall back to characters/4 or an invented endpoint. Initial Ollama Chat admission therefore remains visibly BLOCKED pending a supported counting contract. Connectivity/tests remain available. This is an explicit incomplete requirement, not a claim of functional dual-engine Chat.

Hardware analysis is opt-in read-only local RAM and bounded NVIDIA query; unknown GPU/backend/KV/offload/overhead gives **no numeric safe recommendation**. Already loaded context is an engine ceiling, not a safe-memory promise. No allocation stress test or model load is authorized or run.

Sources consulted: [LM Studio tokenization](https://lmstudio.ai/docs/python/tokenization), [loaded handles](https://lmstudio.ai/docs/python/manage-models/list-loaded), [prediction config](https://lmstudio.ai/docs/typescript/api-reference/llm-prediction-config-input), [REST capabilities](https://lmstudio.ai/docs/developer/rest), [Ollama v0.40.13 API](https://github.com/ollama/ollama/blob/v0.40.13/api/types.go). SDK use is confined to existing loaded models; no `.model()`, load/unload/download or preset changes.

## Verification baseline

Windows Python 3.12 full baseline under restricted sockets: 92 failed / 289 passed / 24 skipped; failures predominantly WinError 10013. With local test networking allowed: **1 failed / 332 passed / 24 skipped / 68 subtests**, existing early-response client race (`test_legacy_ingest_requires_explicit_opt_in_and_does_not_bypass_browser_csrf`, WinError 10053). No product change was made to obtain either result. Private historical artifacts are absent by design. Final changes need fresh Windows/Linux CI, synthetic HTTP/engine/UI proof and separate owner acceptance. Neither baseline is a release pass.

## Destructive choices deferred

No user data, historical jobs/logs, old exports or migration is removed. Chat deletion is an explicit reversible archive with collection/eligibility disabled; retained copies/immutable exports are disclosed. Physical erasure and purging exported versions need a separately reviewed retention/migration decision. Running legacy training scripts becomes an explicit retirement error; their importable dataset-validation helpers remain. Rollback keeps the additive tables/data and restores reviewed source only; never restore an old DB over newer records or roll back before the Hermes security block.
