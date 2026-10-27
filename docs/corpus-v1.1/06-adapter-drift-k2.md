# 06 — Training Adapter Drift (K2) and Verification-Based Reconciliation

Status: **DOCUMENTED; reconciliation plan APPROVED AS DESIGN (2026-10-23). Execution needs OA-02. No adapter copy was modified, replaced or deployed.**

## 1. Evidence (SHA-256, read-only, 2026-10-23)

| Hash (prefix) | Location / record | Timestamp | Meaning |
|---|---|---|---|
| `6885fe30…` | **Git HEAD** blob `scripts/najdilab_training_adapter.py` (commit `10e9c56`, "Initial safe import", 2026-10-09 09:28 +03) | 2026-10-09 | Committed baseline |
| `6885fe30…` | WSL `scripts/najdilab_training_adapter.py.bak` | — | Same as the baseline |
| `6885fe30…` | `training/runtime/najditrain-wsl/latest-check.json` (script hash at last runtime check) | 2026-10-09 16:16Z | What the runtime last verified |
| `6885fe30…` | `training/jobs/train-20261009-001/execution-manifest.json` and `attempt-001` | 2026-10-09 16:17Z | Bound into that job's evidence |
| `c35e8832…` | **WSL active** `<runtime-root>/scripts/najdilab_training_adapter.py` | mtime 2026-10-09 20:15 +03 | Changed after the last runtime check. **Not recorded in any manifest** |
| `b14c7c23…` | **NajdiLab working tree** `scripts/najdilab_training_adapter.py` (uncommitted) | mtime 2026-10-10 01:10 +03 | Newer repo edit. Never deployed |
| `9c3aaae1…` | NajdiLab `scripts/najdilab_training_adapter.py.tmp` (untracked) | 2026-10-09 | Scratch copy |
| `8c0de8ad…` | WSL `najdilab_training_adapter.phase310-8c0de8ad.py`; `train-20261006-001` manifests (the completed, **rejected** production run) | 2026-10-06 | Historical, preserved |
| `bb2c52cf…` | `train-20261007-001/execution-manifest.json` (Round 2 dry run); cited as "active" in `CURRENT_PROJECT_STATUS.md` | 2026-10-07 | **No copy found** in NajdiTrain (`*.py*`, venv excluded) or NajdiLab `scripts/`/`backups/` |

The only diff between `c35e88` (WSL) and `b14c7c` (repo) is in the training-plan check inside `train()` (WSL lines 183–184 vs repo lines 183–187). The repo version separates the full plan from the execution plan, so Smoke (`max_steps=2`) and Full are validated differently. Both are uncommitted edits on top of `6885fe`.

`train_najdi_sft.py` is identical in WSL and the repo (`71d546e0…`), but it's also an uncommitted edit relative to HEAD.

## 2. Assessment

- **Execution safety today:** fail-closed. Authorization re-measures the runtime script hash (`runtime_control.py:775`) and compares it with the execution manifest. A fresh runtime check would report `c35e88`, which mismatches the manifests (`6885fe`, `bb2c52`), so existing READY jobs can't be authorized without a new dry run. **No change is needed for safety.**
- **Traceability gap:** the code that produced the `train-20261007-001` dry-run evidence (`bb2c52`) can't be reproduced. `CURRENT_PROJECT_STATUS.md` is out of date.
- **Process gap:** the WSL adapter was edited outside the hash-verified `deploy_adapter` path (`runtime_control.py:430`), which creates a timestamped backup and verifies hashes (deploy script at `:351`).

## 3. Reconciliation plan (Phase 1A, each step needs approval; nothing here has been done)

| Step | Action | Writes? | Acceptance |
|---|---|---|---|
| R1 | Record this evidence table as an immutable report (this document) | Docs only | Done in Phase 1 |
| R2 | Three-way diff: HEAD `6885fe` ↔ repo `b14c7c` ↔ WSL `c35e88`, reading all three as files without modifying them. Classify each hunk (bug fix / feature / unknown) | No | Signed-off hunk table |
| R3 | Run the adapter-related tests (`tests/test_training_plan_mismatch_unit.py`, `_regression.py`, `test_safe_adapter_deployment*.py`, `test_phase311_training_adapter.py`) **in an isolated copy** of the repo, because tests create `.test-temp*` folders | Isolated copy only | Results recorded per candidate version (`b14c7c` and `c35e88`) |
| R4 | Owner chooses the authoritative version (expected: `b14c7c` if R3 shows it's a superset fix) | Decision | Written decision referencing hashes |
| R5 | Commit the chosen version to git in NajdiLab with the hash in the message (with the other uncommitted work reviewed separately: K12) | Git (approval) | HEAD blob hash = chosen hash |
| R6 | Deploy **only** through the existing UI/API `deploy-adapter` path (backs up `c35e88` automatically as `.backup-<stamp>-<token>`) | WSL (approval) | API returns PASS; destination hash = chosen hash; backup file hash = `c35e88` |
| R7 | Fresh runtime check | Runtime check | `latest-check.json` script hash = chosen hash |
| R8 | Mark existing READY jobs' dry-run evidence stale (existing invalidation behavior); new dry runs only on request | Job metadata via existing UI | No READY job carries a manifest hash ≠ the deployed hash |
| R9 | Correct `CURRENT_PROJECT_STATUS.md`; record `bb2c52` as an unrecoverable artifact | Docs | Status doc matches measured hashes |

Rollback for R6: redeploy the backup copy through the same verified path. `8c0de8ad` and the `6885fe` `.bak` stay untouched throughout.

## 4. Preventive controls (proposed for Phase 1A/2)
- The runtime check warns when the deployed script hash ≠ the git HEAD blob hash.
- A status report generator writes adapter hashes from measurement, never by hand.
- Direct edits to the WSL adapter are prohibited by runbook. Deployment goes only through `deploy-adapter`.
