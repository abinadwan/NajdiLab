# Developer setup and first change

Use an authorized disposable checkout of the V2.3.0 candidate on `update-project` and read [PROJECT_STATUS](../PROJECT_STATUS.md). Review the exact revision before running a launcher. Tests use synthetic databases and isolated file roots. Follow [installation](installation.md). The core application has no frontend build step or mandatory pip packages. The [reduced Core profile](public-core-user-guide.md) is a separate distribution.

## Test tooling

The minimal venv intentionally has no pip. For development, bootstrap pip with the interpreter's standard ensurepip support, then install the recorded runner separately:

```powershell
.\.venv\Scripts\python.exe -m ensurepip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests -rs
```

```bash
.venv/bin/python -m ensurepip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests -rs
```

Some distributions supply pip/venv through OS packages; failure is a missing prerequisite, not permission for an unreviewed remote bootstrap script. Network package installation is distinct from verified offline core setup. Runner upgrades need validation.

Synthetic fixtures are included. Specific historical tests declare private file prerequisites via tests/private_artifacts.py. Missing files produce explicit SKIP reasons; present-but-corrupt files still fail. Read -rs; never report skips as passes or reconstruct/publish private data. Authorized maintainers can restore verified private copies to ignored paths for full checks. Original missing-fixture failures and final counts are in [verification](verification-evidence.md).

`python -m unittest discover -s tests -v` is supplementary: it omits function-style pytest cases. Tests create temporary databases and patch paths; understand imports before running historical utilities. Training/download/deployment is never onboarding or CI.

## Chromium prerequisites and commands

Use Node 22+ and an installed Chrome/Chromium. Browser test tooling is separate from the core runtime.

```powershell
npm install --prefix .test-tmp/browser-tools --ignore-scripts --no-audit --no-fund puppeteer-core@25.16.0
$env:NODE_PATH=(Resolve-Path '.test-tmp/browser-tools/node_modules').Path
$env:NAJDILAB_BROWSER_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
node --test --test-concurrency=1 tests/guided-workspace-browser.cjs tests/legacy-workspace-browser.cjs tests/workflow-restart-browser.cjs
```

```bash
npm install --prefix .test-tmp/browser-tools --ignore-scripts --no-audit --no-fund puppeteer-core@25.16.0
export NODE_PATH="$PWD/.test-tmp/browser-tools/node_modules"
export NAJDILAB_BROWSER_EXECUTABLE="$(command -v google-chrome)"
node --test --test-concurrency=1 tests/guided-workspace-browser.cjs tests/legacy-workspace-browser.cjs tests/workflow-restart-browser.cjs
```

Select the actual Chromium executable on systems using another binary name. These fixtures use new temporary databases and random loopback ports. Run the full suite with `-rs` to retain optional-engine/private-artifact skip reasons. The [documentation screenshot procedure](screenshots.md#reproduction) publishes selected current captures.

## Continuous integration policy

`Source checks` (Windows and Ubuntu: Python suite, Node unit tests, Chromium acceptance) and `Source-only candidate` (packaged Core on Windows and Ubuntu) are heavy. To avoid spending runner time on every intermediate commit:

- Pushes to a **draft** pull request start no heavy job. Run local checks first: `python -m pytest -q tests -rs`, `node --test tests/*.test.cjs` and the Chromium suites with `NAJDILAB_BROWSER_EXECUTABLE` and `NODE_PATH` set.
- To verify a specific draft HEAD on hosted Windows and Ubuntu, start both workflows manually from the Actions tab (**Run workflow** on the branch), or with `gh workflow run checks.yml --ref <branch>` and `gh workflow run public-source-candidate.yml --ref <branch>`. GitHub offers manual runs only once the `workflow_dispatch` trigger exists on the default branch; if manual dispatch is unavailable, record hosted checks as unavailable and retain the authorized Draft status.
- Opening a PR, marking it **Ready for review**, every push to a ready PR, and every push to `main` run the full matrix automatically.
- A newer run for the same PR or ref cancels the older one (`concurrency`). Jobs time out after 30 minutes and each Chromium step after 10.
- Every `tests/*.test.cjs` must be listed in `checks.yml`; `tests/test_ci_workflows.py` fails otherwise.

A skipped job on a draft is not a pass. Merge decisions require a completed green run on the final HEAD.

## Debugging, logs and first contribution

Use a free NAJDILAB_PORT and no-demo launch. `python -m pdb scripts/launch.py` supports backend debugging with the selected supported interpreter; continuing can initialize this checkout's DB. Browser developer tools inspect plain JS. Local tracebacks may contain private paths/content; redact before sharing. Never log real bearer secrets, conversation HMAC payloads or session values in public issues.

Read [architecture](architecture.md), [code map](codebase-navigation.md), [API](api-reference.md), [migrations](database-and-migrations.md) and [standards](../CONTRIBUTING.md). Create `git switch -c codex/short-purpose`; reproduce a defect with synthetic proof, change the owning layer, run focused and full checks, update docs/status and the relevant result record and inspect git diff --check plus staged files. Preserve Arabic data/API/schema/masks. Submit a PR with rollback and approval gates, not an implicit deployment.

## Extending one endpoint safely

1. Locate the existing route in `docs/api-routes.md` and `app/server.py`; choose the responsible service/dataset/Chat module using the code map.
2. Specify the input fields, structured errors, state changes and approval requirements. Add a synthetic test in the owning test file using a temporary database/directory; never use historical IDs as fabricated evidence.
3. Keep HTTP security before dispatch and enforce authorization in the owning operation. Use SQL parameters, path containment and argv-based subprocess calls; avoid shell interpolation. Preserve Arabic content and API compatibility.
4. Run focused tests, then the available full source suite with `-rs`; update the API inventory through `python scripts/generate_api_reference.py`, relevant English docs/status/changelog and worklog. Run `python scripts/check_docs.py` and inspect staged files.
5. Submit a Draft PR with observed results, skips, security/data impact and ordinary-revert rollback. Schema, engine-consent and installed-update changes retain their own explicit scope.

For a disposable app, use a fresh checkout and a free port; port selection alone does not separate database paths. Existing startup migrations may run only against that disposable state during tests. Missing private historical fixtures must remain explicit skips. [Current evidence](verification-evidence.md) records reproducible commands and environment limits.
