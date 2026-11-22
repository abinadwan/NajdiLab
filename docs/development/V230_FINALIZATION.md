# V2.3.0 finalization and verification

## Goal and implementation plan

Make the four-stage Guided Wizard the official data workflow, preserve a restorable Advanced Workspace, and publish a reviewed development candidate to `update-project` using an ordinary fast-forward push.

The user's two finalization and documentation-audit specifications govern this work. The starting checkout is clean on `update-v2.3.1` at `8753463f27009f8574614294e8e45425142d5706`. Work stays in this explicitly selected checkout. The implementation uses the existing Python server, vanilla browser JavaScript, CSS and synthetic Chromium fixture.

- [x] Add failing contracts for the Wizard-only shell, ignored historical mode preference, lazy legacy interface and V2.3.0 version.
- [x] Extract the legacy launcher, mode controls and specialist panels into a separately loaded HTML/JavaScript/CSS bundle. Keep shared functions and APIs in place. Direct diagnostic URLs mount their panels on demand. The official shell loads the Wizard without fetching or mounting this bundle.
- [x] Preserve and document restoration through an explicit developer operation in a temporary static checkout. Exercise the old mode controls and shared diagnostic APIs in that isolated restoration test.
- [x] Archive selected real bilingual synthetic screenshots and write the required architecture, features and restoration guides.
- [x] Run Python, Node and Chromium, including stale preferences, drafts/restart, data history, privacy, leakage, Frozen integrity, Manifest/SHA256, export and safe deletion.
- [x] Inventory every repository Markdown/MDX file. Review current instructions against code and mark historical evidence explicitly. Audit local paths, anchors, external URLs, examples and image provenance.
- [x] Capture permanent V2.3.0 screenshots and update the official README, user/developer guides and release-candidate notes. Preserve historical version numbers.
- [x] Run documentation regression checks and a fresh independent whole-change review.
- Commit on `update-v2.3.1` after verification. The final task response records the observed result.
- Fetch origin after the commit, prove the target history is an ancestor, push only to `update-project`, verify the remote SHA and rendered README/assets, and inspect Actions while preserving Draft PR #23. The final task response records the observed delivery evidence.

## Review focus

- A stored `najdilab.advancedMode=1` must leave the Wizard, chosen IDs and drafts intact.
- The default journey must request no legacy bundle or unused specialist panel.
- On-demand diagnostic views must bind their original controls once, retain backend safety checks and handle load failure with a retryable error.
- Restoration must modify only an explicitly synthetic temporary static tree and must not re-enable the official shell.
- Screenshots and examples must contain synthetic data, and current documentation must link only to permanent tracked assets.
- Push must preserve all remote commits and leave PR #23 in Draft with its existing base.

## Progress and decisions

The original backend and reusable record editor remain shared. Only the workspace presentation and specialist-panel mounting change. The archived controller has an explicit developer restoration entry point, with no official navigation control invoking it.

Implementation, independent review and the final local documentation/test gates are complete. The candidate is ready for the local commit. Delivery verification follows the commit, fetch and fast-forward ancestry check. The complete documentation inventory is in [the audit](V230_DOCUMENTATION_AUDIT.md).

## Completed verification

All runtime fixtures use new synthetic databases, disposable files and random loopback ports. Real model services and installed user state are excluded from this acceptance run.

| Proof | Result |
| --- | --- |
| Full Python suite | 1044 passed, 57 skipped, 59 subtests passed |
| Node unit tests | 73 passed, 0 failed |
| Seven serial Chromium suites | 45 passed, 0 failed |
| Model library Chromium | 18 passed, 0 failed |
| Review restrictions Chromium | 12 passed, 0 failed |
| Standalone Chat browser | PASS |
| Standalone Chat enhancements browser | PASS |
| Documented examples and setup/version/provenance | 4 passed |
| Combined documentation, README and scope contracts | 22 passed |
| Side-effect-free installer check and Python compileall | PASS |
| Independent final whole-change review | No material findings |

The final full Python rerun completed with 1044 passed, 57 skipped and 59 subtests passed in 170.87 seconds. One preceding rerun encountered Windows socket error 10053 during an Origin-refusal test, while the server logged 403. The unchanged four-test security module then passed, followed by this clean full rerun. No error filtering or retry behavior was added to the tests.

The formal Chromium total is 75 passing cases, including parent cases, plus two passing standalone scripts. The guided English and Arabic journeys recorded zero page, console and server errors and no legacy-asset requests. Restart acceptance preserved the exact draft, selected record, check stage and Arabic direction while ignoring the stored legacy mode preference.

The legacy restoration test recreated a static shell under `.test-tmp`, exercised both languages, specialist navigation, mode changes and reload, and confirmed that the official source hash stayed identical. The reviewer also compared all seven preserved panel subtrees with baseline `8753463` and checked lazy loading, event bindings, navigation races, storage and restoration boundaries.

Optional real engines, LM Studio SDK, Unsloth Python, private historical artifacts and Windows symlink privileges explain the Python skips. Hardlink/junction and Gold deletion safety cases executed. Chromium accessibility-tree evidence has a narrower scope than real screen-reader or Firefox/Safari acceptance.

## Documentation and visual evidence

- The audit covers 105 Markdown files, with 73 updated or added and no MDX files.
- Twelve unmodified V2.3.0 PNGs and provenance live in `docs/assets/screenshots/v2.3.0/`. Four appear in the README and the complete set appears in `docs/screenshots.md`.
- Two selected unmodified V2.2.0 synthetic screenshots and the required four guides live in `docs/legacy/advanced-workspace/`.
- All fourteen selected PNGs received visual review. Historical version labels remain explicit.
- All 58 unique external URLs returned HTTP 200, including the post-push Actions run. Authenticated GitHub API checks cover private repository targets.
- Actual GitHub Markdown API HTML rendered in Chromium with 23 second-level headings, 19 images and zero broken images. `v230-render-verification.json` records the result. The available browser session is signed out, so direct authenticated private repository-page inspection remains unavailable. Post-push verification uses authenticated branch-specific GitHub HTML and image bytes.
- Five synthetic record examples execute through a fresh database, Manifest/SHA256 verification and a two-target conversational handoff. DPO and evaluation content stay outside that handoff.

Gold inclusion alone does not establish SFT training eligibility. Legacy Gold deletion retains conservative ownership/reference restrictions, and Frozen safety checks remain active. Training is external. The separate Core distribution profile requires its own source-policy/build revalidation. Only its corrected historical README link and corresponding documentation hash pin changed in this task.

## Delivery verification

The initial candidate was committed as `5fdd6837cf288ed80c3fe752f5efce182604e942` on `update-v2.3.1`. Its working tree was clean before `git fetch origin`. The fetched `origin/update-project` was `1abf2d71db284a2becf2d89703feaaaffbace124`, an ancestor of the candidate. An ordinary fast-forward push delivered all four pending commits to `update-project`, and both `git ls-remote` and GitHub API confirmed the exact candidate SHA.

Authenticated post-push verification matched all 471 committed file blobs. Nineteen README, brand/architecture, screenshot and provenance assets matched the committed bytes, including all fourteen selected PNGs. The branch-specific GitHub-rendered README contained V2.3.0, 23 second-level headings and 19 image elements. PR #23 remained open, Draft, with base `main` and head `update-project`. [Delivery evidence](v230-delivery-verification.json).

Manual Source checks run `42322521062` completed with failure before either Ubuntu or Windows started any test step. Both check annotations report failed recent account payments or the need to increase the spending limit. There are no runner test logs because the jobs never started. The automatic Draft PR runs for Source checks and Source-only candidate were skipped under their existing policy. [Observed Actions run](https://github.com/abinadwan/NajdiLab/actions/runs/42322521062).

**BLOCKED** applies to hosted verification. The implementation push, local test gates and authenticated remote-file checks succeeded. The account owner must resolve the Billing & plans condition before a hosted verification can execute. The final task response records the SHA of the documentation-only follow-up containing this observed evidence. No passing CI result is inferred from the local runs.

## Complete changed-file list

The following source, test, documentation and selected evidence paths comprise this task. Ignored temporary logs, fixtures and previews are excluded.


```text
.github/workflows/checks.yml
CHANGELOG.md
CONTRIBUTING.md
PROJECT_STATUS.md
README.md
app/version.py
docs/UX_UI_DESIGN_REVIEW.md
docs/accessibility.md
docs/api-reference.md
docs/architecture.md
docs/asset-provenance.md
docs/assets/screenshots/v2.3.0/dark-export.png
docs/assets/screenshots/v2.3.0/dashboard.png
docs/assets/screenshots/v2.3.0/gold-delete-confirm.png
docs/assets/screenshots/v2.3.0/gold-versions.png
docs/assets/screenshots/v2.3.0/manual-edit.png
docs/assets/screenshots/v2.3.0/mobile-data.png
docs/assets/screenshots/v2.3.0/mobile-version.png
docs/assets/screenshots/v2.3.0/provenance.json
docs/assets/screenshots/v2.3.0/wizard-approve.png
docs/assets/screenshots/v2.3.0/wizard-check-problem.png
docs/assets/screenshots/v2.3.0/wizard-check-ready.png
docs/assets/screenshots/v2.3.0/wizard-data.png
docs/assets/screenshots/v2.3.0/wizard-export.png
docs/chat-completion-results.md
docs/chat-review-workflow-results.md
docs/chat-ui-fixes.md
docs/cleanup-plan.md
docs/cleanup-results.md
docs/codebase-navigation.md
docs/configuration.md
docs/data-retention.md
docs/database-and-migrations.md
docs/database-schema.md
docs/dataset-export.md
docs/dependency-licensing-matrix.md
docs/design-system.md
docs/developer-setup.md
docs/development/CHAT_COMPOSER.md
docs/development/CHAT_EXPERIENCE_V2.md
docs/development/CHAT_V2_SECURITY_REVIEW.md
docs/development/GOLD_HEALTH_P1.md
docs/development/GUIDED_WORKSPACE.md
docs/development/HUGGING_FACE_DIRECT.md
docs/development/LANGUAGE_METADATA.md
docs/development/MANAGED_RUNTIME.md
docs/development/MODEL_DISCOVERY.md
docs/development/NAJDI_LAB_REDESIGN.md
docs/development/PERMANENT_DELETION_AUDIT.md
docs/development/PR21_PR22_RECONCILIATION.md
docs/development/PUBLIC_READINESS.md
docs/development/REAL_MODEL_ACCEPTANCE.md
docs/development/RELEASE_NOTES_V2.0.0.md
docs/development/RELEASE_NOTES_V2.1.0.md
docs/development/RELEASE_NOTES_V2.2.0.md
docs/development/RELEASE_NOTES_V2.3.0.md
docs/development/TRAINING_CORRECTNESS.md
docs/development/UX_CONSISTENCY.md
docs/development/V230_DOCUMENTATION_AUDIT.md
docs/development/V230_FINALIZATION.md
docs/development/WINDOWS_ACCEPTANCE.md
docs/development/v230-delivery-verification.json
docs/development/v230-external-links.json
docs/development/v230-render-verification.json
docs/documentation-index.md
docs/examples/v230-records.json
docs/installation.md
docs/integrations-validation.md
docs/integrations-windows-update.md
docs/legacy/advanced-workspace/ARCHITECTURE.md
docs/legacy/advanced-workspace/FEATURES.md
docs/legacy/advanced-workspace/README.md
docs/legacy/advanced-workspace/RESTORE_GUIDE.md
docs/legacy/advanced-workspace/screenshots/arabic-mobile-dark.png
docs/legacy/advanced-workspace/screenshots/english-desktop-light.png
docs/legacy/advanced-workspace/screenshots/provenance.json
docs/localization.md
docs/maintainer-handover.md
docs/native-runtime.md
docs/open-source-readiness.md
docs/remediation/PHASE_B_IMPLEMENTATION.md
docs/remediation/PHASE_C_IMPLEMENTATION.md
docs/remediation/REMEDIATION_ROADMAP.md
docs/review-and-quality.md
docs/review-restriction-integrity.md
docs/rights-evidence.md
docs/roadmap.md
docs/screenshots.md
docs/shell-commands.md
docs/superpowers/plans/2026-11-02-chat-review-workflow.md
docs/system-requirements.md
docs/troubleshooting.md
docs/user-guide.md
docs/verification-evidence.md
public_source/README.md
public_source/policy.json
scripts/check_docs.py
scripts/publish_documentation_screenshots.py
scripts/restore_advanced_workspace.py
static/advanced-workspace.css
static/advanced-workspace.html
static/advanced-workspace.js
static/app.js
static/chat.js
static/index.html
static/prepare-data.js
static/workspace.css
tests/a11y-browser.cjs
tests/chat-browser.cjs
tests/chat_browser_fixture.py
tests/data-journey-browser.cjs
tests/gold-health-browser.cjs
tests/guided-workspace-browser.cjs
tests/i18n-browser.cjs
tests/legacy-workspace-browser.cjs
tests/models-browser.cjs
tests/test_ci_workflows.py
tests/test_dataset_scope_ui.py
tests/test_docs_integrity.py
tests/test_readme_structure.py
tests/test_ux10_navigation.py
tests/test_ux_consistency.py
tests/test_v230_documentation.py
tests/test_version.py
tests/workflow-restart-browser.cjs
```
