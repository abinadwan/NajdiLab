# Restoring the preserved presentation for development

Historical / Archived Documentation

Use an isolated synthetic instance. The supported helper creates a new child of this checkout's ignored `.test-tmp` directory. It refuses existing destinations and paths outside that boundary. It copies static source and patches one initialization call in the copy. Databases, model files and the official static tree are outside that operation.

## Reproduce the restoration test

Install the development test prerequisites described in the [developer guide](../../developer-setup.md). From the repository root, run the real Chromium acceptance.

```powershell
$env:NODE_PATH=(Resolve-Path '.test-tmp/browser-tools/node_modules').Path
$env:NAJDILAB_BROWSER_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
node --test tests/legacy-workspace-browser.cjs
```

The test creates a unique marked static copy, launches `tests/chat_browser_fixture.py` with a new synthetic database and random loopback port, restores the old presentation in English and Arabic, visits every tool, returns to the Wizard, reloads the old mode and verifies the original `static/app.js` digest. It checks JavaScript and HTTP 500 failures.

## Inspect a temporary restored instance

Choose a new output name for each run.

```powershell
python scripts/restore_advanced_workspace.py --output .test-tmp/legacy-preview
python -u tests/chat_browser_fixture.py --static-root .test-tmp/legacy-preview
```

Open the `BROWSER_FIXTURE` URL printed by the fixture and navigate to `/datasets/prepare`. The restored shell includes the original Advanced Mode control. Close that test process with Ctrl+C when finished. The fixture's default database is ephemeral.

The fixture accepts `--static-root` only for a marked restoration beneath `.test-tmp`. Production server flags are unchanged. The helper is a development restoration procedure, with no official user navigation entry.

## Reintroducing the presentation in future source work

Review the archived reference commit and current shared APIs. A future product change can explicitly invoke `restoreWorkspace` during initialization and add a supported navigation policy. Re-run the preserved browser test and all Wizard, privacy, split, Frozen and deletion regressions. Review storage behavior, accessibility and localization before treating the presentation as supported again.

The source module alone is insufficient for a standalone application. It relies on the templates, CSS, current shared JavaScript and backend operations listed in [the architecture](ARCHITECTURE.md).
