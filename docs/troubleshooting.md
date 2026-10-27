# Troubleshooting

## Python or launcher fails

Check `python --version` (Python 3.11+). Set `NAJDILAB_PYTHON` to an existing executable when using a launcher. If PowerShell blocks script execution, use your approved shell policy or invoke the intended Python executable with `-m app.server`; changing machine-wide policy is not required. Run from the repository root when invoking Python directly.

## Port already in use

Check whether the intended instance is already running. Stop only the instance you own, or choose another `NAJDILAB_PORT`. Do not terminate unrelated Python, Hermes, model-serving or WSL processes. Open the same configured port in the browser and collector.

## Empty pages or UNKNOWN / BLOCKED state

A fresh checkout has no private operational datasets, reports or model registry. Missing evidence must stay visible. Do not copy arbitrary artifacts into a frozen version or weaken gates. Use the normal collection/review/build flow or an authorized verified restore. Refresh stale cached pages after an interface change.

## Export refused

Read the structured export-readiness findings. Resolve pending/stale/conflicting reviews and privacy/evaluation flags through supported review actions. HTTP 409 is an intentional integrity gate. Correcting a record creates a separate overlay; do not edit source text or a historical export to remove a blocker.

## Migration or database failure

Stop additional writes, preserve the database and diagnostic evidence, and use [backup/restore](backup-and-restore.md). Check `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on an isolated restored copy. Do not run proposed migrations or delete WAL/SHM files to clear an error. Startup automatically applies files already in `migrations/`; this remains a known upgrade limitation.

## Browser writes rejected

Check the current [security contract](../SECURITY.md), local origin and selected port. A cross-origin or malformed request should fail. Do not disable protections or add a wildcard CORS rule. External collectors must follow their supported integration contract.

## Training not READY

Registration is not model validation. Confirm the exact model/revision, available weights/tokenizer, frozen dataset fingerprint, masks, live runtime/CUDA evidence, staging hash, worker freshness and VRAM. Estimates are not fit guarantees. Historic runtime checks/authorization expire and cannot be reused after restore. Read [model selection](model-selection-guide.md) and [preflight](training-preflight-runbook.md).

## Tests need local artifacts

The full suite includes historical integration checks requiring private Gold/holdout/report/model fixtures. Record missing-fixture failures with test names and sanitized diagnostics, and run relevant self-contained fixtures separately. Historical passing counts cannot prove a code-only checkout passes today. Never publish private fixture contents in an issue.
