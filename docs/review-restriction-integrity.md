# Review restriction integrity remediation

Approved source: `b074bd3f5711dff4ab7e1bb245a615cf72f924e8` on
`refactor/remove-legacy-training` (Draft PR #13). Work is isolated on
`fix/review-restriction-integrity`; no push, PR, merge or installed update is authorized.

## Investigation and implementation plan

The queue renderer resets tags and five restrictive flags instead of reading their
saved values. The save service treats omitted fields as false/empty and the
approve/correct wrappers default eligibility to true. Single and bulk restore
explicitly reset evaluation and exclusion flags. These independent layers must
all be covered: correcting the renderer alone leaves API callers vulnerable.

- [x] Reproduce reset, omitted-field loss, implicit eligibility and restore loss
  with automated tests before changing implementation; record failures below.
- [x] Merge omitted fields from the locked saved row, validate explicit flags/tags,
  keep all restriction gates, and retain optimistic revision checks.
- [x] Share single/bulk restoration policy: PENDING, eligibility off, restrictions,
  tags, originals and corrections retained; retain the mandatory restore reason.
- [x] Populate queue controls from persisted data; selecting eligibility must not
  implicitly clear restrictions. Verify refresh, failure and stale-update behavior.
- [x] Run affected API/browser checks, the full synthetic application suite and
  the affected restricted Core candidate checks; document exact results and limits.
- [x] Review the final diff and safeguards; package as one local commit only.

## Approved restoration policy

Restore changes lifecycle only. It never authorizes dataset inclusion or removal
of privacy, sensitivity, fact-check, evaluation-only or exclusion restrictions.
Changing those restrictions later requires a separate explicit review decision.
Bulk operations remain transactional. No migration or historical-data rewrite is
part of this change. Optional event tables remain optional.

## Implementation contract

The service merges omitted flags/tags/notes/reviewer from the saved row under
BEGIN IMMEDIATE. Explicit false and an explicit empty tag list remain supported;
malformed flags/tags fail before writes. All five restrictions force eligibility
off. Approval/correction wrappers and bulk decisions no longer opt into eligibility
by default. Existing tests of eligible decisions now request eligibility explicitly;
new regressions cover its absence.

The first post-fix full run found five old-fixture assumptions (440 passed,
5 failed, 33 skipped, 59 subtests passed): archive/reload/HTTP readiness fixtures
assumed automatic eligibility, and two privacy-export cases expected the old
writer to persist contradictory eligibility. Eligible fixtures now opt in
explicitly. The privacy-export cases assert the writer blocks eligibility, then
seed a legacy inconsistent row in their temporary DB so the existing independent
export privacy backstop remains tested. No export implementation changed.

Single and bulk restore share `_restore_review_conn`; requests cannot clear
restrictions during restoration. `ignored_reason` retains the restoration reason
even without optional event history; `ignored_at`/`deleted_at` are cleared. Prior
corrections, notes, tags, original messages and existing event rows stay intact.
Optional event tables are tested only in disposable fixtures, not enabled in the
application or by a new migration.

A follow-up regression exposed that the next correction cleared the retained
restoration reason even without an event table (one expected failure). Review
saves now preserve the last lifecycle reason as well. This is latest-reason
retention, not a new immutable audit ledger; later lifecycle actions can record
a new reason, and complete history still depends on existing optional events.

The browser reads persisted controls and never clears evaluation/exclusion flags
when eligibility is clicked. Bulk browser lifecycle requests carry each loaded
record's timestamp. The backend compares supplied single/bulk preconditions in
the transaction and generates monotonic timestamps. Preconditions remain optional
for API compatibility; legacy callers omitting them can still overwrite an
explicit concurrently changed field. Reviewer assertions remain unauthenticated
categories; this patch adds no RBAC or historical reconstruction.

## Evidence

Before implementation: the unchanged source suite passed 415 tests, skipped 33,
and passed 59 subtests on Linux. New API/service regressions failed 26 and passed
4 (30 total), exposing omitted flags/tags, implicit eligibility, restore loss,
missing bulk preconditions and repeated-clock revisions. Chromium reproduced all
five persisted restriction controls rendered unchecked; six browser subtests
failed (seven failures including their parent). No implementation was changed
before these failures were observed. An earlier browser fixture used invalid
test timestamps; that setup error was corrected before recording the UI defect.

The first sandbox-only baseline attempt was unsupported: 4 failed, 251 passed,
33 skipped, 160 setup errors and 11 subtests passed, primarily because socket
binding was prohibited. The supported loopback-enabled baseline above supersedes
that attempt. One browser launch approval could not complete due to a temporary
approval-service usage limit; after the owner requested continuation, it ran.

All databases and browser fixtures are disposable synthetic
SQLite data, never owner databases. No inference, provider discovery or GPU work
is needed for review acceptance.

## Exact file inventory

- `app/service.py`: omitted-field merge, validation, eligibility gates, revisions,
  shared single/bulk restore and reason retention.
- `static/app.js`: persisted controls, safe eligibility interaction and loaded
  revisions for bulk lifecycle requests.
- `tests/test_review_restriction_integrity.py`: synthetic service/HTTP regressions
  and disposable browser fixture.
- `tests/review-restrictions-browser.cjs`: actual Chromium UI/API regressions.
- `tests/test_najdilab.py`: explicit eligibility in existing eligible fixtures.
- `tests/test_review_management.py`: explicit eligibility in bulk-ready fixtures.
- `tests/test_unsloth_export.py`: retain legacy privacy backstop coverage while
  asserting that new decisions cannot persist contradictory eligibility.
- `.github/workflows/checks.yml`: run the new browser regression in future CI.
- `public_source/policy.json`: refresh only the shared service hash; classify the
  three new root-only files as excluded. Core remains the same 71-file profile.
- `docs/review-and-quality.md`: current policy and API semantics.
- `docs/review-restriction-integrity.md`: plan, evidence, limits and rollback.

No migrations, schema, dataset/export code, Chat consent, inference providers,
Hermes, themes or navigation were modified. The exact protected source paths were
compared against the approved baseline. No owner data was inspected or changed.

## Verification commands and limits

Final observed results (subtests reported separately, never added to test totals):

| Check | Passed | Failed | Skipped | Subtests passed |
| --- | ---: | ---: | ---: | ---: |
| Full root synthetic suite | 446 | 0 | 33 | 59 |
| Affected review/export suite | 107 | 0 | 0 | 0 |
| New service/API regressions, included in the above suites | 31 | 0 | 0 | 0 |
| Chromium review regression | 9 | 0 | 0 | 0 |
| Existing Node Chat/integration controllers | 10 | 0 | 0 | 0 |
| Restricted Core builder | 12 | 0 | 0 | 18 |
| Final rebuilt Core suite | 78 | 0 | 0 | 68 |

The nine Chromium tests comprise eight functional subtests plus their parent.
Existing root Chat browser acceptance passed one synthetic suite. Final Core
browser acceptance passed four groups, and its manifest-copy boundary harness
passed. The builder verified the same 71 selected files; no profile expansion.
Documentation validation passed all 64 Markdown files and generated API inventory.
Python compilation, Node syntax and whitespace checks passed. Earlier iterations
and their failures are retained above rather than relabeled as final results.

Use the repository's pinned requirements in a separate test environment. Commands
below are recorded executions, not permission to run against owner data:

- `NAJDILAB_DISPOSABLE_OLLAMA=0 python -m pytest -q tests -rs`
- `python -m pytest -q tests/test_review_restriction_integrity.py tests/test_review_management.py tests/test_review_integrity.py tests/test_review_lifecycle.py tests/test_najdilab.py tests/test_unsloth_export.py`
- `node --test --test-isolation=none tests/review-restrictions-browser.cjs`
- `node --test --test-isolation=none tests/integrations-ui.test.cjs tests/chat-ui.test.cjs`
- `node tests/chat-browser.cjs` (synthetic engines only)
- `python -m pytest -q public_source/tests/test_builder.py`
- Build and verify the Core into a separate directory with `public_source/build.py`;
  there run `python -m pytest -q tests -rs`, `node tests/harness.cjs` and
  `node tests/browser.cjs .`. Only disposable synthetic copies are started.
- `python scripts/check_docs.py`, Python compilation, Node syntax checks and
  `git diff --check`.

Chromium used the separately installed pinned `puppeteer-core@25.16.0` driver,
with `PYTHON`/`NAJDILAB_TEST_PYTHON` set to the isolated test interpreter and
`NAJDILAB_BROWSER_EXECUTABLE=/usr/bin/chromium`. No runtime dependency changed.
The preceding results are from Linux/Python 3.12; the local Windows follow-up
is recorded below. Hosted CI has not been run as part of this follow-up.
Nine opt-in real-Ollama checks are intentionally disabled, 22 checks need
unavailable private historical artifacts, and two checks require Windows. Those
33 skips are not passes. No real-model, GPU, installed-application or private-data
acceptance is claimed. Independent read-only review found no actionable issues.

Remaining limits: no reconstruction of previously cleared restrictions; optional
preconditions remain optional for legacy callers; reviewer identities are asserted
categories. Existing single exclude/delete paths still do not compare submitted
revisions; this change does not expand into those separate lifecycle endpoints.
Existing exports retain their historical state and are never rewritten.

## PR #14: Windows browser viewport follow-up (2026-11-01)

The local checkout was clean on `fix/review-restriction-integrity` at
`e38eed62e2d48c6737c12149cb5262fb3143690d` before this follow-up. Windows used
Node 26.10.0, Python 3.12.10, the existing `puppeteer-core` 25.16.0 installation
and Chrome 156.0.8078.74; no dependencies were installed or updated.

Before editing, `node --test tests/review-restrictions-browser.cjs` reproduced
6 PASS / 3 FAIL / 0 skipped in 1671.6537 ms. The first failure was the click on
`#apply-reviewed-filters` in single-card restoration:
`Node is either not clickable or not an Element`. Bulk restoration then failed
with `0 !== 2`, and the parent failed too. The earlier investigation reported
that `/gold` was active and Apply was visible with normal dimensions. The
owner's temporary 1440 x 1000 experiment passed 9/9 in approximately 1.7 seconds;
the fresh before/after runs below corroborate the viewport dependency.

`tests/review-restrictions-browser.cjs` now calls
`await page.setViewport({width:1440,height:1000});` immediately after
`browser.newPage()` and before navigation. An explicit desktop viewport makes
the layout assumption of this desktop review workflow repeatable instead of
relying on Puppeteer's default viewport. All assertions, success conditions,
existing UI clicks and API integrity checks remain unchanged. There is no DOM
click bypass, disabled integrity check, added retry or application-code change.

This stabilizes the browser test only. It does not fix responsive UI defects,
prove mobile/small-window usability, or establish the precise rendering cause
of the default-viewport click failure. Separate responsive acceptance is still
needed; it is outside this narrow follow-up.

Run from `C:\Users\Admin\Documents\NajdiLab-PR14` with the existing environment:

```powershell
$env:NODE_PATH='C:\Users\Admin\Documents\NajdiLab-PR14-BrowserTools\node_modules'
$env:PYTHON='C:\Users\Admin\Documents\NajdiLab-Test\.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:NAJDILAB_BROWSER_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:NAJDILAB_DISPOSABLE_OLLAMA='0'
$env:NAJDILAB_TEST_PYTHON=$env:PYTHON
node --test tests/review-restrictions-browser.cjs # run 1
node --test tests/review-restrictions-browser.cjs # run 2
node --test tests/review-restrictions-browser.cjs # run 3
& $env:PYTHON -m pytest -q -p no:cacheprovider tests/test_review_restriction_integrity.py
& $env:PYTHON -m pytest -q -p no:cacheprovider tests/test_review_management.py tests/test_review_integrity.py tests/test_review_lifecycle.py tests/test_najdilab.py tests/test_unsloth_export.py tests/test_complete_review_queue.py -rs
& $env:PYTHON -m pytest -q -p no:cacheprovider tests -rs
node --test tests/integrations-ui.test.cjs tests/chat-ui.test.cjs
node --check tests/review-restrictions-browser.cjs
& $env:PYTHON scripts/check_docs.py
git diff --check
```

The pytest cache provider is disabled to avoid repository cache writes; this
does not change test selection or assertions. Browser counts include eight
functional subtests and their parent. Consecutive post-fix executions were:

| Check | Passed | Failed | Skipped | Duration |
| --- | ---: | ---: | ---: | ---: |
| Chromium run 1 | 9 | 0 | 0 | 1788.7314 ms |
| Chromium run 2 | 9 | 0 | 0 | 1765.5895 ms |
| Chromium run 3 | 9 | 0 | 0 | 1769.2129 ms |
| Python review restriction integrity | 31 | 0 | 0 | 4.33 s |
| Related Python review/export checks | 79 | 0 | 0 | 4.23 s |
| Full root Python regression suite | 447 | 0 | 32 | 103.66 s |
| JavaScript Chat/integration controllers | 10 | 0 | 0 | 60.467 ms |

All entries above exited 0. The full Python suite also passed 59 subtests,
reported separately from the 447 tests. Its 32 skips are not passes:

- Nine real-engine checks in `tests/test_chat_ollama_real.py` were intentionally
  disabled by `NAJDILAB_DISPOSABLE_OLLAMA=0`; no real inference was run.
- Twenty-two checks require unavailable private historical artifacts.
- `tests/test_integrations.py::test_symlink_marker_is_not_followed`
  was skipped because this Windows account cannot create the required symlink.

The documentation checker passed all 64 Markdown files, local file links and
the generated API inventory. Node syntax and `git diff --check` passed. No
post-fix test failed. Hosted CI and mobile/responsive acceptance were not run.

Only the browser test, this existing evidence document and `CHANGELOG.md` are
changed. The original NajdiLab checkout, `NajdiLab-Test` environment and database,
and real user data were not modified. Browser/HTTP writes target disposable
synthetic SQLite fixtures on random loopback ports. No Ollama, LM Studio or
Hermes application was started, and no model download or real inference ran.

Rollback for this viewport-only follow-up: remove the added `setViewport` call,
join the surrounding page/error-listener line if desired, and remove this
follow-up section plus its changelog entry. Then rerun the same checks and
expect the default-viewport regression to be possible again. No schema, database,
exports, dependencies, reset/clean or history rewrite is required. Do not revert
the underlying review-integrity remediation to undo this test setup change.
At the time of the local verification recorded above, no commit or push had been performed. No new PR, merge or base-branch change was performed during that verification.

## Rollback

This work changes source only. Preserve this branch and its evidence. If rollback
is later approved, revert the remediation commit on a separately reviewed branch;
do not reset shared history or launch old code against private data. No migration,
database restore, export deletion or provider change is needed. Reverting source
reintroduces the restriction-loss risks and does not recover previously lost flags.
