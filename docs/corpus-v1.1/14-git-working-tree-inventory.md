# 14 — Inventory of Pre-existing Uncommitted Changes (K12) and Reconciliation Plan

Status: **INVENTORY; reconciliation plan APPROVED AS DESIGN (P1-07, 2026-10-23); execution needs OA-01. Nothing was reset, discarded, overwritten, staged or committed.**
Observed read-only with `GIT_OPTIONAL_LOCKS=0` on 2026-10-23. HEAD = `bcdf4a7` ("Document training readiness and model selection"). The Phase 1 documentation files under `docs/` are excluded from this inventory.

## 1. Inventory (16 items: 11 modified, 5 untracked)

| # | Path | State | ± lines | mtime (+03) | Group | Purpose (from the diff) |
|---|---|---|---|---|---|---|
| 1 | `app/server.py` | M | +7 −1 | 10-09 13:57 | G-A | Routes for model acquisition: `GET /api/v1/training/model-acquisition/catalog`, `POST …/prepare`, `POST …/acquire` |
| 2 | `app/training_control.py` | M | +154 −5 | 10-09 14:05 | G-A, G-E | `OFFICIAL_MODEL_CATALOG` (Gemma 4 E2B IT, `google/gemma-4-E2B-it`, pinned revision `3e22461f…`), `model_acquisition_catalog`, `prepare_model_acquisition`, `acquire_model` with an exact-approval step and WSL probe; QLoRA VRAM estimate change |
| 3 | `static/app.js` | M | +7 −1 | 10-09 13:57 | G-A | UI: acquisition card, prepare and acquire buttons, approval state |
| 4 | `static/index.html` | M | +2 −1 | 10-09 13:57 | G-A | Panel "Model acquisition — Official trainable Gemma 4" (historically Arabic) |
| 5 | `tests/test_arabic_training_ui.py` | M | +17 | 10-09 13:58 | G-A | `test_official_model_acquisition_is_reviewable_and_never_implicit` |
| 6 | `tests/test_training_control.py` | M | +31 | 10-09 14:05 | G-A, G-E | `test_qlora_vram_uses_quantized_parameter_footprint_not_disk_size`, `test_acquisition_requires_exact_approval_and_registers_verified_local_model` |
| 7 | `app/runtime_control.py` | M | +113 −12 | 10-10 13:57 | G-B | Hardened `deploy_adapter`: injectable runner, `ADAPTER_DEPLOY_MODE=0o444`, in-WSL deploy script with lock, live-training-process detection, timestamped backup, atomic replace and rollback, hash evidence |
| 8 | `tests/test_safe_adapter_deployment.py` | ?? | 9,342 B | 10-10 13:57 | G-B | Production-path deploy tests (single-file verified, idempotent, pre/post-replace failure rollback, concurrent lock, active-training rejection, invalid target) |
| 9 | `tests/test_safe_adapter_deployment_simple.py` | ?? | 5,947 B | 10-10 01:54 | G-B | Simplified deploy tests (atomic replace, rollback, SHA-256, companions, permissions, active training) |
| 10 | `scripts/najdilab_training_adapter.py` | M | +39 −7 | 10-10 01:10 | G-C | Training-plan fix: Smoke validates the **full** plan against `expected_steps` but executes 2 steps; Full validates plan and `max_steps`. Repo hash `b14c7c…` (see `06-adapter-drift-k2.md`) |
| 11 | `tests/test_training_plan_mismatch_regression.py` | ?? | 5,551 B | 10-10 01:11 | G-C | Mocked-stack regression: Smoke validates 27-step plan and runs 2; Full runs 27; genuine mismatch rejected before `trainer.train` |
| 12 | `tests/test_training_plan_mismatch_unit.py` | ?? | 5,577 B | 10-09 19:51 | G-C | Unit test of the same logic. **References a WSL model path** (`<runtime-root>/models/gemma-4-E2B-it-official`) |
| 13 | `scripts/najdilab_training_adapter.py.tmp` | ?? | 3,681 B / 32 lines | 10-09 19:34 | G-G | Scratch fragment of `validate()` (not a runnable file) |
| 14 | `scripts/train_najdi_sft.py` | M | +12 −4 | 10-09 14:11 | G-D | Gemma-native tool-call serialization and masking (`<|tool_call>…<tool_call|>`), branching on the tokenizer's chat template; Ministral path unchanged. **Identical to the deployed WSL copy** (`71d546e0…`) |
| 15 | `tests/test_phase37_tool_hardening.py` | M | +22 | 10-09 14:11 | G-D | `test_gemma_native_template_uses_object_arguments_and_masks_results` |
| 16 | `scripts/NajdiLab_Autostart.ps1` | M | +1 −1 | 10-07 20:08 | G-F | **Line ending only** (LF → CRLF on the final line). No functional change |

## 2. Groups and relevance

| Group | Theme | Live relevance | Relevance to Corpus v1.1 |
|---|---|---|---|
| G-A | Official Gemma 4 E2B IT acquisition with explicit approval | **In use**: `training/models.json` lists Gemma 4 E2B IT as VALID/AVAILABLE; WSL has `models/gemma-4-E2B-it-3e22461f`; `training/acquisitions/gemma4-e2b-it-official.json` exists. HEAD doesn't contain the code that produced this state | High: the initial eligible model (BR-02) |
| G-B | Hash-verified, backup-preserving adapter deployment | Code path for K2 reconciliation step R6 | High: a prerequisite for safe reconciliation |
| G-C | Training-plan mismatch fix (Smoke vs Full) | Relates to the K2 drift. The WSL copy `c35e88…` contains a **different** variant of this fix | High: decision OA-02 |
| G-D | Gemma-native tool-call masking | Already deployed to WSL (identical hash) | High: model independence (template-specific logic isolated in the runtime layer) |
| G-E | QLoRA VRAM estimate | Training preflight accuracy | Medium |
| G-F | CRLF-only change | None | None |
| G-G | Scratch fragment | None | None |

## 3. Observations for review (not fixes)

- **O-1:** in the repo adapter's `resolve_plan`, full training computes `total = steps_epoch * epochs` without rounding up, while HEAD used `math.ceil(steps_epoch*epochs)`. With fractional `epochs` this yields a non-integer step count, and the plan check could reject valid jobs. Verify in R2/R3 (`06-adapter-drift-k2.md`).
- **O-2:** HEAD doesn't represent the running system. If NajdiLab was restarted after 2026-10-09 it runs the working-tree code (G-A, G-B). Any `git reset`/`checkout` would remove live capabilities and the deploy safety logic.
- **O-3:** a private intermediate-snapshot directory holds copies of `server.py`, `training_control.py`, `app.js` and `index.html` whose hashes match **neither** HEAD nor the working tree (intermediate snapshots). Keep them as evidence.
- **O-4:** test #12 depends on a machine-specific WSL path, so it isn't portable.

## 4. Safe reconciliation plan (proposal; every write step needs separate owner approval, OA-01)

| Step | Action | Writes? |
|---|---|---|
| W1 | Preserve the evidence: export `git diff` per group and copies of the 5 untracked files into a new timestamped folder under `backups/` (git-ignored), with a SHA-256 manifest | Yes (approval) |
| W2 | Review each group's diff with the owner. Classify keep / revise / park | No |
| W3 | Run the affected tests **in an isolated copy** of the repo (`10-test-plan.md` §0): G-A (#5, #6), G-B (#8, #9), G-C (#11, #12), G-D (#15), plus the full suite | Isolated copy only |
| W4 | Resolve the adapter (G-C) together with K2 (decision OA-02). Fix O-1 only in a separately approved code change | — |
| W5 | Commit per group, in this order: G-F (or drop, if the owner prefers LF), G-D, G-B, G-A+G-E, G-C. Each commit message lists file hashes | Yes (approval per commit) |
| W6 | G-G: move to the W1 archive after approval. **Not deleted** | Yes (approval) |
| W7 | Record the new HEAD and protected-hash inventory as the Phase 1A baseline | Docs |

**Explicitly not proposed:** `git reset`, `git checkout -- <file>`, `git stash`, or `git clean`. Each would destroy evidence or live capability.

## 5. Acceptance criteria (Phase 1A-0)
1. W1 archive exists, with a manifest whose hashes match the files at archive time.
2. Each group has a recorded owner decision.
3. After W5, `git status` shows only the intentionally parked items, and each commit's blob hashes equal the archived working-tree hashes.
4. The running behavior is unchanged: same routes, and the same adapter deploy behavior unless OA-02 decides otherwise.
