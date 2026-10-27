# 08 — Risk Register (Corpus v1.1 track)

Status: **Living document. Phase 1 baseline 2026-10-23.** Likelihood/Impact: H/M/L.

| ID | Risk | L | I | Evidence | Mitigation | Owner | Phase |
|---|---|---|---|---|---|---|---|
| K1 | Authoritative review audit not live (`review_events` absent) | H | H | DB: migrations 001–004 only | Guarded runner + apply 006 (`07-…`) | Eng + owner approval | 1A |
| K2 | Training adapter drift: WSL `c35e88…` ≠ repo `b14c7c…` ≠ HEAD `6885fe…`; `bb2c52…` unrecoverable | H | M | `06-adapter-drift-k2.md` | Verification-based reconciliation R1–R9 | Eng + owner | 1A |
| K3 | Modules duplicated by copy across repos (`tool_runtime.py`, `native_tool_data.py`, `train_najdi_sft.py`) | M | M | Identical hashes; deploy only covers the adapter | Extend deploy verification to all runtime modules; hash report in runtime check | Eng | 1A/2 |
| K4 | Manual items can be inserted trainable without review | H | H | `service.py:1449` | Lifecycle + four enforcement layers (`03-…`) | Eng | 2 |
| K5 | CSRF / DNS rebinding against the local API | M | H | `server.py:306/471/489`, no Origin/Host/Content-Type checks | S1–S4 | Eng | 1A |
| K5b | A local process can read the DB directly | L | M | DB file on disk | OS-level controls; out of scope | Owner | — |
| K6 | No reviewer identity or roles | H | H | `_reviewer` categories only | S6–S8 + 008 | Eng | 2 |
| K7 | DB on the Windows FS, runtime in WSL; concurrent writes forbidden | M | H | README | Generators write via the service layer only, on the Windows side | Eng | 2 |
| K8 | Running tests creates folders in the repo | H | L | `.test-temp*`, `.pytest_*` in root | Run tests in an isolated copy or with a temp-dir override | Eng | 1A |
| K9 | Small data and a small eligible base model (Gemma 4 E2B IT); v009 has 66 gradient records | H | M | `training/models.json`, README | Pilot sized to measure; thresholds recalibrated after the pilot | Owner | 1/7 |
| K10 | NajdiTrain hygiene: root-owned files, `.tmp`/`.candidate`/`.bak` scripts, legacy pipelines | M | M | Listing of `<runtime-root>` | Inventory + archive plan (read-only first); no deletion without approval | Owner | 1A |
| K11 | Docs refer to `/path/to/najdilab`, but the platform lives on Windows | M | L | README Linux section | Correct the docs in Phase 1A | Eng | 1A |
| K12 | **Uncommitted code in the NajdiLab working tree** (11 modified, 5 untracked). Some of it is live (model acquisition, safe adapter deploy); HEAD doesn't represent the running system | H | H | `14-git-working-tree-inventory.md` | Plan W1–W7: archive, review, isolated tests, per-group commits (OA-01). **No reset, checkout, stash or clean** | Owner + Eng | 1A-0 (first) |
| K13 | `datasets/`, `exports/`, `reports/`, `training/`, `data/` are git-ignored: immutability relies on app logic and hashes only | M | H | `.gitignore` | Protected-hash inventory before and after each phase; backups via SQLite backup API | Eng | all |
| K14 | Migrations auto-apply on server start | M | H | `db.py:75-90`, `server.py:509` | All migrations blocked; loader guard L1–L7 (PRQ-MIG-01, `15-…`) before any SQL enters `migrations/` | Eng | 1A-00 |
| K15 | Rollback-file sort hazard (`007_….rollback.sql` sorts before forward) | L | H | `07-…` §2 | Never place rollback files in `migrations/`; non-`.sql` suffix | Eng | 1A |
| K16 | Migration 007 would create a competing training registry | M | H | No consumers in `app/` | Hold 007; cutover design first | Owner | — |
| K17 | Dialect authority bias (a single reviewer's idiolect) | M | M | — | ≥ 2 native reviewers, κ, linguistic lead adjudication | Owner | 2/7 |
| K18 | Silver variation slides back into templating (v1.0 failure mode) | M | H | Corpus v1.0 analysis F01–F05 | Typed lexicon, G1 property tests, `SIG_TEMPLATE_CONCENTRATION`, `LING_SLOT_VALUE_REPEAT` | Eng | 6 |
| K19 | Bronze provider governance (terms of service, privacy, dialect bleed) | M | H | — | ADR-007; deferred | Owner | — |
| K20 | Live data keeps changing (80 PENDING reviews; DB modified 2026-10-20) | H | L | DB counts | Design never assumes static counts; migrations re-preflight at run time | Eng | all |
| K21 | Eval contamination by Silver variants of eval-adjacent Gold | M | H | — | Split by `parent_item_id` group; template-level leakage check in G4 | Eng | 2/8 |
| K22 | Unvalidated Arabic word lists or examples treated as ground truth | M | H | `01` provisional banner | PRQ-LANG-01; dialect-list detectors advisory-only until native sign-off | Owner | 7 |
| K23 | Repo adapter rounding change (O-1) may reject valid fractional-epoch plans | M | M | `14-…` §3 | Verify in K2 R2/R3; DF-10 | Eng | 1A-2 |
| K24 | Dialect quotas creeping back through generator or detector design | L | H | v1.0 F01–F05 | BR-10: no minimum checks; `SIG_DIALECT_MARKER_EXCESS` upper-side only; G1 property test that the generator inserts no marker to reach a density | Eng | 3/6 |
