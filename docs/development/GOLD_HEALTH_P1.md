# P1 Gold health crash and browser acceptance

Date 2026-11-06. Branch `update-v2.3.1`, based on local commit `e7cfe9319df2d8aca8e57b22b956ec4c6a83f296`. Application version V2.2.0.

## Proven cause

Both the current diagnostics producer in `app/dataset_platform.py` and the historical producer in `scripts/build_gold_v007_balanced.py` intentionally return `None` for the three highest conversation shares when there are no SFT conversations. Direct Language records retain their separate format and do not populate that conversation summary.

`dataset_health()` supplied a default only for a missing key and then indexed the result. An explicitly present `None` therefore raised `TypeError` at the old line 649. The same assumption existed for context-word concentration. Version Details calls Health, and Balance also calls Health, propagating the crash to those endpoints and the readiness/export interface.

Before changing product code, a new synthetic Direct Language-only export reproduced the traceback. The real Arabic and English browser journeys each observed POST export 201 followed by GET Health 500. The initial composition/null/malformed-data matrix reported 20 failures and 7 passes on the original implementation. Ordinary SFT cases already worked.

Repeated browser creation subsequently exposed stale Health/Balance version selectors. Their cached catalog omitted the second version. The existing catalog helper supports an explicit refresh, which those two view entry points now request.

## Fix and contracts

- A focused conversation-balance reader validates the optional statistics at their shared read boundary. Missing or null measurements stay unavailable. Missing nested metric values normalize to `None` in memory. Frozen files are read-only.
- Numeric shares must be JSON numbers within 0 through 1. Booleans, strings, malformed pairs, negative/out-of-range values, nonfinite values and oversized integers are validation failures. Bounds comparisons avoid converting large integers to floats.
- Concentration warnings run only for available measurements. Strict thresholds remain greater than 15 percent of records and greater than 30 percent of context words. Actual zero stays zero.
- Malformed concentration statistics return `INVALID_DIAGNOSTICS` with HTTP 422 across Health, Balance and Version Details. Existing malformed balancing-report errors retain `INVALID_MANIFEST` with HTTP 422. Balance propagates these specific diagnostics/report errors.
- Health shows unavailable concentration as Unavailable / غير متاح with a dash. Health and Balance refresh the existing version catalog when entered. The new validation message uses the existing Arabic catalog and preserves technical field identifiers.

## Regression matrix

`tests/test_gold_health_edge_cases.py` contains 34 cases and uses a fresh SQLite database, temporary exports and a loopback HTTP server on a random port. It constructs no model runtime manager.

| Case | Expected result |
| --- | --- |
| One Direct Language record with repeated Arabic letters | All three GET routes 200, concentration unavailable |
| Two Direct Language records | All three GET routes 200, concentration unavailable |
| One single-turn SFT record | GET routes 200, real concentration warnings retained |
| One multi-turn SFT record | GET routes 200, real concentration warnings retained |
| SFT plus Direct Language | GET routes 200, separate formats and valid warnings |
| Direct Language plus evaluation-only | GET routes 200, independent evaluation preserved |
| Evaluation-only with no training | Existing creation policy permits it, GET routes 200, conversation concentration unavailable |
| Three distinct training sources | GET routes 200, genuine concentration warnings retained |
| Empty selection | Existing `NO_EXPORTABLE_DATA` refusal before publication |
| Missing/null statistics and missing nested measurements | GET routes 200, unavailable measurements preserved |
| Malformed concentration values or report structure | All three GET routes 422 with a structured validation error |
| Zero and exact warning thresholds | Zero preserved, no warning at the exact thresholds |
| Thresholds exceeded | Both concentration warnings retained |
| Legacy Frozen Direct Language version | Read-only computed diagnostics, GET routes 200 |

Every read-only HTTP scenario snapshots the Frozen files before and after reading. Supported export compositions also compare computed file hashes against every manifest checksum. Existing privacy, split, fingerprint and loss-mask regression suites remain part of full verification.

## Real browser acceptance

`tests/gold-health-browser.cjs` uses the existing disposable browser fixture. That fixture binds database operations, exports, dataset catalog, handoffs, model directories and synthetic runtimes to temporary locations. Headless Chrome launches its own browser context. Test ports exclude 8770, 8870 and 8871.

For Arabic RTL and English LTR independently, actual UI clicks select the language, open Add data, save a Direct Language record containing repeated Arabic letters, open Prepare data, choose exactly that record, run Check, give fresh confirmation and create Gold. The journey opens My versions and Readiness and exports, then uses the existing specialist navigation to Health, Balance and Version Details. It returns to ordinary mode and deliberately repeats creation from the same record with a fresh confirmation.

Arabic creates synthetic `gold-v001` and `gold-v002`. English creates `gold-v003` and `gold-v004` in the same isolated fixture, selecting its own record explicitly. Assertions verify that each version contains exactly one Direct Language record and no SFT or evaluation records, every listed manifest checksum matches the independently computed file checksum returned by Version Details, and the complete file hash/size/count list stays identical after navigation and subsequent builds.

The API response ledger records all requests. Record creation returns 201, Check returns 200, Gold creation returns 201, and Health, Balance and Version Details return 200 for each new version. JavaScript exceptions, browser console errors and failed API response collections are empty. Visible interface text contains no `null`, `undefined`, `NaN` or internal-error message. HTTP ledgers and synthetic screenshots are kept in ignored `.test-tmp/gold-health-screens/`.

## Final verification

| Command | PASS | FAIL | SKIPPED | NOT TESTED |
| --- | ---: | ---: | ---: | ---: |
| `python -m pytest -q tests -rs` | 980 | 0 | 57 | 0 |
| Python subtests, separately reported | 59 | 0 | 0 | 0 |
| `node --test tests/*.test.cjs` | 62 | 0 | 0 | 0 |
| `node --test tests/gold-health-browser.cjs tests/data-journey-browser.cjs tests/i18n-browser.cjs tests/a11y-browser.cjs` | 37 | 0 | 0 | 0 |

The 34 new Python regression cases are included in the full Python total. The new browser suite contributes three Node test results, comprising two language scenarios and their parent. Both language scenarios create two intentional versions and traverse all required diagnostic screens.

The 57 skips comprise 22 private historical artifact cases, 18 missing optional LM Studio SDK cases, 13 opt-in real-engine cases, three Windows symlink cases and one external Unsloth Studio Python case. They are excluded from PASS. Required browser acceptance was executed. Hosted CI, Linux and non-Chromium engines were not run in this local task. The changed workflow is covered by the local CI-wiring regression.

The Direct Language browser response ledgers contain 63 HTTP 200 and three HTTP 201 responses for Arabic, and 67 HTTP 200 and three HTTP 201 responses for English. Every required read endpoint for the four created versions returned 200. No API response was 400 or higher in those valid browser journeys. Invalid-statistic/report scenarios separately assert HTTP 422 across all three read endpoints in Python.

Verification ran on Windows with Python 3.12.10, Node 26.10.0, headless Chrome and the existing recorded `puppeteer-core@25.16.0` tooling. `python scripts/check_docs.py`, Python compilation and `git diff --check` passed. An independent read-only review found no introduced regression and independently passed four UI unit tests. The final specific balancing-report error-propagation guard was added after that review, with three reproducing tests and a fresh full-suite run.

Final recommendation is READY FOR REVIEW. Evidence covers temporary synthetic datasets. Existing private datasets and external model-engine acceptance remain represented by the explicit skips above.

## Files and rollback

| File | Responsibility |
| --- | --- |
| `app/dataset_platform.py` | Optional-statistic validation and guarded concentration warnings |
| `app/dataset_balancer.py` | Preserve statistic/report validation errors |
| `app/server.py` | Map `INVALID_DIAGNOSTICS` to HTTP 422 |
| `static/app.js` | Unavailable concentration and fresh version selectors |
| `static/i18n-ar.js` | Translate the new validation message |
| `tests/test_gold_health_edge_cases.py` | Composition, null, malformed, threshold, HTTP and immutability regressions |
| `tests/dataset-identity-ui.test.cjs` | Unavailable display, genuine warning and catalog refresh |
| `tests/gold-health-browser.cjs` | Actual bilingual UI acceptance and file/HTTP evidence |
| `tests/test_ci_workflows.py` | Keep browser acceptance wired into Source checks |
| `.github/workflows/checks.yml` | Run the new browser regression with existing tooling |
| `CHANGELOG.md` | Dated unversioned development record |
| `docs/development/GOLD_HEALTH_P1.md` | Root cause, contract, evidence and rollback |

Rollback is an ordinary revert of the source commit. The patch adds no schema or data migration. Existing Frozen versions use the corrected read path directly. Privacy, eligibility, split rules and loss-mask generation retain their existing implementation.
