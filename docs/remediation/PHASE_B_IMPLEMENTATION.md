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

## Second implementation increment — functional UX (2026-11-02)

The following **eight finding IDs** have code changes but remain `IMPLEMENTED_PENDING_VERIFICATION` until all applicable CI/browser and owner gates pass. No finding is represented as fully accepted merely because code was pushed:

- UX-04: explicit per-completed-pair collection state in NajdiLab's own Chat UI, based on persisted `turn.collected`. A collected pair is **not** automatically training-approved; there is no imported native-app capture.
- UX-08: a COMPLETED Send clears the composer only if its content still equals the submitted text. Newer user typing, failures and context rollover retain the draft. Unit and delayed synthetic browser tests added.
- UX-06: the export readiness panel shows **every** returned blocking finding with escaped identifiers and reasons, as a persistent list instead of only the first three.
- UX-14: Add Data subtab event binding is limited to Add Data controls; the manual edit dialog's own tabs remain independent.
- UX-15: no-turn and blank-turn manual SFT submission is rejected visibly before API dispatch; no dereference of a missing textarea.
- UX-16: manual item PATCH has a disabled/pending Save button, persistent failure message, retry preserving form edits, and a distinct message for a post-commit list-refresh error. Browser failure/retry proof remains to be built.
- UX-17: the exclusion reason is labeled as required; existing backend/frontend rejection of empty reasons is preserved.
- UX-12: Unsloth handoff now offers a catalogue of existing readable **Frozen** versions only; the action is disabled without a valid choice. No free-text version input or auto-export.

UX-03 remains open: changing a label to clarify that dataset eligibility differs from human approval is not enough to prove the full review-flow semantics. No blanket claim is made on UX-03, UX-05, UX-07, UX-09, or the remaining UI/a11y/QA findings.

### Test and operational limits

- Regression additions: `tests/chat-ui.test.cjs`, `tests/chat-browser.cjs`, delayed **synthetic-only** fixture in `tests/chat_browser_fixture.py`. No real user prompts, models, runtimes or installations touched.
- Hosted CI is the acceptance source; intermediate commits are not the final head and their results do not establish final acceptance. The browser test initially timed out during initial provider discovery on intermediate commits; final-head diagnostics and rerun evidence must be checked before concluding PASS.
- Existing Core candidate remains separate from the full product; source-policy exclusions are preserved and not weakened.
- No migration, physical data wipe, live API operation, GPU load, model download, Hermes/Gateway change, local pull or merge.

## Third implementation increment — review-draft integrity and UI truthfulness (2026-11-02)

Five further original findings are implemented in source **PENDING final acceptance**, and remain separate from the still-open findings:

- **UX-07:** Snapshots the current review's editable fields in memory (correction, status, notes, reviewer identity, exclusion reason, tags, eligibility/restriction flags). Navigation to another view and queue refresh require explicit discard consent when changed. The beforeunload guard protects against accidental tab closure; it does not store the draft to disk or submit it. Browser acceptance checks cancel and accept and restoration from trusted server data.
- **UX-09:** The Chat panel explicitly labels selectors as *new-conversation setup*. Active/saved conversation identity shows the pinned provider, model, context budget, reserve and status without pretending that changing the new-conversation selectors mutates the saved session. Sending is disabled when that session's original runtime/model is not selected; no automatic model change or loading.
- **UX-11:** Dashboard no longer advertises static readiness. Counts are labeled as API snapshots and export gate status is deferred to the actual Export center readiness endpoint.
- **UX-24:** Fixed specificity regression that kept the sidebar column at 240px when only the contents visually collapsed. Explicit 76px collapsed grid wins on desktop; small-screen breakpoint preserves single-column shell. Synthetic Chromium test measures computed width.
- **UX-26:** Removed fixed 127.0.0.1:8770 UI badge; it now displays the browser's actual host/port, without using it as an access-control input. Replaced the hardcoded SQLite “Passed” status with a bounded live /api/v1/health *service reachable* check that explicitly does **not** certify SQLite integrity, migration state or backup availability.

The newly added tests were written for disposable hosted fixtures only; initial source acceptance is **not** claimed for the latest head until both Windows and Ubuntu Source checks and Core candidate workflows are green. UX-07 does not yet cover every editable form/dialog in the product; full unsaved-change acceptance remains open for broader Phase B QA.

No migrations, third-party-service edits, local PC access or destructive actions. Rollback is the feature branch diff only; the backend Hermes safety block stays active.

## Fourth implementation increment — dataset identity, Phase39 and presentation (2026-11-02)

Five more original findings now have source changes and dedicated synthetic acceptance tests. They are **IMPLEMENTED_PENDING_VERIFICATION**, not closed:

- **UX-13**: Opening Dataset Versions forces a fresh version catalog. The UI will not select a stale/unreadable version from an earlier page visit. This does not rebuild a missing registry or mutate dataset files.
- **UX-18**: The Phase39 UI derives row count, indexes, navigation bounds and prior decision from the API payload rather than a seven-row UI assumption. On an empty queue, it renders an empty state. Missing contamination or loss-mask status is **UNVERIFIED**, never fabricated PASS. A synthetic Node VM test checks three items, zero items and persistent failed-save retry. Backend's historical seven-record private review contract remains unchanged and private legacy files are not fabricated.
- **UX-23**: CSS constrains the Add Data tab strip, review controls, panel grids and filter widths at a 390px viewport. Wide manual tables retain intentional **internal** horizontal scrolling. Hosted Chromium viewport checks added; additional platform/font and 200% zoom checks still required.
- **UX-25**: Dark-mode overrides correct contrast for Phase38 assistant messages, summary badges, labels, safety status and metadata. Hosted Chromium tests compute actual foreground/background contrast (>=4.5:1) on representative elements. This is not yet a complete all-screen audit.
- **UX-27**: Evaluation screen displays the exact requested dataset-version name beside its returned integrity report and ignores an older pending response if the selection has since changed. Concurrent synthetic Node test added; private evaluation data not accessed.

New acceptance sources: \`tests/phase39-ui.test.cjs\`, \`tests/dataset-identity-ui.test.cjs\`, and extended \`tests/chat-browser.cjs\`. Both new test files are explicitly classified as full-product-only exclusions in the Core source policy. We must verify the **same final branch HEAD** with both Windows and Ubuntu Source checks and packaged Core candidate; no success claim until those runs finish green.

Rollback is a code-only branch revert. There is no schema migration, model download, GPU load, local Windows modification, or third-party app configuration change in this increment.

## Fifth implementation increment — quality decision and recoverable errors (2026-11-02)

- **UX-03:** The review screen visibly distinguishes the human review decision (Approve) from the separately selected dataset export eligibility checkbox, and labels its assistive help via `aria-describedby`. Existing server-side privacy, fact-check and holdout gates still take precedence. Browser assertions verify text/help and prove that an approved restricted sample remains ineligible; no data is automatically approved for training.
- **UX-19:** General UI error notifications no longer silently disappear after 2.8 seconds; they use `role="alert"`, assertive announcement and an explicit accessible Dismiss error button. Informational/success notifications continue to expire automatically. The hosted Chat browser test demonstrates persistence after 3.1 seconds and dismissal, using synthetic no-turn validation only. Persistent errors must still be audited screen-by-screen for contextual messaging and recoverable state.

Both findings remain **IMPLEMENTED_PENDING_VERIFICATION** until final same-SHA Windows/Ubuntu CI, complete Arabic/English UI localization and full accessibility/zoom acceptance. Existing Node synthetic-DOM tests were updated to emulate `createElement`, `append`, and ARIA setters rather than hiding browser behavior behind a no-op production shim.

**Phase B tally:** 20 of the 31 original finding IDs have code changes pending full verification; 11 findings remain open. None is marked finally fixed by this increment. No native application or user's local files were touched.
