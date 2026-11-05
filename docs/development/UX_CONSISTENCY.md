# UX consistency implementation and verification

Date 2026-11-05. Source branch `update-project`, source SHA `1abf2d71db284a2becf2d89703feaaaffbace124`. Development continues locally on `update-v2.3.1`. Application version remains V2.2.0.

## Behavior and ownership

The existing Prepare data page already owns selection, privacy/eligibility checks, fingerprint-bound creation, frozen Gold and exports. The existing route map owns direct URLs. Browser preferences already use guarded localStorage access. The existing Arabic catalog and MutationObserver own interface translation while skipping stored user content and technical identifiers.

Implementation reuses these owners. Dashboard presents the three preparation stages and a primary Prepare data action. Its frozen version count and recent versions use the same dataset-version catalog as My versions, filtered to Frozen. This also covers versions absent from the legacy export registry. Human review remains independent. Settings owns the Advanced Mode checkbox and six specialist destinations. A root class controls specialist navigation visibility, including diagnostics added asynchronously to version cards. Strict stored value `1` enables the preference. Unavailable storage leaves the current session usable. Direct URLs work in both modes.

The implementation choice to place all six tools at the top of Settings keeps them together with their preference. The per-version full-diagnostics link follows the same preference. Readiness summaries and export downloads stay available in ordinary My versions.

Health descriptions and health/balance errors are interface text. Their former `dir="auto"` marker bypassed localization. Removing that marker only from these interface explanations lets the existing catalog translate them. User text, identifiers, files, code and SHA-256 retain their existing skipped containers.

## Implementation sequence

1. Verify remote HEAD, clean checkout and absence of the requested remote branch. Create the requested local branch from that HEAD.
2. Add five failing regression contracts for Dashboard navigation, specialist tool placement, storage behavior, localizable explanations and honest counts. Run them before changing product code.
3. Update existing markup, preference initialization, CSS visibility and catalog entries. Update affected existing tests.
4. Extend the existing synthetic journey and localization browser suites. Check actual navigation, reload persistence, all six deep links, downloads, keyboard operation and 36 responsive/theme/language screen combinations.
5. Run Node, Python, browser and documentation checks, inspect screenshots and review the diff. Record final outcomes before the local commit.

## Verification

All data-writing tests use synthetic data in temporary databases and directories. Browser tests spawn the existing disposable fixture with random loopback ports and fake runtimes. Real Ollama and llama-server opt-in tests are disabled. Browser tooling is installed only in ignored `.test-tmp/browser-tools`. Tests use headless Chrome and never attach to an existing browser session.

Baseline selected Python checks passed 62 tests. Baseline Node catalog passed 7 tests and baseline bilingual browser passed 10 tests. All five initial regression contracts failed on the source behavior, then passed with the implementation. A sixth regression reproduced the legacy export registry omitting cataloged frozen versions. It failed before Dashboard switched to the shared catalog and passed afterward.

### Final checks

| Check | PASS | FAIL | SKIPPED |
| --- | ---: | ---: | ---: |
| `python -m pytest -q tests -rs` | 945 | 0 | 57 |
| Python subtests, reported separately by pytest | 59 | 0 | 0 |
| `node --test tests/*.test.cjs` | 61 | 0 | 0 |
| `node --test tests/data-journey-browser.cjs tests/i18n-browser.cjs` | 21 | 0 | 0 |
| `node --test tests/a11y-browser.cjs` | 13 | 0 | 0 |
| `node tests/chat-browser.cjs`, standalone acceptance script | 1 | 0 | 0 |

Python skips comprise 22 private historical artifact cases, 18 missing optional LM Studio SDK cases, 13 opt-in real-engine cases, 3 Windows symlink cases and 1 external Unsloth Studio Python case. These are explicitly excluded from PASS.

Three manual verification areas are NOT TESTED. Screen-reader announcements require manual assistive-technology testing, other browser engines require their own runs, and independent Arabic wording review requires another language reviewer.

The journey covers 36 screenshots from Dashboard, Settings and My versions in English/Arabic, light/dark and 320/390/1440px. Screenshots were inspected for representative desktop/mobile and RTL/LTR states. Browser assertions verify reflow, empty-value artifacts, persistent preferences, all six specialist links and disabled-mode deep links. The synthetic Gold journey proves privacy refusal, filter selection preservation, check invalidation after selection changes, explicit confirmation, frozen creation and successful export downloads. Its page-error and failed-API-request collections are empty. Existing Python coverage checks preview/build agreement, privacy, train/evaluation leakage, loss masks and manifest/hash gates.

The final independent code review found no actionable regression. It identified export-based Dashboard counts as pre-existing behavior, which prompted the additional catalog regression and scoped correction. Backend enforcement is exercised by the test suites. Non-Chromium rendering and manual screen-reader behavior remain in the limits above.

`python scripts/check_docs.py`, JavaScript syntax checks and `git diff --check` also pass. Verification used Windows, Python 3.12.10, Node 26.10.0, headless Chrome and the repository's recorded `puppeteer-core@25.16.0` test dependency. Logs and synthetic screenshots are in ignored `.test-tmp/`.

### File inventory

| File | Purpose |
| --- | --- |
| `static/index.html` | Dashboard journey and Settings preference/tool placement |
| `static/app.js` | Preference binding, normal Dashboard navigation, canonical frozen counts and localizable health/balance interface explanations |
| `static/my-versions.js` | Apply the display preference to asynchronous full diagnostics |
| `static/najdi.css` | Specialist visibility and existing workflow-step layout |
| `static/i18n-ar.js` | Arabic translations for changed interface text |
| `tests/test_ux_consistency.py` | Six regression contracts, including shared catalog counts |
| `tests/data-journey-browser.cjs` | Real navigation, persistence, blocked storage, links, reflow, downloads and API errors |
| `tests/i18n-browser.cjs` | Dynamic descriptions/errors, version readiness and advanced tools in Arabic |
| `tests/i18n-catalog.test.cjs` | Include preparation and versions in fixed-message coverage |
| `tests/test_theme_support.py` | Preserve readiness caveat with the approved preparation destination |
| `tests/chat-browser.cjs` | Follow the new Settings entry point to existing export blocker checks |
| `docs/user-guide.md` | Document ordinary workflow and optional specialist navigation |
| `CHANGELOG.md` | Record unversioned development changes |
| `docs/development/UX_CONSISTENCY.md` | Record architecture, implementation sequence, evidence and rollback |

## Rollback and limits

Revert the source commit to restore the previous interface. The optional localStorage key may be removed through browser storage controls. There are no schema changes or data migrations in this change.

Manual screen-reader review and browsers other than Chromium remain untested. Arabic wording awaits independent language review. Test evidence covers synthetic datasets and preserves the existing external-training boundary.
