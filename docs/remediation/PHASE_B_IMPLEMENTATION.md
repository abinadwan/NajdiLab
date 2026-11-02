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

## Sixth increment — CI repair and Actions cost control (2026-11-02)

**Finding from CI history:** `Source checks` had failed on every commit since the UX-07 browser test was added (for example run `41400132842` on `841f42e`: 4 passed, 7 failed in `review-restrictions-browser.cjs`). Earlier increments recorded the tests as added but not that they were failing. Reproduced locally; the failures were in the test, not the product:

1. **UX-07 test assumption.** After discarding a draft, the test expected an empty notes field. The fixture's review has a saved note (`Saved synthetic note`, present since Phase 0), and the UI correctly restores it. The test now asserts the field equals the server-saved value and differs from the abandoned draft.
2. **Unhandled guard dialogs.** Two earlier steps intentionally leave an unsaved draft. The next `page.reload()` raised `beforeunload` and the next navigation raised the UX-07 `confirm`; with no handler Chromium blocked, and every later step hit protocol timeouts. The test now asserts each prompt (`beforeunload`; the exact confirm text) appears once, then accepts it explicitly.
3. **UX-19 product defect found while fixing step 8.** The dismiss glyph `×` was part of the error toast's text, so `role="alert"` announced "message ×" to screen readers. The message now lives in `.toast-message` and the glyph is `aria-hidden`; the button keeps `aria-label="Dismiss error"`. The test asserts the message, role and label.

**Missing CI wiring — and both unwired tests were broken.** `tests/phase39-ui.test.cjs` and `tests/dataset-identity-ui.test.cjs` (UX-18, UX-13, UX-27 acceptance) were documented as acceptance but never run by CI, and both failed on pushed HEAD `36a38cf`:

- `phase39-ui`: its code-slicing end marker `ensureDatasetVersions(){` stopped existing when UX-13 added the `force` parameter, so the file failed before any test ran. Marker corrected; 3/3 pass.
- `dataset-identity-ui` (UX-27): the test assumed one microtask tick was enough for the first request to be sent. The controller reads the selection only after the catalog check, so both calls requested `gold-v2` and the test crashed. The product guard was correct. The test now waits until each request is actually issued, and a second case covers the old response arriving first while the new one is pending. Removing the guard from `app.js` makes both UX-27 tests fail (mutation check).

They now run in `Source checks`, and `tests/test_ci_workflows.py` fails if any `tests/*.test.cjs` is not wired. A local shell loop of mine first reported these two as passing because `$?` was read after a `$(basename …)` substitution; the counts below come from runs that capture the exit status first.

**Actions consumption.** At hand-over 28 runs were queued or in progress for superseded commits. Both heavy workflows now: cancel superseded runs per PR/ref (`concurrency`), start no heavy job for draft-PR pushes, support manual `workflow_dispatch` for a chosen HEAD, and time out (30 minutes per job, 10 per Chromium step). Policy and how to run checks on a draft: [developer setup](../developer-setup.md#continuous-integration-policy). Risk: a draft PR shows skipped checks; skipped is not passed, so the final HEAD needs a manual or ready-for-review run before any merge decision. Limitation: GitHub enables manual dispatch only when the trigger exists on `main`, so for PR #19 the available verification run is marking it Ready for review (one run), then back to draft. The hosted result for `36a38cf` (runs `41401116909`/`41401116929`): candidate green on both systems; Source checks red on both, failing subtests 1 and 7–11 of `review-restrictions-browser.cjs`, matching the local reproduction. Rollback: revert the two workflow files.

**Local evidence (Linux container, synthetic data only), on the uncommitted working tree:** Python `pytest -q tests` 556 passed, 37 skipped (private-artifact prerequisites); new CI guard 7 passed; Node unit tests 4 files, 18 tests, all pass in one `node --test` invocation (the CI form); `chat-browser.cjs` pass; `review-restrictions-browser.cjs` 11/11 subtests; Core builder tests, build, verify, candidate 78 tests, harness and browser pass. **Windows not verified** (no hosted run yet). Nothing was pushed; findings keep their status.

## Seventh increment — UX-20 record paging (2026-11-02, local only, not pushed)

**Problem.** Four lists cut data silently: conversations had no limit at all (every row on every request), reviewed records stopped at 500, manual data at 500, saved chat sessions at 200. Nothing told the user records were hidden.

**Design.**
- `service.page_request` reads `limit` (1–500, default 100) and `offset`; invalid values raise `ValidationError` (HTTP 400). `service.page_info` returns `{total, limit, offset, returned, has_more, max_limit}`.
- New `reviewed_page` and `conversations_page`; `list_manual_data` pages its results; saved chat sessions are paged by the new read-only `app/chat_history.py`. `app/chat_workspace.py` is hash-pinned as a protected Chat security implementation (`tests/test_dataset_boundary.py`), so it is deliberately left unchanged rather than re-pinned. Totals use the same filter as the page query. Ordering gains an id tie-breaker so equal timestamps cannot repeat or skip rows across pages.
- The Core profile still calls `list_reviewed` / `list_conversations`, which keep their plain-list contracts.
- UI: one shared pager (`listPage`, `renderPager`, `correctedPage`) for conversations, reviewed and manual data. Filters reset to page 1; if deletions leave the current page empty, the UI moves to the last real page. "Select all" now says it selects the records on this page. Saved chat sessions show "N of M loaded" and a Load more button.

**Safety change found on the way.** Browser fixtures bound the database by redirecting individual server functions; any route they did not redirect silently fell back to `data/najdilab.db`. Both fixtures now bind the new paged functions, and `tests/fixture_safety.py` makes any unredirected database access raise instead.

**Tests (local, Linux, synthetic):** `tests/test_ux20_pagination.py` 23 passed (bounds, rejection, exactly-once coverage across pages, filters, Core contracts, empty past-the-end page, archived sessions excluded, HTTP 400 and metadata on all four routes); `tests/pagination-ui.test.cjs` 5 passed (wired into Source checks); `review-restrictions-browser.cjs` 11/11 including a pager assertion; `chat-browser.cjs` pass.

**Limits and risks.** Offset paging is not a snapshot: records added or removed between page loads can shift later pages. Pager labels are English until UX-21. Rollback is a code revert; no schema change.

## Eighth increment — UX-21 Arabic and English interface (2026-11-02, local only, not pushed)

**Decision.** English stays the source language of markup and scripts; Arabic is applied at runtime from a catalog. Rewriting ~1,000 strings into keyed lookups across `index.html`, `app.js`, `chat.js` and `integrations.js` would have been a large, regression-prone rewrite; a catalog-driven DOM localizer covers static markup, dynamic templates, toasts and late-rendered views with one mechanism, and leaves English almost unchanged: the only English changes are readable labels instead of raw values (`Yes`/`No` instead of `YES`/`NO`, origin labels such as `Manual` instead of `manual`, "Select all records on this page"). All English browser suites still pass. Design, rules and how to add text: [localization](../localization.md).

**Changes.** `static/localization.js` (engine; same `NajdiI18n` API plus `t`, `setLanguage`, `language`), `static/i18n-ar.js` (catalog), `static/i18n.css` (selector and RTL rules), language selectors in the top bar and Settings, `<time datetime>` dates, `confirm()` texts through `t()`, identifiers isolated with `bdi`/`translate="no"` in version lists, file lists, chat status lines, model menus and data tables. Balancer warnings and recommendations are server text, so they moved out of `dir="auto"` and are translated; raw source names stay isolated.

**Defects found and fixed during this work.**
- My first version of `fmtDate` returned markup that `integrations.js` then escaped, printing `<time …>` as text in Settings. Fixed before any push; the Chromium scan caught it.
- Adding the language selector overflowed the top bar at 390px in **both** languages (scroll width 624 / 550). Fixed with wrapping and visually hidden labels (selects keep accessible names); the scan and the UX-23 width check both cover it.
- `theme-init.js`/`theme.js` called `localStorage` unguarded, so a browser that blocks storage threw at startup. Guarded; covered by a blocked-storage test.
- The chat browser fixture bound only some service functions to its disposable database and read the project's real `exports/`. It now binds every service function and uses a synthetic dataset catalog (`tests/synthetic_datasets.py`); `tests/fixture_safety.py` makes any remaining default-database access fail.

**Tests (local, Linux, Chromium, synthetic only).** `tests/i18n-catalog.test.cjs` 5/5; `tests/i18n-browser.cjs` 9/9; English suites unchanged: `chat-browser.cjs` pass, `review-restrictions-browser.cjs` 11/11; Python 587 passed, 37 skipped; Core candidate build/verify, 78 tests, harness and browser pass.

**Not verified.** Real screen readers, Firefox/Safari, 200% zoom in Arabic (QA-05), second-speaker review of the Arabic text. Rollback: code revert; no data or schema change.

## Ninth increment — UX-10 navigation grouping (2026-11-02, local only, not pushed)

**Audit (read-only, before changes).** 15 destinations in 5 groups; "Dataset" alone held 9, mixing review, data entry and dataset preparation. Group labels were `span`s not tied to their items. Icon glyphs (◫ ◈ ⌁) were part of each button's accessible name. No `aria-current`. Collapsed sidebar (UX-24): `.nav-label{display:none}`, but 10 of 15 items had no `.nav-label`, so their text stayed visible; the other 5 lost their accessible name. The sidebar `aside` and the `nav` had the same accessible name.

**Change.** Same 15 destinations and routes, regrouped in workflow order — Overview · Chat · Review (queue, conversations, reviewed) · Data entry (add, manual data) · Datasets (records, health, balancer, versions, evaluation sets) · Export · Administration (analytics, settings). Each group is `role="group"` labelled by its heading; icons are `aria-hidden`; every item has a `.nav-label` and a matching `title`; `switchView` maintains `aria-current="page"`; collapsed labels are visually hidden, not removed. "Administration" replaces "System" because the catalog already uses "System" for the theme option.

**Also fixed.** `app.js` used `localStorage` unguarded for the sidebar state, so with storage blocked `init()` stopped before binding events and the interface did not respond. My first blocked-storage test passed anyway because the dashboard is active in the static markup; it now proves navigation works and no startup error is shown.

**Tests.** `tests/test_ux10_navigation.py` 5/5; `chat-browser.cjs`, `review-restrictions-browser.cjs` 11/11 and `i18n-browser.cjs` 9/9 pass after the change. Rollback: markup/CSS revert.

## Tenth increment — UX-22 and QA-05 accessibility and zoom (2026-11-02, local only, not pushed)

**Method.** Measured, not inspected by eye: Chromium's accessibility tree (CDP `Accessibility.getFullAXTree`, the source screen readers read) for every focusable control in all 15 views, a focus-indicator check per control, and page scroll width per view at several widths.

**Findings and fixes.**
- 9 filter and sort menus had no accessible name (the first option only looked like a label); search fields relied on `placeholder`. All named; Arabic names added.
- No skip link; added, with the main region named by the page title.
- Review shortcuts: single keys fired while a modal dialog was open — "4" approved the review behind the delete confirmation — and could not be turned off (WCAG 2.1.4). Now off by default, opt-in in Settings, never active behind a dialog or while focus is in a field, button or link, and shown on screen. A stray key press can no longer decide a review.
- The shortcut hint was a `<kbd>`, which the localizer skips; it is now a styled `span` so it is translated.
- Reflow at 320 px (400% zoom) overflowed on Analytics (table), Reviewed (310 px grid minimum) and Settings (wide selects). Fixed; 640 px already passed.
- Focus indicators and image alternatives already passed everywhere.

**Tests.** `tests/a11y-browser.cjs` 11/11 subtests (wired into Source checks with a step timeout). Full local run after the change: Python 593 passed, 37 skipped; Node 28/28; `chat-browser.cjs`, `review-restrictions-browser.cjs` 11/11, `i18n-browser.cjs` 9/9; Core candidate build/verify, 78 tests, harness and browser pass.

**Blocked / not verified.** Firefox and WebKit are not installed in this environment (only Chromium), so other-browser acceptance is BLOCKED here. Screen-reader speech output is NOT VERIFIED. See `docs/accessibility.md`.

## Eleventh increment — UX-05 continuity and complete content (2026-11-02, local only, not pushed)

**Definition used.** The roadmap gives only the title and "nothing decisive in source"; no fuller text was found in the repository or PR #19. Read as two requirements: the reviewer sees the conversation continuously (every earlier turn, in order, up to the response under review), and permitted content is never cut off without a way to read it.

**Findings.** Continuity was already correct at the data layer and on the review screen. Two lists truncated with no way to see the rest: Reviewed cards (original and saved correction at 220 characters) and Dataset records (preview at 180). The manual-data table preview already had a full View dialog.

**Change.** `fullText()` in `app.js` keeps the preview and adds `<details>`/`<summary>` with the exact stored text (`dir="auto"`, never translated). Dataset records show translated origin/language labels and isolate domain/model identifiers. The reviewer-identity menu no longer widens the page at 320 px (`.view select{max-width:100%}`).

**Tests.** UX-05 subtest in `tests/a11y-browser.cjs`; whole file 12/12 subtests.

## Twelfth increment — operational QA (QA-03, QA-04, QA-06, QA-07, QA-08) (2026-11-02, local only, not pushed)

- **QA-03 — BLOCKED.** Exactly 22 skips declare private historical prerequisites; they cannot run here and are not recreated. Inventory and unblock steps are in the roadmap row.
- **QA-04.** Symlink and junction refusal now has deterministic tests that do not need the right to create links (`tests/test_qa04_symlink_unavailable.py`, 12; junction branch mutation-checked). One of my own tests first depended on every repository file being classified for the source candidate; it is now isolated so it tests only the symlink refusal.
- **QA-06 — evidence, not proof.** `GET /api/v1/hermes-hook/refusals` reports refused deliveries to the blocked hook (count and last time, nothing stored from requests). Not added to Settings, which no longer shows Hermes. `app/integrations.py` is hash-pinned and was not changed. The owner's verification procedure is in `docs/hermes-integration.md`; external disconnect stays NOT VERIFIED.
- **QA-07.** Optional timestamped signatures with a 300-second window and replay refusal; existing senders unaffected; `NAJDILAB_REQUIRE_FRESH_SIGNATURE=1` enforces it. Documented in `SECURITY.md`, `docs/configuration.md`, `docs/api-reference.md`. `app/http_security.py` is Core-selected and was re-pinned; Core suites pass. Access-policy impact: none by default; enforcement is an explicit operator choice.
- **QA-08.** Retention semantics proven end to end and documented in `docs/data-retention.md`, including that deleted text remains in every new export's `full_archive.json`. Physical erasure is BLOCKED pending an owner decision.

**Phase B tally (2026-11-02, from the roadmap rows):** 30 of 31 findings are IMPLEMENTED_PENDING_VERIFICATION and 1 is BLOCKED (QA-03). None is PASS: every finding still needs a hosted Windows/Ubuntu run on the final HEAD and the owner's review. Within the 30, these parts remain open: QA-05 other browsers (BLOCKED here, only Chromium installed) and real screen readers (NOT VERIFIED); QA-06 external sender disconnect (NOT VERIFIED, owner procedure); QA-08 physical erasure (BLOCKED, owner decision); UX-21 second-speaker review of the Arabic text.

