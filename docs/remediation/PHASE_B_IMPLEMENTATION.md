# Phase B implementation record — NajdiLab-first UI and operations

Status: IN_PROGRESS. Owner authorized starting Phase B on 2026-11-02 after Phase A PR #18 merged as `5de14f9` and main CI `41390294489` passed on Windows and Ubuntu.

## Product decision and boundaries

NajdiLab is the **single application experience** for local model chat, eventual in-app agents, conversation review, dataset preparation and export. Ollama and LM Studio remain optional **model runtimes**, not conversation-history sources. Users do not need to chat in either runtime's native UI or capture their native history. This supersedes the original native-app-collection premise of issue #9, **but does not prove or close that issue's original acceptance criteria**; issue triage must explicitly record the change of scope.

The UI removes the Hermes integration card and all Hermes actions. The existing blocked legacy Hermes ingress remains blocked in backend and packaged Core; removing the visible integration must not silently re-enable, weaken or bypass that protection. Nothing reads or modifies an installed Hermes instance, Gateway, WhatsApp Bridge, Baileys, model service or native conversation history.

Hugging Face Direct is a **future optional** download/run path, not an implemented provider or runtime. The Phase B card is descriptive only: no connect, search, model download, plugin install, server process, GPU allocation or data migration. Any eventual Phase C implementation requires explicit scope approval, gated model licenses, pinned revisions/digests, safe file paths, storage/VRAM checks, cancellable and integrity-verified downloads, approved execution backend, sandbox/permission boundary, and complete opt-in lifecycle tests. Do not execute arbitrary repository code or allow remote trust-code flags without explicit security design.

## Phase B implementation workstreams (31 original findings)

- Critical functional UX: UX-03 through UX-09, UX-12 through UX-17, UX-19, UX-20 and UX-27.
- Information architecture, complete bilingual Arabic RTL / English LTR UI (including dynamic content, persisted language selection, keyboard navigation, screen-reader labels, date/number formats and responsive mobile): UX-10, UX-11, UX-18 and UX-21 through UX-26.
- Operational security, retention, recovery and missing acceptance cases: QA-03 through QA-08.
- Cross-cutting product decision: integrated NajdiLab-owned chat instead of implicit collection from native apps; remove Hermes from settings only; keep backend refusal.
- Future-only concept: Hugging Face Direct placeholder (not added to the runtime registry in Phase B).

All original findings retain their identifiers and acceptance requirements. The remaining workstreams are **not** marked fixed by this first UI change.

## Initial changes implemented in this branch

1. Settings integration controller displays **only** `lmstudio` and `ollama` model-runtime connectors. It filters the internal selectable snapshot as well as rendered cards; hidden/legacy source IDs cannot be dispatched by a UI event.
2. Settings heading and explanatory text describe NajdiLab-owned chat, avoiding claims of native-app collection.
3. Static, visibly unavailable Hugging Face Direct preview, with no runtime or download action.
4. Node controller regression test verifies legacy source exclusion and refusal to dispatch a hidden connector.
5. No backend Hermes/config/service changes. No migration. No local device changes.

## Quality gates for one consolidated Phase B PR

The Phase B branch is the sole implementation branch and its PR stays a **draft** until **all 31 findings** are implemented, tested and independently reviewed. Do not open smaller phase PRs and do not merge automatically.

Every feature must include regression tests and documentation in the same commits. Run full Python and Node suites, Windows/Ubuntu GitHub Actions, browser acceptance (Arabic/English, desktop/mobile, keyboard and consent flow) and packaged Core checks. Do not substitute a green CI status for acceptance evidence of untested private historical fixtures or the user's Windows environment.

Blocked/unavailable private artifacts remain explicitly unverified. Do not fabricate their test passes. Maintain reviewed backup/restore evidence and rollback instructions; source-only UI changes in this initial commit have no schema rollback.

## Owner gates

- Phase A main: merged and green; no local pull is authorized by this Phase B start.
- Phase B: branch/PR development authorized. No merge until a **separate owner decision** on the completed PR.
- Phase C: not started or authorized. Real GPU/model download tests remain blocked until explicit permission.
