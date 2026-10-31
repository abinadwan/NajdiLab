# Windows update and rollback — only after PR approval and merge

Do not run these installation steps while the PR is open. Review the final diff, obtain owner merge approval, merge through GitHub, and confirm the exact merged commit has green Linux/Windows CI first. This is guidance only; development did not touch the installed checkout, credentials or running services.

Commands support Windows PowerShell 5.1 and PowerShell 7. Use your trusted private console. Never publish backup contents, environment variables or private logs.

## 1. Inspect and stop safely

Finish active reviews/jobs first. Stop only the intended NajdiLab instance through its own normal console/launcher when safe; do not kill Python globally or stop Hermes, Ollama, LM Studio, workers or other services. If a training job or unknown writer is active, postpone updating. Existing Hermes outbound configuration needs a separate private operational review; `enabled:false` does not prove delivery stopped.

```powershell
$repo = Join-Path $env:USERPROFILE 'Documents\NajdiLab'
Set-Location -LiteralPath $repo
git status --short --branch
if ($LASTEXITCODE -ne 0) { throw 'Not the intended Git checkout.' }
git remote get-url origin
git branch --show-current
$before = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot record recovery commit.' }
$changes = @(git status --porcelain)
if ($changes.Count -gt 0) { throw 'Preserve and review local changes/untracked files first. Do not reset, clean or stash blindly.' }
```

Verify the remote is `abinadwan/NajdiLab` and the branch is the intended `main`. Review ignored local data/config too: clean Git status does not mean no private data exists. Never overwrite a different checkout to force a match.

## 2. Back up before code changes or startup

Choose private local storage with enough free space. The folder below is outside the repository. Preserve separately configured model/dataset locations under your existing backup policy; this list cannot cover unknown external files. Use the approved interpreter for your installation if it differs from `python`.

```powershell
$backup = Join-Path $env:USERPROFILE ('Documents\NajdiLab-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $backup) { throw 'Choose a new backup folder.' }
New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null
$before | Set-Content -LiteralPath (Join-Path $backup 'before-commit.txt')
git bundle create (Join-Path $backup 'source.bundle') --all
if ($LASTEXITCODE -ne 0) { throw 'Git bundle backup failed.' }
foreach ($name in @('data','datasets','exports','training','config','reports','.env')) {
    $source = Join-Path $repo $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $backup -Recurse -ErrorAction Stop
    }
}
$db = Join-Path $repo 'data\najdilab.db'
if (Test-Path -LiteralPath $db) {
    @'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("Backup integrity check failed")
finally:
    target.close()
    source.close()
'@ | python - $db (Join-Path $backup 'najdilab-consistent.db')
    if ($LASTEXITCODE -ne 0) { throw 'Consistent database backup failed; do not update.' }
}
```

Verify the backup is readable and complete. SQLite backup includes committed WAL state; copying only the `.db` of a running database is insufficient. Avoid concurrent writers during the filesystem snapshot. Nothing is deleted.

## 3. Fetch, inspect migrations, then fast-forward

```powershell
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
git log --oneline HEAD..origin/main
git diff --stat HEAD..origin/main
git diff --name-status HEAD..origin/main -- migrations plans
git diff HEAD..origin/main -- migrations
```

Verify fetched `origin/main` contains exactly the reviewed merge and any separately approved changes. **This Integrations PR adds no migration and changes no applied SQL.** If migrations appear, stop and review their backup/compatibility/rollback separately. Existing startup automatically applies pending `migrations/*.sql`; do not launch before this review. Never move proposed SQL from `plans/` into startup as part of updating. Do not run migration/training/deployment scripts to refresh integrations.

```powershell
if ((git branch --show-current).Trim() -ne 'main') { throw 'Review the branch first.' }
git merge --ff-only origin/main
if ($LASTEXITCODE -ne 0) { throw 'Diverged history; stop and review, do not reset.' }
python scripts/install.py --check
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed; keep the backup.' }
python scripts/check_docs.py
if ($LASTEXITCODE -ne 0) { throw 'Documentation/source check failed.' }
git status --short --branch
```

Run tests on a **disposable copy/checkout**, using the pinned development runner and fixture-only tests, before starting the updated installation. Do not install test dependencies into the application environment without deciding to do so. Review the PR's exact test/skip evidence; private artifacts require their own authorized checks. Resume NajdiLab only with its existing reviewed launcher/environment, without printing secrets. Open Settings and verify initial disconnected/BLOCKED states before granting actions. Real generation requires the visible synthetic-test consent; it is not an automatic update check.

## 4. Rollback without deleting data

Keep the backup and `$before` until acceptance. If only this PR changed, no database downgrade is needed: it adds no schema/persistent state. Disconnect integrations locally, finish active work, stop only the intended NajdiLab process and recheck Git status. With a clean tree, `git switch --detach $before` restores reviewed old tracked source while retaining ignored data; do not use `git reset --hard`, `git clean` or delete folders. Detached checkout is temporary recovery, not a branch to push.

**Security warning:** old code may reopen the unsafe Hermes receiver. Before running it, arrange separately approved sender-side removal/verification; otherwise keep the receiver stopped. Restoring old code does not repair Hermes sender privacy. If other merged changes introduced schema changes, follow their reviewed rollback instead. Never overwrite newer data from backup casually: restore into a separate private recovery folder and validate first. This PR does not automatically authorize restoration or external service changes.
