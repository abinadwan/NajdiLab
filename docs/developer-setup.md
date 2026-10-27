# Developer setup and first change

Clone the authorized source, select the preparation branch while unmerged and read [PROJECT_STATUS](../PROJECT_STATUS.md). Use a disposable checkout; no tests/tools may target production. Follow [installation](installation.md). There is no frontend build or core package installation.

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

Synthetic fixtures are included. Specific historical tests declare private file prerequisites via tests/private_artifacts.py. Missing files produce explicit SKIP reasons; present-but-corrupt files still fail. Read -rs; never report skips as passes or reconstruct/publish private data. Authorized maintainers can restore verified private copies to ignored paths for full checks. Original missing-fixture failures and final counts are in [verification](verification-and-readiness-report.md).

`python -m unittest discover -s tests -v` is supplementary: it omits function-style pytest cases. Tests create temporary databases and patch paths; understand imports before running historical utilities. Training/download/deployment is never onboarding or CI.

## Debugging, logs and first contribution

Use a free NAJDILAB_PORT and no-demo launch. `python -m pdb scripts/launch.py` supports backend debugging with the selected supported interpreter; continuing can initialize this checkout's DB. Browser developer tools inspect plain JS. Local tracebacks may contain private paths/content; redact before sharing. Never log real bearer secrets, conversation HMAC payloads or session values in public issues.

Read [architecture](architecture.md), [code map](codebase-navigation.md), [API](api-reference.md), [migrations](database-and-migrations.md) and [standards](../CONTRIBUTING.md). Create `git switch -c fix/short-purpose`; reproduce a defect with synthetic proof, change the owning layer, run focused and full checks, update docs/status/worklog and inspect git diff --check plus staged files. Preserve Arabic data/API/schema/masks. Submit a PR with rollback and approval gates, not an implicit deployment.
