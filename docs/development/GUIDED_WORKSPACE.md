# Guided workspace implementation and acceptance

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

Branch `update-v2.3.1`, base `1e677dd767c40f14085dd35e577f99e1cd9e3105`. Application version V2.2.0.

## Design and ownership

The default Data workspace is one four-stage wizard. Data contains the existing manual entry forms and a selectable record list with existing history-aware edit, clone and logical-delete operations. Check uses the same `prepare_check` planning and fingerprint contract as Gold creation. Approve presents actual output counts, warnings and explicit confirmation. Export displays the created or opened Frozen version, supported Unsloth profiles and separate raw JSONL types.

Advanced Mode switches the workspace display to independent existing tools. A visible top-bar control and Settings share one preference. Deep links remain routable. Returning to normal mode restores the wizard context. Local draft persistence covers stage, selection, filters and unsaved entry/edit fields. Stored checks are never trusted after a reload, they are rerun before approval. Frozen export state is reloaded from the backend.

The existing vanilla JavaScript, local fonts, color tokens and flat NajdiLab shell remain the design foundation. The four stages are a short numbered rail with one working section, a restrained primary action and expandable evidence. Record content and identifiers retain their own direction and localization boundaries.

Gold management uses a preview and explicit typed confirmation. Backend ownership, hash, link and dependency proofs decide whether deletion is allowed. Original registry/history evidence remains through an audit/tombstone, preventing identifier reuse. Unprovable legacy versions are refused. Raw downloads use a fixed manifest-verified allowlist and exclude the private recovery archive.

## Execution plan

1. Add failing UI acceptance for four stages, visible mode switching and preserved context. Implement the existing-form integration and draft lifecycle in the wizard.
2. Implement backend export options, safe download and deletion in an independently owned module with synthetic regression tests. Wire routes through the existing security/CSRF boundary.
3. Extend My versions with inline details, readiness, direct export entry and a preview-backed deletion dialog.
4. Exercise the complete user journey in Arabic and English through real Chromium clicks, including correction, logical record deletion, mode changes, reload, exports, canceled deletion and isolated Gold deletion.
5. Capture and inspect screenshots for all stages, both directions/themes and 320/390/1440px. Produce a local visual report. Run relevant and full regression suites, review the diff and create local commits.

## Review focus

- Reloaded or changed selections require fresh backend checks and confirmation.
- Source edits and deleted records never mutate previously Frozen files.
- Hidden selected records survive filters and mode changes.
- Data formats keep their identity through export.
- Deletion refuses stale previews, unowned files, shared references and unsafe paths, and records auditable outcomes.

Implementation progress and observed results are recorded below as verification completes.

## Implemented behavior

The four panels share one route and the existing manual forms. `NajdiPrepare` owns selection, stage and browser drafts. `najdilab.workflow.v1` stores entry fields, exact multiline turns, filters, selection, the open editor draft and current version. `najdilab.advancedMode` owns the shared visible mode controls. Switching modes moves the form host and changes the workspace presentation. Returning or reloading repeats backend checks and requires explicit approval again. Record changes invalidate the old check, and a revision guard rejects stale check responses.

Gold ownership is implemented in `app/gold_management.py`. The existing filesystem registry remains authoritative for readable versions. Pending database deletion plans are merged into the versions response so recovery remains reachable after restart. Preview tokens bind the database, exports root, exact filenames, sizes and hashes. A typed version name and a fresh token are required for mutation. The original dataset row and manual export history remain as a tombstone. A persistent flat reservation prevents a filesystem-derived version or another database sharing the root from reusing the identity.

The lifecycle module serializes public Gold mutations with reentrant per-root thread and operating-system locks. Lock files must be regular, unshared files and their ownership is checked again after acquisition. Windows junctions, symlinks and hardlinks are refused. Deletion commits an audited plan, reserves the identity, quarantines the directory and removes only attested files. Interrupted operations retain a newly previewable plan, including the case where no files remain and only completion must be recorded. Refused export readiness checks run before storage is created and are repeated inside the lock.

New manifests carry `ownership.managed_reference_policy = 1`. Managed Unsloth publication records a durable reference before publishing, including custom output roots. Migration 011 adds `gold_version_deletions` and `gold_deletion_audit`. Migrations 001–010 retain their existing contents and hashes.

## Browser evidence

The actual Chromium journey runs separately in English and Arabic against temporary synthetic databases and random loopback ports. Each journey starts with empty manual records and seeded synthetic legacy versions. It creates and corrects an example, checks its edit history, duplicates an example, confirms logical deletion of a temporary record, encounters evaluation leakage, corrects the evaluation answer in place, reruns checks, explicitly approves Gold, verifies Manifest/SHA256, creates an Unsloth handoff and downloads its JSONL. It also creates a second Gold, cancels deletion, confirms deletion and verifies the first Gold hashes remain unchanged. Standalone Direct Language gets its separate JSONL and an explained incompatible Unsloth option.

The restart suite stops the synthetic Python process and starts a different PID on the same temporary origin and state root. It verifies Arabic RTL, Advanced Mode, stage 2, chosen IDs and exact multiline drafts, with all ten seed-file digests unchanged. Browser, console and server error counters are zero in the full journeys.

- Stage-linked screenshot gallery (`../../.test-tmp/guided-acceptance/visual-report.html`, local historical evidence)
- Screenshot index (`../../.test-tmp/guided-acceptance/screenshots.json`, local historical evidence)
- Actual restart proof (`../../.test-tmp/workflow-restart-acceptance/proof.json`, local historical evidence)
- English HTTP evidence (`../../.test-tmp/guided-acceptance/http-en.json`, local historical evidence)
- Arabic HTTP evidence (`../../.test-tmp/guided-acceptance/http-ar.json`, local historical evidence)
- Downloaded training JSONL (`../../.test-tmp/guided-acceptance/downloads/en/dataset.jsonl`, local historical evidence)
- Inspector measurements (`../../.test-tmp/guided-inspector/report.json`, local historical evidence)

These local evidence files are ignored test artifacts. They are retained in this checkout and excluded from the source commit.

## Visual review

The existing Najdi Sans typography, neutral sheet shell and teal state accent were retained as the design direction. No external photographs or generated sample UI assets are used. The screenshots contain actual synthetic records and counts from the running application. The acceptance matrix uses 320, 390 and 1440 CSS pixels, Light and Dark, Arabic RTL and English LTR.

### Round 1

The first screen exposes the workspace name, four-stage rail and primary data action. The record editor and checks use aligned full-width panels. Examination found a cropped 390px RTL capture, transient success notifications obscuring evidence, and a technical byte label in English. DOM geometry proved the RTL viewport and content bounds were correct. Chromium's beyond-viewport capture was replaced with a full-page viewport capture after animations and notifications settle. The byte label was localized. The stage indicator's inset shadow was replaced with a flat border.

### Round 2

The corrected Arabic problem-check image shows the complete stage rail and usable Edit/Exclude actions at 390px. The 320px Arabic forms stack roles, text, taxonomy fields and record actions within the viewport. English desktop export separates raw data files, readiness and compatible training profiles. Advanced Mode presents independent tool buttons while the Wizard is hidden. Dialog screenshots use the viewport so their native scroll behavior and focus are represented accurately.

The inspected samples cover the Dashboard, empty and populated data, editing, blocked and successful checks, approval, exports, versions, deletion, Advanced Workspace and restored context. Spacing and reading order follow both directions. Textareas retain the user's text and technical identifiers retain LTR isolation. Long file hashes wrap inside the deletion dialog. The manual entry form is intentionally tall on a phone and collapses through its Add data manually disclosure. A long deletion plan scrolls within the dialog.

The app-screen critique scores are design 8, usability 8, product specificity 8 and content 9, giving 8.25 overall. The product-specific element is the four-stage record-to-Frozen workflow with actionable backend findings. The remaining density comes from the reused full manual editor and long hash lists. The final automated inspector reports 0 FAIL and 0 WARN. Visual judgments come from inspecting actual screenshots in addition to these measurements.

## Safety decisions and limits

- Permanent deletion is refused for legacy versions without the managed-reference ownership proof, unknown extra files, mismatched hashes, ambiguous roots, links or dependencies. Existing readable legacy versions retain their export entry points.
- A failed handoff publication can leave a durable reference reservation. It conservatively blocks deletion until that reference is investigated. The UI cannot discard this evidence.
- Browser drafts remain in this browser profile. Blocked browser storage uses the current page's in-memory context and displays a persistence warning.
- Real engine execution, private historical artifact checks and optional SDK/tooling integrations are recorded as skipped where their prerequisites are absent. Acceptance uses synthetic engine fixtures.
- The separate `public_source` distribution profile was outside this private-app implementation and its packaging verification was not run.

## Final verification results

| Verification | PASS | FAIL | SKIPPED | Evidence |
| --- | ---: | ---: | ---: | --- |
| Full Python suite | 1036 | 0 | 57 | `.test-tmp/workflow-python-final.log` |
| Python subtests | 59 | 0 | 0 | Included in the same Python run |
| Gold lifecycle focused suite | 52 | 0 | 0 | `.test-tmp/gold-lifecycle-final.log`, included in the full suite |
| Node unit suite | 73 | 0 | 0 | `.test-tmp/workflow-node-final.log` |
| Six Chromium acceptance files | 42 | 0 | 0 | `.test-tmp/workflow-browser-final.log` |
| Standalone Chat browser journey | 1 script | 0 | 0 | `.test-tmp/workflow-chat-browser.log` |
| Final UX/Gold delta regression | 58 | 0 | 0 | `.test-tmp/workflow-last-delta.log`, overlapping the full suite |
| App-screen inspector | 0 findings | 0 | 0 | `.test-tmp/guided-inspector/report.json` |

The Python skip report lists 57 individual cases. They require real engines, the optional LM Studio SDK, Unsloth Studio's external Python, private historical artifacts, or Windows symlink privileges. Windows hardlink, junction and locked-file Gold deletion tests ran. No skipped case is counted as passed. Real-engine owner acceptance and the separate public distribution package are NOT TESTED in this task.

The six-file browser run includes 13 accessibility cases, 11 data-journey cases, 3 Gold-health cases, 3 full-workflow cases, 10 localization cases and 2 restart cases. Node's counts include parent test cases. Both full guided journeys report zero page, console and server errors. Compileall, documentation links/API inventory and `git diff --check` pass. The gallery contains 98 distinct PNG paths. Repeated captures of the same named stage reference its latest image in the screenshot index.

Two independent review findings were corrected and rechecked. Deleted identities remain reserved across derivation and databases sharing an exports root. Interrupted deletion remains reachable through My versions and can finish with an empty remaining-file plan after a fresh typed confirmation.

The implementation is READY FOR USER ACCEPTANCE. The local commit identifier is supplied with delivery so this report does not contain a self-referential commit hash.

## Changed source files

The implementation and safety boundaries are in the following files.

```text
app/dataset_platform.py
app/gold_lifecycle.py
app/gold_management.py
app/server.py
app/service.py
app/unsloth_export.py
migrations/011_gold_version_deletions.sql
migrations/registry.json
static/app.js
static/i18n-ar.js
static/index.html
static/my-versions.js
static/prepare-data.js
static/workspace.css
```

The verification, CI and documentation changes are in the following files.

```text
.github/workflows/checks.yml
CHANGELOG.md
docs/api-routes.md
docs/cleanup-inventory.json
docs/development/GUIDED_WORKSPACE.md
docs/user-guide.md
tests/chat-browser.cjs
tests/chat-ui.test.cjs
tests/chat_browser_fixture.py
tests/data-journey-browser.cjs
tests/gold-health-browser.cjs
tests/guided-workspace-browser.cjs
tests/i18n-browser.cjs
tests/i18n-catalog.test.cjs
tests/my-versions-ui.test.cjs
tests/synthetic_datasets.py
tests/test_ci_workflows.py
tests/test_gold_management.py
tests/test_migration_010_language.py
tests/test_phase_a_regressions.py
tests/test_ux_consistency.py
tests/workflow-restart-browser.cjs
```
