# 02 — Component Reuse Map (Gold / Silver / Bronze and G1–G4 onto NajdiLab)

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23).** All references were read on 2026-10-23 against the working tree (commit `bcdf4a7` plus uncommitted changes listed in `08-risk-register.md` K12).

## 1. Source-of-truth rules

1. **NajdiLab is authoritative** for records, reviews, versions, datasets, training jobs and evaluation decisions. NajdiTrain is the training runtime registered in `training/runtimes.json` (`najditrain-wsl`).
2. No parallel database, event store, review UI, export format or training launcher may be created.
3. Generated content enters NajdiLab **only through the service layer** (`app/service.py`), never by writing SQLite or dataset folders directly. This matters because the DB lives on the Windows filesystem and the README forbids concurrent Windows/WSL writes.
4. Frozen datasets (`exports/`, `datasets/` with `state=Frozen`), raw messages, review history, training artifacts and Corpus v1.0 evidence are read-only to this track.

## 2. Tier mapping

| Tier | Storage (existing) | Provenance (existing → proposed extension) | Entry path | UI | Verdict |
|---|---|---|---|---|---|
| **Gold**: native-authored | `manual_sft_items` (`003_manual_data_manager.sql`); versions in `manual_data_versions` | `origin='manual'`, `source_type='human_written'` (existing values, `service.py:49`, `:1234`) + `metadata_json.corpus_v11.author_profile_id` | `POST /api/v1/training-data/sft` → `add_manual_sft` (`service.py:1406`) | `/data/add`, `/data/manual` | **REUSE + EXTEND** (taxonomy fields, author identity, review lifecycle) |
| **Silver**: controlled variation of Gold | `manual_sft_items` with `parent_item_id` → Gold item (column exists) | **New** `origin='synthetic_variant'` + `source_type='synthetic_variant'` (migration 008); `metadata_json.corpus_v11.{variation_ops, generation_batch_id, generator_version, generator_sha256}` | New service function `create_generated_items(batch)` calling the same insert path as `_insert_training_item` (`service.py:1443`) with eligibility forced to 0 | New **Generation** page (batch preview → explicit run) | **BUILD** generator; **EXTEND** storage |
| **Bronze**: LLM-assisted draft (optional, OA-04) | Same table | **New** `origin='llm_draft'`, `source_type='llm_draft'`; `metadata_json.corpus_v11.{model_id, prompt_template_sha256, sampling, seed}` | Same as Silver | Same Generation page | **DEFERRED** until OA-04 |

Precedent for labelling machine involvement honestly: the automated review queue records `reviewer='ai_suggestion'` and keeps rows `training_eligible=0` (`scripts/complete_review_queue.py:20`, `:281`). The current DB holds 205 such rows.

## 3. Gate mapping

| Gate | Purpose | Existing component | Change | Verdict |
|---|---|---|---|---|
| **G1** Generator validation | Proves the *tool* is correct before it can produce candidates | NajdiLab `tests/` (unittest, 230 tests per board), deterministic fixture patterns | New test module for the generator + regression fixtures from read-only copies of Corpus v1.0 evidence | **BUILD** (tests) |
| **G2** Automated linguistic validation | Deterministic defects (blocking) + heuristic signals (advisory) | `app/dataset_quality.py:43-160`: finding registry with stable IDs, severities, Arabic explanations; served by `GET /api/v1/dataset-versions/{v}/quality-findings` | Add G2-D and G2-H finding codes; add a candidate-scope entry point that runs before review (not only on dataset directories) | **EXTEND** |
| **G3** Human review | Explicit human approval per item version | Conversation reviews: `reviews`, `review_tags`, `review_lifecycle.py:15-73`, `service.py:547-684`. Candidate-batch review precedent: `phase38_dataset.py:153-195` (v009-specific), `phase39_edits.py` (audited edits) | New manual-item review lifecycle (`03-review-lifecycle.md`); generalize the Phase 3.8 queue into a generic candidate queue; reviewer identity (`05-security-prerequisites.md`) | **EXTEND** + **BUILD** (identity, κ) |
| **G4** Training readiness | Dataset + job are fit to train | `dataset_platform.py` (derive `:294`, freeze `:448`, eval leakage `:475`, health `:518`), `dataset_quality.validate_candidate_release` (`:167`), `review_integrity.export_readiness` (`:189`), `training_control` quality gate / preflight / jobs, `runtime_control` execution gate + single-use authorization (`:761`) | Quality gate requires: zero unapproved generated items; G2-D blockers zero; G3 batch thresholds met; template-level leakage check | **REUSE + EXTEND** |

## 4. Workflow → UI mapping (UI-first)

| Routine workflow | UI route (existing / new) | API (existing / new) | Human control |
|---|---|---|---|
| Author Gold | `/data/add` (existing) | `POST /api/v1/training-data/sft` (existing) + taxonomy fields | Author submits explicitly |
| Edit / correct an item | `/data/manual` (existing) | `PATCH /api/v1/manual-data/sft/{id}` (existing); creates a new version | An edit invalidates the prior approval |
| Generate Silver/Bronze | **New** `/data/generate` | **New** `POST /api/v1/generation/batches` (preview) and `/batches/{id}/run` | Explicit run; preview first; generated items arrive as `PENDING_REVIEW` |
| Review candidates | **New** `/review/candidates` (generalized from `/evaluation/remediation-review`) | **New** `POST /api/v1/manual-data/{type}/{id}/review` | Approve / request changes / reject by a named reviewer; author ≠ approver for Silver/Bronze |
| See linguistic findings | `/datasets/health` (existing) + candidate view | `GET .../quality-findings` (existing) + candidate scope | Findings route items to review; G2-D blocks |
| Build a dataset version | `/datasets/versions` (existing) | `POST /api/v1/exports` / `.../derive` (existing) | Export gate blocks unapproved items (HTTP 409 pattern) |
| Freeze | `/datasets/versions` (existing) | `POST .../freeze` (existing) | Data-owner role (new authorization) |
| Authorize training | `/training/jobs` (existing) | Existing dry-run → authorize → start | Existing single-use token + data-owner role |
| Evaluate | `/evaluation/human-review` (existing) | Existing Phase 3 review endpoints | Existing explicit final decision |

## 5. Not to be built (duplicates removed from the earlier proposal)

| Earlier proposal item | Replaced by |
|---|---|
| Separate SQLite DB / hash-chained events table | `data/najdilab.db` + `review_events` (prepared 006) + proposed `manual_item_events` (008) |
| Content-addressed record store, manifest pointers | `manual_data_versions` snapshots + immutable `exports/` / Frozen `datasets/` with manifests and SHA-256 |
| New record schema | Existing export format (`messages`, `target_message_index`, `train_on_last_assistant_only`, `message_loss_mask`, `language_layer`, `domain`, `origin`, `source`, `source_type`) |
| Separate review service / dashboard | NajdiLab review UI and API |
| Training export to NajdiTrain | Existing staging + execution manifest + adapter CLI |
| Separate split / dedup / holdout logic | `create_export` (`service.py:2099`), `dataset_platform`, `dataset_quality` |
| Separate approval tokens | Existing single-use training authorization (`runtime_control.py:761`) |

## 6. Genuinely new components (BUILD list)

1. Generator module (Silver; Bronze connector only if OA-04 allows): a NajdiLab app module + CLI wrapper calling the service layer.
2. G2 detector set (inside `dataset_quality.py` or a sibling module it imports).
3. Manual-item review lifecycle + `manual_item_events` (migration 008).
4. Reviewer profiles, sessions, role checks, CSRF protection.
5. Generic candidate review page; double-annotation assignment; κ report.
6. Generation page.
