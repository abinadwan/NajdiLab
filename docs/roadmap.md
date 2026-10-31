# NajdiLab roadmap — dataset-first scope

This roadmap supersedes training execution priorities in older phase documents. It does not rewrite historical decisions or authorize an installed update.

## Product boundary

**Local Chat → Review/correct → Quality/dedup → Dataset version → external Unsloth handoff.** LM Studio/Ollama remain externally managed runtimes. No local GGUF execution, trainer, model download/merge/release, WSL worker, RAG, tools or external memory is part of NajdiLab's active workflow. Hermes remains BLOCKED. Native application capture remains a separate unresolved Issue #9; this workspace is not its replacement acceptance test.

## Phase 1 — scope and non-destructive retirement

- Read-only architecture/data/migration/roadmap audit and KEEP/REMOVE/DEPRECATE rationale: [audit](scope-audit-2026-10-31.md).
- Independent feature branch from `d992b0a`, without PR #10 changes.
- Remove Training setup/jobs/model-download/WSL/deploy UI; training namespace writes return structured 410 before bodies are read. Keep read-only job/attempt/log/metric APIs and legacy dataset/quality read contracts.
- Retire executable trainer, benchmark, adapter/GGUF/Ollama deployment scripts before dependency imports; preserve importable historical validation helpers and records.
- No existing data or migrations 001–004 removed. Migration 005 adds only Chat tables and archive eligibility guard.

## Phase 2 — raw Chat and collection

- Text-only saved Chat sessions, immutable provider/model per session, user budget + reply reserve, exact preflight, complete unchanged history; context-limit rollover never replays the rejected draft.
- LM Studio implementation uses **pinned optional SDK 1.5.0**, only existing loaded instances. Template, tokens, context and inference use an instance-reference-bound protocol. The pinned SDK's session helpers are private compatibility surfaces; unknown SDK versions fail closed. Synthetic SDK/WebSocket proof is not real-engine acceptance.
- **Ollama sending implemented with per-turn proof** ([method](chat-workspace.md#ollama-admission)): `truncate`/`shift` off, a live refusal check, an exact one-token count, a `/api/ps` clamp check and digest binding. Verified on the real 0.40.13 binary with a synthetic model only. No character-ratio estimates or invented token API. It relies on fields absent from Ollama's REST reference page, so the refusal check stays on every turn and blocks if behavior changes.
- Separate collection consent OFF on creation/restart; continuously consented completed pairs form review segments. Earlier OFF turns stay only in saved Chat. A segment that begins mid-chat is labeled “earlier context excluded”; review/export must not claim it is the entire original inference history.
- Request receipts, single database owner, stop/error/restart/revoke/re-enable/stale-tab/transaction/archive tests.
- Read-only RAM/NVIDIA snapshot plus selected-model evidence on explicit click. Model maximum, runtime context, measured use and estimated feasibility stay separate; any suggested context is labeled unverified, never safe. No stress tests run or implied.

## Phase 3 — reviewed external handoff

- Preserve existing manual edits, quality/dedup/balance, holdout separation, immutable versions and exports.
- Block complete export windows containing known private/sensitive/excluded/deleted/evaluation context; do not trim them silently. Privacy recheck and complete source snapshot share a SQLite write transaction.
- New versions attest `no_flagged_or_excluded_context_v1`. Older exports remain intact and usable through their existing interfaces; the new Unsloth handoff asks for a fresh version when privacy attestation is absent.
- Handoff JSONL uses conversational `prompt`/`completion`, with exactly the approved final assistant as completion. External Unsloth/TRL needs `completion_only_loss=True`, `packing=False` and rejection of overlength records. No trainer is invoked. Hash and snapshot every quality input, including evaluation holdout, then atomically publish JSONL/provenance/manifest.

## Review and future gates

Delivery evidence is in [results](dataset-chat-results.md). Before merge: green final-head Windows/Linux source and candidate CI, synthetic security/transport/UI proof, reviewed diff and rollback. **Owner approval is still required to merge or update the installed app.** After that, separate owner-operated synthetic Windows acceptance verifies actual engine versions, model template/count agreement, no hidden runtime presets/plugins, memory behavior and cancellation. None has been performed by this change.

Remaining work: owner [Windows acceptance](chat-windows-acceptance.md) of Ollama with an installed model and of LM Studio, optional owner-approved staged allocation experiments, separately reviewed physical erasure/export retention, and eventual deletion of deprecated research implementations after compatibility review. Do not mark these complete based on synthetic checks.
