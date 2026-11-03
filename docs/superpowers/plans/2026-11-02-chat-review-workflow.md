# Chat review workflow implementation plan

**Goal:** Implement the owner-authorized 2026-11-02 Chat fixes on an isolated branch based on integration/pr19-pr20-local-20261102 at 634e7a5414aa7e620f674f420adeda2d97f02c43, then safely update the persistent Windows installation.

**Architecture:** Extend existing Chat controller, response validation, consent metadata and SFT export. Reuse existing messages/masks and seven migrations; no new schema or migration execution is planned. Keep raw model content unchanged and reasoning discarded. Display formatting belongs exclusively in the UI.

**Spec:** Owner's detailed execution request in this chat, continuing review conversation 6ae8b263-58fc-83eb-95bc-b9722af35a40. It supplies execution authorization and overrides additional design-confirmation gates.

**Constraints:** Never modify main or merge PR19/20; never send private data to GitHub/tests; synthetic isolated DBs only; collection OFF by default/restart; no retrospective capture or training approval. No user-data migrations. Source-only upgrade only after backup integrity and unchanged migration registry verified; retain rollback source and launcher.

## Tasks and proof
- [x] Trace/reproduce Ollama failure with synthetic prompts on existing authorized runtime. Add regression tests before changing response checks. Retain strict unchanged content, prompt identity/count, completion, model pinning, reserve and context checks; report the exact failed predicate using content-free constant diagnostics.
- [x] Add new-conversation presets 4096/1024, 8192/2048, gated 16384/3072, Advanced manual input and verified ceiling display. Add 4096 to existing hardware estimates and expose budget_ceiling. Test stale evidence, model limit, unknown VRAM and no saved-session mutation.
- [x] Add Enter/Shift+Enter with IME/repeat/blank/busy guards, preserve failed/newer drafts; safe presentation-only Markdown; bilingual user messages. Test with Node and synthetic Chromium fixture.
- [x] Audit consent-segment-to-review-to-SFT messages/target masks. Mark incomplete pre-consent prefixes and refuse their training promotion/export, never import earlier roles. Preserve single-turn/multi-turn without forced ratios. Prove opt-in/restart/privacy/archival invariants on temporary DBs; no schema changes.
- [x] Run Windows Python/JS/Chromium and Core checks and available Ubuntu equivalents. Record actual skips separately from passes. Independent whole-diff review and targeted follow-up proof.
- [ ] Publish isolated fix branch/PR or comment on PR20 with actual evidence. Keep draft and no hosted-green claim.
- [ ] Inspect launcher/process identity, stop only owned idle service, verified private SQLite+files backup, source/migration comparison, fast-forward source only, update launcher pin, read-only data preflight, restart and read-only health/UI smoke. Compare logical DB digest before/after (allow only startup receipt behavior if documented); rollback source on failed health. Never restore DB automatically.

## Review focus
1. A different model/selection invalidates hardware evidence, and saved conversation context is immutable.
2. Final prompt count differs despite a successful Ollama stop: refuse with precise localized diagnostic, never weaken validation without evidence.
3. Reasoning-only/length/tool replies never enter history or review; raw Markdown is preserved in storage.
4. Consent starts mid-conversation or is revoked mid-flight: no previous roles are captured; incomplete prefix cannot become SFT.
5. User writes during inference or request fails: draft survives; Enter never sends during composition or busy state.

## Execution evidence ledger
- Source checkout is clean at expected SHA. Isolated clone `najdilab-chat-fixes`, branch `fix/chat-review-workflow-20261102`.
- Initial restricted Windows baseline: 53 passed,43 failed due denied loopback transport, not product assertion regressions; unrestricted rerun pending.
- Root owns engine validation, hardware, release/upgrade docs; delegated independent frontend and dataset scopes under dispatching-parallel-agents.

- Final source verification: Windows697/32skip; Ubuntu696/33skip; Node37 each; Chromium35 plus main/enhancements; Core Windows75/3skip and Ubuntu78. Details in ../../chat-review-workflow-results.md.
- Ruling: Use existing metadata rather than schema changes; conservatively quarantine unproven historical prefixes. No user-data mutation or migration.
