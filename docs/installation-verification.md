# Installation verification — 2026-10-27

Historical installation record. Current combined-branch checks and updated repository state are in [unified verification](unified-readiness-verification.md). PR #1 is now merged; final paragraphs below describe the earlier delivery state.

All operations used disposable source-only checkouts, paths containing spaces, fresh databases, synthetic content and separate/free loopback ports. Production/Hermes/training services and the existing backup volume were not operated. Exact private paths/logs are excluded from Git.

| Environment / check | Commands / actual result |
|---|---|
| Windows 11, Python 3.12.10, SQLite 3.49.1 | python scripts/install.py --check; scripts/install.ps1 twice: PASS, no DB created, no dependencies downloaded |
| Windows actual launcher | run.ps1 selected local .venv, no-demo default, health 200 with matching checkout, migrations 001–004, zero messages: PASS |
| Windows port conflict / shutdown | Second launcher refused busy test port; Ctrl+C printed NajdiLab stopped. PowerShell interruption returned nonzero as expected; no unrelated process stopped |
| Windows optional developer tooling | .venv/Scripts/python.exe -m ensurepip then -m pip install -r requirements-dev.txt: PASS in disposable venv; this separate step downloads test tooling |
| Ubuntu 24.04 / WSL2, Python 3.12.3, SQLite 3.45.1 | python3 scripts/install.py --check; sh scripts/install.sh, repeated and after app shutdown: PASS; settings/DB bytes preserved |
| POSIX script validation | sh -n and bash -n on each run.sh / scripts/install.sh: PASS |
| Ubuntu/WSL launch/health/conflict/shutdown | sh ./run.sh using venv/free port; health identity and zero demo rows; conflicting launch rejected; SIGINT/Ctrl+C path printed stopped, exit 0: PASS |
| Ingest example / Arabic / idempotency | Approved mandatory secret, conversation_id payload with synthetic Arabic; exact stored/read text; repeat source_message_id returned duplicate: PASS |
| SQLite online backup/restore, both OS test instances | Built-in scripts/backup.py, live online snapshot, ZIP read/CRC, SHA256 per member/archive, isolated extraction, integrity_check=ok, FK errors=0, table counts match: PASS |
| Read-only setup / incomplete venv / unsupported Python / permission error | Eight regression cases observed RED then GREEN; permission denial injected before writes; unsupported-version probe simulated Python 3.10; broken/missing executable rejected, existing state preserved |
| Clean source-only Windows suite | python -m pytest -q tests -rs -p no:cacheprovider: 278 passed, 23 explicit private-artifact skips, 68 subtests, one pre-existing warning |
| Full authorized fixture-copy suite | Same command in isolated development checkout: 301 passed, 68 subtests, one existing return-value warning |
| Documentation / API | python scripts/check_docs.py; python scripts/generate_api_reference.py --check: PASS |

The preceding source-only baseline failed 24 historical integration cases; its log is retained privately. Twenty-three checks now declare private-artifact dependencies. One missing-path test now supplies its own temporary empty registry and passes. No private data was added and no present-but-invalid fixture is treated as success.

Not tested/certified: bare-metal Linux, OS/WSL provisioning, macOS, older Windows/browsers, every Python >=3.11, real GPU training, package compatibility across ML runtimes, production update/deployment, existing full private backup recovery, destructive uninstallation or live database migrations. Core startup is verified on Windows and Ubuntu within WSL only; other environments are experimental/unverified. Safe retirement guidance was reviewed but no deletion performed. Hosted Actions source checks passed on Ubuntu 24.04 (Python 3.12.15) and Windows Server 2025 image (Python 3.12.10). This verifies hosted source tests, not arbitrary native-Linux deployment or bare-metal hardware.

Built-in backup scope is SQLite plus exports, demonstrated using synthetic data. This rehearsal does not certify the existing full private backup, model weights, adapters or external runtimes; those need the separately documented full inventory/hash/restore gates. All 317 protected original artifact hashes matched. Existing production and backup are preserved; no deletion approval is given.

## GitHub delivery and hosted checks

Draft PR: https://github.com/abinadwan/NajdiLab/pull/1 . Ordinary branch push succeeded; main remains the original baseline and repository visibility was verified Private. A real independent GitHub clone passed git fsck, local setup, documentation verification, source-only tests and its actual launcher/health/shutdown using a separate test port/database. No merge or publication occurred.

Hosted source-check run: https://github.com/abinadwan/NajdiLab/actions/runs/40451855276 . Windows: 278 passed, 23 historical skips, 68 subtests; Ubuntu: 277 passed, 24 skips (the additional case is explicitly Windows-only), 68 subtests. Both have the one pre-existing return-value warning. The initial failed run is retained: it exposed canonical long/short Windows temp-path comparison and a chmod fault-injection stub lacking standard-library keyword forwarding. Those test-harness defects were fixed; deployment logic was unchanged.
