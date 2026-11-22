# Shell commands for beginners

Run commands in your own disposable checkout unless a row says otherwise. Shells interpret syntax differently: use PowerShell examples on Windows, POSIX sh/bash in Linux/WSL. Quotes preserve spaces. Never paste private credentials into shared transcripts. A successful clone is code acquisition, not setup or restoration.

| Command / PowerShell equivalent | What and why | Where / expected result | Common error and safe recovery |
|---|---|---|---|
| git clone URL | Download source/history for installation | Parent workspace; new repository folder | Access denied: obtain private repo access; do not expose credentials. Existing destination: inspect it, use another new folder |
| git status | Show branch and edits before changing code | Checkout; clean or explicit file list | Not a repository: check pwd and cd; do not initialize unrelated folders |
| git pull --ff-only | Update without manufacturing a merge | Intended clean branch after backup/review; advances to descendant | Divergence/edits: stop and preserve work, review history; never force/reset |
| git switch NAME / git checkout NAME | Select an existing branch | Checkout; confirms branch | Unknown name: fetch authorized refs and inspect; changed files blocking switch: preserve on branch first |
| git switch -c fix/name | Create scoped development branch | Clean intended base; new branch | Name exists: inspect/use it or choose a new name |
| cd PATH / Set-Location -LiteralPath PATH | Change working directory | Any shell; next commands operate there | Spaces/missing path: quote literal path, inspect before retry |
| pwd / Get-Location | Identify current directory | Any shell; absolute location | Unexpected location: navigate deliberately before writes |
| ls / Get-ChildItem | List files before operating | Any directory; filenames | Access denied: select an authorized directory, no automatic elevation |
| mkdir NAME / New-Item -ItemType Directory -Path NAME | Create a local directory | Chosen parent; new folder | Already exists: inspect and reuse intentionally, never delete automatically |
| python --version / python3 --version | Check interpreter identity | Before setup; 3.11+ | Missing/Store alias/old version: select supported installed Python; Get-Command helps |
| Get-Command python | Resolve PowerShell executable | Any directory; Source path | Not found: correct PATH or use explicit approved executable |
| python3 -m venv .venv / python -m venv .venv | Standard manual isolated environment | Disposable checkout; environment folder | venv support missing: install normal OS prerequisite. Existing broken environment: preserve before explicit repair; recommended installer refuses replacement |
| source .venv/bin/activate / . .venv/bin/activate | Select venv in bash / POSIX sh | Checkout; PATH changes in this shell | Wrong shell/path: use correct form or explicit .venv/bin/python. Activation is optional |
| . .\.venv\Scripts\Activate.ps1 | Optional PowerShell activation | Checkout; interpreter PATH changes | Policy blocks: use explicit interpreter instead; avoid machine-wide policy changes |
| chmod +x run.sh | Add executable permission | Linux checkout; enables ./run.sh | Wrong filesystem permissions: use sh ./run.sh; do not recursively chmod state |
| sh ./scripts/install.sh | Execute reviewed POSIX setup | Checkout; isolated environment, no DB migration, optional runtime download only after approval | Runtime/permission error: read message, choose writable checkout/supported Python; repeat preserves settings |
| bash -n run.sh | Parse without launching | Linux/WSL checkout; no output on success | Syntax error: inspect reported line; do not run until fixed. sh -n also checks POSIX shell |
| python -m pip install -r requirements-dev.txt | Install optional test runner, not core dependency | Intended dev venv only; package install | pip missing: approved ensurepip/OS package. Offline failure: preserve app, install test tooling later; never disable TLS |
| $env:NAME='value' / export NAME='value' | Set variable for current shell/children | Before launch; configure port/no-demo/token | Wrong syntax: use correct shell; .env is not automatically read. Avoid real secret transcripts |
| $env:NAJDILAB_PYTHON='path' / export NAJDILAB_PYTHON='path' | Explicit launcher interpreter | Before run; overrides local venv | Bad path: inspect executable/version, remove override to use valid venv |
| .\run.ps1 / sh ./run.sh | Launch this checkout | Checkout; URL and DB printed | Port busy: choose unused port; never terminate unknown process |
| Ctrl+C | Supported terminal shutdown of this instance | Its launching terminal; stopped message/process exit | Wrong terminal: identify intended instance first. No global service stop command is part of setup |
| $LASTEXITCODE / echo "$?" | Inspect most recent native command exit | Immediately after command; 0 success, nonzero failure | A later command overwrites value; record immediately. Ctrl+C codes can differ by shell |

PowerShell script policy: inspect Get-ExecutionPolicy -List if a reviewed local script is blocked. Prefer explicit Python commands or, if permitted, a process-scoped policy for that session; do not run remote scripts with Invoke-Expression. Shell scripts here can be read before execution; no curl-pipe-shell workflow is recommended. Updating/stopping/reinstalling production requires separate operational approval and verified restoration, even if commands are familiar.
