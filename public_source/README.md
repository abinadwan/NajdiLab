# NajdiLab Core

**Hermes security correction (2026-10-31):** the Hermes HTTP receiver is BLOCKED before body reading because Hermes v0.22.5 sender filtering and external disconnect are unverified. Credentials/legacy mode cannot reopen it. This profile still excludes model execution and Settings runtime integrations; no publication/license approval is implied. See [API](docs/api.md).

NajdiLab Core is a local-first workspace for collecting authorized conversations, reviewing Arabic/Najdi responses and preparing traceable datasets. It keeps original messages separate from human corrections, privacy flags and eligibility decisions.

It is for dataset curators, reviewers and developers who want to understand what entered a dataset and why. The browser workflow connects conversation context → explicit review → readiness and quality checks → a new local dataset version with integrity hashes.

**NajdiLab Core is a dataset review and preparation platform, not a complete model-training or inference runtime.** It runs without a GPU, Hermes, Ollama, model weights or an ML framework. Training, historical research and deployment remain unavailable.

**Private engineering candidate — NOT READY — BLOCKERS REMAIN.** Source ownership, license and exact redistribution approval are unresolved. No active source license, public package or permission to publish is supplied. Original project: [NajdiLab](https://github.com/abinadwan/NajdiLab), currently Private and requiring authorized access.

## Explore

- [Practical user guide](docs/user-guide.md): fictional Arabic review-to-dataset journey.
- [Core architecture](docs/architecture.md): editable SVG, storage and security boundaries.
- [Actual interface screenshots](docs/screenshots.md): real application, synthetic data only.
- [Exact API scope](docs/api.md), [contributor guidance](CONTRIBUTING.md).
- [Historical initial profile](../docs/verification-evidence.md): retained evidence, superseded instructions.

## Included scope

Contextual conversation inspection/search; pending/reviewed/eligible/excluded/evaluation filters; original-preserving corrections, approve/exclude/restore; explicit privacy/eligibility flags; mandatory server-side stale-save protection; read-only readiness/dedup/quality/balance/holdout inspection; version preparation and manifest/hash inspection; selected JSONL downloads; coherent private backup and separate validated restore.

Deferred: manual direct/preference editing/preparation, bulk management, model configuration, offline model planning, general human model comparison, canonical registry/events and proposed SQL. No runtime probing, model acquisition, training, merge, quantization or deployment. Native tool training requires separate support. Private dataset/research evidence is not included.

## Requirements and official prerequisites

| Technology | Required / verified evidence | Official source |
|---|---|---|
| Python | Minimum: 3.11; observed local 3.12.14, hosted Windows 3.12.10 / Ubuntu 3.12.15; acceptance status below | [Python downloads](https://www.python.org/downloads/) |
| SQLite | Minimum: 3.24 via Python sqlite3; observed local 3.53.1, hosted Windows 3.49.1 / Ubuntu 3.45.1 | [SQLite](https://www.sqlite.org/index.html) |
| Browser | Current Chromium tested; other modern browsers require independent validation | [Chromium](https://www.chromium.org/) |
| Git | Only needed for authorized engineering checkout, not a generated candidate | [Git downloads](https://git-scm.com/downloads/) |
| Windows / Linux | Local Linux exercised; Windows/Ubuntu hosted outcomes are recorded separately in verification | Existing Linux/WSL only; no OS provisioning |

Core uses Python's standard library and HTML/CSS/JavaScript without a frontend build step. No Administrator/sudo is required for an ordinary writable checkout. True minimum CPU/RAM/disk has not been benchmarked. Dataset inspection/backup/restore is bounded to 16 MiB per file and 64 MiB aggregate; this is a safety limit, not a hardware minimum. Keep space for source, venv, DB, each version and separate backups. The optional pytest/Node/browser tools below are development tools, not application dependencies. Python/SQLite versions are distinct from dataset identifiers; no software release number is assigned.

## Build first, then install the exact candidate

These instructions run **inside the generated candidate**, identified by MANIFEST.json with profile source-only-engineering-candidate. The engineering repository's root launcher starts the preserved original application. Do not confuse those profiles.

An authorized developer builds from the reviewed implementation checkout:

```sh
python public_source/build.py --output ../najdilab-core-candidate
python public_source/build.py --verify ../najdilab-core-candidate
cd ../najdilab-core-candidate
```

Output must be a new separate directory. The builder selects reviewed hash-pinned files, excludes Git/private artifacts and refuses unknown source. This is not publication. Preserve a pristine copy for verification; installation and runtime caches/state intentionally make a used copy fail pristine verification.

### Windows PowerShell

```powershell
python --version
Get-Content .\scripts\install.ps1, .\scripts\install.py
.\scripts\install.ps1
.\.venv\Scripts\python.exe .\scripts\synthetic_demo.py --confirm-disposable --workshop
.\run.ps1
```

### Linux / Ubuntu / WSL

```sh
python3 --version
cat scripts/install.sh scripts/install.py
sh scripts/install.sh
.venv/bin/python scripts/synthetic_demo.py --confirm-disposable --workshop
sh run.sh
```

The synthetic command is **optional** and only works before the first launch on a fresh disposable candidate. It creates 32 independently fictional pending conversations, never approvals. Omit --workshop for the preserved two-row demo; that tiny set cannot satisfy current preparation gates. Existing DBs are refused; startup never seeds examples. No installer downloads models or ML packages.

Open http://127.0.0.1:8770. Ctrl+C stops that instance. Set NAJDILAB_PORT in the launching shell for another free port. A different port does not isolate storage: a second server for the same root is refused by an OS lock. An OS may retain a recently closed port; wait or select another free port. Run each independent test instance in its own checkout/storage.

Setup creates an offline no-pip venv and preserves settings/state; repeated setup does not reset the DB. First launch initializes only existing migrations 001–004. Proposed SQL is absent. .env is a template/reference and is **not automatically loaded**. Native ingestion needs a privately configured NAJDILAB_INGEST_TOKEN bearer/HMAC credential; browser mutation uses a process-local CSRF token. Never commit a real credential.

## Review and prepare

1. Open Conversations and inspect the user question/context and original response. Select Review this response.
2. Existing correction/type/notes/flags are loaded. Correct or approve deliberately. Editing text preserves omitted flags; enabling privacy/evaluation/exclusion/fact-check restrictions forces training eligibility off.
3. Select Training eligible only after actual review and rights/privacy assessment. This checkbox is not consent. Save, reopen and inspect the saved state.
4. A stale save returns409 without writes. Your draft stays visible; reload explicitly and compare. The server requires expected_updated_at on **every** review mutation.
5. Exclude preserves the original and any correction. Restore preserves restrictions and leaves PENDING/ineligible. A restored retained correction must be resolved explicitly before another exclusion; it is never silently replaced. Complete append-only event history is not implemented.
6. Open Dataset readiness. Demo inclusion defaults off. Inspect pending, excluded/evaluation records, blockers, duplicate candidates and holdout evidence. Restricted earlier context blocks later targets; it is never silently stripped.
7. Preparation requires at least 20 final records, three holdout conversations, a 10–15% holdout, valid review/source/mask/privacy/dedup checks and no conflicting targets. Manual direct/preference kinds block before writes. Near-duplicate warnings require human review; no automatic near-match deletion.
8. Prepare a new local version, then inspect its files, counts, SHA256, quality/balance and holdout. READY means implemented dataset checks passed; it does not authorize model execution or redistribution.
9. Choose one permitted JSONL download and confirm its private-data warning. Full archives, DBs, credentials, backups and models are never downloadable through this route.

See the [user guide](docs/user-guide.md) and [API](docs/api.md) for details. Generated data stays private by default. The unchanged export algorithm also writes full_archive.json containing all local records, including excluded ones: retain it privately for recovery, never publish the exports directory or backup blindly. Changing a review does not rewrite earlier versions; derive a newly reviewed version rather than altering history.

## Backup and separate restore

From this candidate:

```sh
python scripts/backup.py
python scripts/restore_backup.py backups/CHOSEN-BACKUP.zip --output ../core-restored-snapshot --confirm-disposable
```

Replace CHOSEN-BACKUP.zip with the actual printed filename. The new backup wrapper snapshots SQLite and copies only that snapshot's registered, verified version files; temporary/unregistered files are excluded. It does not bundle models, external runtimes, source/venv/configuration or a full research installation.

Restore requires a new destination outside this candidate, validates ZIP safety/CRC, SQLite integrity/FKs, registry/manifests/file hashes/counts and refuses overwrite. Keep the original backup. A failed IO operation can leave .RESTORE_INCOMPLETE in its newly reserved destination; do not launch or copy from that result. Choose a different new destination after resolving the cause.

To resume, build a **second fresh candidate** and, **before installing**, copy the validated restored data and exports directories only when those destination directories do not already exist. Then run the installer without demo creation and launch the same-schema candidate; installation preserves existing state. Preserve the backup and original candidate. Do not copy over an initialized DB or activate migrations. Do not use this guide to move protected historical research without a separately reviewed compatibility plan. Restore integrity is separate from dataset quality; a semantically blocked version remains blocked.

## Security and limitations

Trusted local single-operator tool on loopback; no public/shared network hosting or multi-user RBAC. Host/Origin/Fetch Metadata, CSRF, JSON framing/2MiB request limit, credentialed native Ingest, safe DOM rendering and filesystem constraints apply. HMAC has no replay freshness. Core refuses native ingestion with503 when the legacy unauthenticated override is inherited; remove it and configure credentials. Local programs can obtain intent sessions. No protection against an administrator deliberately rewriting the DB/files outside the application is claimed.

One server process per storage root and serialized supported HTTP mutations keep preparation coherent. Backup uses its own SQLite snapshot. Original startup migration-loader debt remains; no proposed event/registry migrations are enabled. Review identity is an assertion, not authenticated user identity. No automatic PII detection, consent verification, linguistic quality certification or model compatibility guarantee. Diagnostics may reveal your local record identifiers/content; do not share them without review.

## Testing and contributing

Run in a disposable copy of the exact candidate:

```sh
python -m unittest discover -s tests -p test_candidate_contract.py
python -m ensurepip
python -m pip install -r requirements-dev.txt
python -m pytest -q tests -rs
```

Full developer verification includes separate builder, exact-candidate, browser and preserved-original suites. Browser tests require separately installed Node 22+ and puppeteer-core 25.16.0 plus an explicit Chromium/Chrome executable. No browser/runtime binary is bundled:

```sh
npm install --prefix ../core-browser-tools puppeteer-core@25.16.0
NODE_PATH=../core-browser-tools/node_modules node tests/harness.cjs
node tests/browser.cjs .
```

Set NAJDILAB_BROWSER_EXECUTABLE for your installed browser. Windows PowerShell: set $env:NODE_PATH and $env:NAJDILAB_BROWSER_EXECUTABLE in the session, then run node. Consult the [Phase5 engineering verification](https://github.com/abinadwan/NajdiLab/blob/a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9/docs/public-core-phase5-verification.md) for actual hosted Windows/Ubuntu outcomes, failures, counts and exact tested commits; observed versions alone are not full acceptance. Browser fixtures/demonstrations are synthetic; none is historical research evidence. See [contribution guidance](CONTRIBUTING.md). No training is needed for any acceptance test.

## Troubleshooting and updates

- Missing Python/old SQLite: install an appropriate official Python build; inspect version checks before setup.
- Port busy: stop only your disposable instance or select a free port; never restart another service automatically.
- Storage already used: stop the first Core server; changing ports alone is insufficient. The lock is released by the OS on exit; do not delete lock files to bypass it.
- Existing demo DB: use a new candidate; the fixture refuses overwrite intentionally.
- 409 conflict: inspect/reload saved review, compare draft and save with the new token.
- Preparation blocked: read findings; tiny/unresolved/private/conflicting records must not bypass gates.
- Version integrity failure: preserve evidence and restore/rebuild from a verified backup into another location; do not edit hashes to force PASS.
- Pristine verification fails after launch: runtime files are expected; compare a clean build instead.

For an update, back up and validate restore first, review the new source manifest and migration compatibility, install into another new candidate and test synthetic acceptance before moving authorized state. Do not overwrite an existing installation or use the original private project's data automatically. License, attribution and publication approvals remain owner decisions.

The Python and browser acceptance harnesses require a hash-verified candidate manifest and copy only its selected source into new disposable storage. They refuse a missing/invalid manifest or changed selected file before running setup. Unlisted local state is never copied. This integrity check is not a signature or redistribution approval. Unsupported HTTP methods return controlled405 (HEAD has no body) after Host/Origin/CSRF checks.

Core refuses native ingestion with503 LEGACY_INGEST_DISABLED whenever NAJDILAB_ALLOW_LEGACY_INGEST=1 is inherited, even if a credential is also supplied. Remove that legacy override and configure bearer/HMAC authentication; browser review remains available. This candidate-only refusal does not change the original shared security module or production transition.
