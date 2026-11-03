# Installation and operation

Install only a reviewed source revision for local Chat/review/datasets. Follow the [dataset roadmap](roadmap.md) and [Chat/export contract](chat-workspace.md). This cleanup does not update the installed application or alter existing private data.

Read [requirements](system-requirements.md) and [actual verification](verification-evidence.md). Core app uses Python 3.11+ and SQLite standard library, independently of Hermes, Ollama, GPU/CUDA and models. GitHub access remains private; source-license approval is pending.

## Clone source

```bash
git clone https://github.com/abinadwan/NajdiLab.git
cd NajdiLab
```

The default `main` branch already contains the private preparation changes through [merged PR #5](https://github.com/abinadwan/NajdiLab/pull/5). The deleted `dev/*` branches are not installation targets. A clone downloads code; it does not install dependencies or restore data. These commands operate the main local application, **not** the separately built [reduced Core candidate](public-core-user-guide.md). The repository remains private, and public release is not authorized.

## Windows PowerShell

Install an approved Python distribution with sqlite3/venv and Git. From the checkout:

```powershell
python --version
Get-Content .\scripts\install.ps1
python .\scripts\install.py --check
.\scripts\install.ps1
.\run.ps1
```

If script policy blocks reviewed local scripts, use `python .\scripts\install.py` and `.\.venv\Scripts\python.exe .\scripts\launch.py` directly. A process-scoped policy change is an alternative for a reviewed script; do not weaken machine-wide policy. No elevation needed. run.cmd wraps the PowerShell launcher.

## Managed llama.cpp runtime (optional, for NajdiLab Native)

Setup asks, after the steps above, whether to install the llama.cpp program that NajdiLab Native uses. It first explains what it will read (operating system, NVIDIA GPU, compute capability, driver CUDA version, locally with `nvidia-smi`) and asks; then it shows the chosen package, every file with its size, source and SHA-256, the destination and space needed, and the licenses, and asks again. Nothing is downloaded without both answers being yes, and non-interactive runs never download.

```powershell
.\scripts\install.ps1 -Runtime     # only the runtime step
.\scripts\install.ps1 -NoRuntime   # skip it
```

The same is available in the app: **Model library → llama.cpp runtime**. Offline: copy the pinned archives (names and hashes in `app/runtime_catalog.py`) into `data/native/runtime/archives/` first; installation verifies them and downloads nothing. Details, rollback and licenses: [Managed llama.cpp runtime](development/MANAGED_RUNTIME.md). Cloning the source does not include any binary.

## Linux / WSL2

Use an existing approved WSL2 distribution, its Linux filesystem and its own Python. WSL installation is a separate OS operation; use a separate disposable environment for evaluation. If missing, install Python 3.11+ with sqlite3/venv through normal distribution administration.

```bash
python3 --version
cat scripts/install.sh
python3 scripts/install.py --check
sh ./scripts/install.sh
sh ./run.sh
```

`sh` needs no executable bit; optional `chmod +x scripts/install.sh run.sh` permits direct invocation. POSIX scripts also parse with bash. Consult verification limits before assuming other platforms are supported.

## Setup behavior

Shared scripts/install.py detects Windows/POSIX venv layout, checks Python/SQLite/source, creates .venv without pip/network downloads, verifies that interpreter, creates local state directories and copies .env.example only if .env does not exist. Settings, databases and complete venvs are preserved. An incomplete venv fails clearly, never silently replaced. Repeated setup never initializes/migrates a DB. `--check` creates no DB/config/environment (normal Python bytecode caches can occur).

**The app does not load .env.** Set variables in the launching shell; see [configuration](configuration.md). Core needs no third-party package; test tooling is separate in [developer setup](developer-setup.md).

## Launch, health and shutdown

Launchers choose explicit NAJDILAB_PYTHON, otherwise this checkout's .venv, otherwise available Python only when no venv exists. They validate interpreter/port before server import. Demo seeding defaults off in launchers; explicit NAJDILAB_NO_DEMO=0 enables samples in a disposable instance. Direct `python -m app.server` retains historical demo-on behavior unless NAJDILAB_NO_DEMO=1 is set.

Open http://127.0.0.1:8770 and /api/v1/health. First launch creates data/najdilab.db, applies SQL already in migrations and initializes local dataset metadata. It does not initialize a training registry. Proposed plans SQL is not setup. Launch is not read-only and must not target production for evaluation. Collection fails closed until an Ingest secret matches the client.

Choose a separate test port: PowerShell `$env:NAJDILAB_PORT='8870'`, or POSIX `NAJDILAB_PORT=8870 sh ./run.sh`. On conflict choose a free port; never kill an unknown listener. Ctrl+C in the launching terminal stops that instance. No HTTP shutdown/global service installer is provided. Do not stop an unrelated application or service.

## Manual setup, update and reinstall

Without venv creation, select a supported interpreter using NAJDILAB_PYTHON and run scripts/install.py --check; core pip installation is unnecessary. Repair a broken venv only by deliberate action after preserving it.

Before updating, verify a full private backup/restore, record git status/revision, preserve edits on a branch, review incoming changes/migrations, then use `git pull --ff-only` on the intended clean branch. Non-fast-forward means stop for review; never reset work. Test setup/checks in isolation, obtain operational approval, then deliberately update the intended instance. This task did not operate production.

A fresh clone does not recover DB, Chat history, dataset versions or private evidence. Follow [restore guide](backup-and-restore.md), restore into a separate directory and verify hashes, integrity/FKs, counts and migrations before launch. Do not copy live WAL/SHM.

## Safe uninstallation

Setup registers no global service/package/task. Before retirement verify source plus complete private restoration, close only the intended app after operational approval, archive settings/state, then review the exact folder before any eventual removal. No automatic delete command is provided. Keep Hermes/old data until recovery is proved; this guide grants no deletion approval. See [troubleshooting](troubleshooting.md) and [shell commands](shell-commands.md).
