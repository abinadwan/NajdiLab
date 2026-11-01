# Developer setup and first change

Clone the authorized private repository on the default `main` branch and read [PROJECT_STATUS](../PROJECT_STATUS.md). The earlier preparation branches have been merged and deleted; do not select them. Use a disposable checkout; no tests/tools may target production. Follow [installation](installation.md). The local application has no frontend build or core package installation. For the separate reduced source-only candidate, use [Core onboarding](public-core-user-guide.md).

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

## Debugging, logs and first contribution

Use a free NAJDILAB_PORT and no-demo launch. `python -m pdb scripts/launch.py` supports backend debugging with the selected supported interpreter; continuing can initialize this checkout's DB. Browser developer tools inspect plain JS. Local tracebacks may contain private paths/content; redact before sharing. Never log real bearer secrets, conversation HMAC payloads or session values in public issues.

Read [architecture](architecture.md), [code map](codebase-navigation.md), [API](api-reference.md), [migrations](database-and-migrations.md) and [standards](../CONTRIBUTING.md). Create `git switch -c fix/short-purpose`; reproduce a defect with synthetic proof, change the owning layer, run focused and full checks, update docs/status and the relevant result record and inspect git diff --check plus staged files. Preserve Arabic data/API/schema/masks. Submit a PR with rollback and approval gates, not an implicit deployment.

## Extending one endpoint safely

1. Locate the existing route in `docs/api-routes.md` and `app/server.py`; choose the responsible service/dataset/Chat module using the code map.
2. Specify the input fields, structured errors, state changes and approval requirements. Add a synthetic test in the owning test file using a temporary database/directory; never use historical IDs as fabricated evidence.
3. Keep HTTP security before dispatch and enforce authorization in the owning operation. Use SQL parameters, path containment and argv-based subprocess calls; avoid shell interpolation. Preserve Arabic content and API compatibility.
4. Run focused tests, then the available full source suite with `-rs`; update the API inventory through `python scripts/generate_api_reference.py`, relevant English docs/status/changelog and worklog. Run `python scripts/check_docs.py` and inspect staged files.
5. Submit a Draft PR with observed results, skips, security/data impact and ordinary-revert rollback. Schema, engine-consent and installed-update changes retain their own explicit scope.

For a disposable app, use a fresh checkout and a free port; port selection alone does not separate database paths. Existing startup migrations may run only against that disposable state during tests. Missing private historical fixtures must remain explicit skips. [Current evidence](verification-evidence.md) records reproducible commands and environment limits.
