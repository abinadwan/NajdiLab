# 07 — Review of Prepared Migrations 005–007 and Proposal for 008

Status: **REVIEW APPROVED (2026-10-23); 008 REMAINS A DRAFT PROPOSAL. No migration was applied, moved or created as a file. All of 005/006/007/008 are BLOCKED until the loader guard (PRQ-MIG-01, `15-migration-loader-guard.md`) exists and each migration gets its own approval.** Production DB state (read-only, `immutable=1`, 2026-10-23): migrations `001`–`004` applied; tables `dataset_registry_*`, `review_events`, `model_registry`, `training_jobs`, `training_attempts` absent; no triggers.

## 1. How migrations run today (critical context)

- `apply_migrations` (`app/db.py:75-90`) runs **every** `migrations/*.sql` not yet recorded, in `sorted()` filename order, via `executescript`, and is called on **every server start** (`app/server.py:509`).
- `executescript` isn't transactional unless the file contains its own `BEGIN … COMMIT`. Of the existing files, only 004 does.
- So **placing any file in `migrations/` is equivalent to applying it on the next restart.** The Phase 1.3 runbook already keeps 005 outside for this reason.

## 2. Per-migration review

### 005: `plans/phase13/005_dataset_registry.sql` (REG-09)

| Aspect | Finding |
|---|---|
| Content | Additive: `dataset_registry_versions`, `dataset_registry_locations` + index; JSON and hash-length CHECKs |
| Runner | `scripts/phase13_registry.py` (preflight / prepare / rehearse / execute with `REG-09-APPROVED` token and verified backup), wraps DDL + backfill in `BEGIN IMMEDIATE` |
| Consumers | `app/dataset_registry.py` writes it. Canonical reads (REG-10) are not yet wired |
| Issues | (a) Coexists with the legacy `dataset_versions` table (4 rows) and the filesystem catalog. Until REG-10 cutover there are **three** catalog views; the state semantics differ (`dataset_platform._state` collapses legacy → Frozen, the registry uses `Unknown`, per `docs/phase-2-4-current-state-audit.md`). (b) The file itself has no `BEGIN`; applying it through `apply_migrations` instead of the runner would lose atomicity with the backfill |
| Dependency for Corpus v1.1 | **Not blocking.** Helpful for G4 lineage. Recommended after 006 |
| Recommendation | Apply only through its runner after REG-08 approval; plan REG-10 cutover to make the registry canonical and the legacy table read-only |

### 006: `plans/phase2/006_review_events.sql` (DATA-05)

| Aspect | Finding |
|---|---|
| Content | Additive `review_events` (FK `reviews(id) ON DELETE RESTRICT`, `UNIQUE(review_id, sequence)`, hash CHECKs) + immutability triggers on UPDATE/DELETE |
| Consumers | Ready: `review_lifecycle.append_event`, `service._record_review_event` (`service.py:457-488`, active only when the table exists), `review_integrity` history checks (`review_integrity.py:100-152`) |
| Runner | **None.** No guarded runner equivalent to `phase13_registry.py` exists |
| Issues | (a) Covers conversation reviews only. Manual items are excluded (gap closed by 008). (b) `actor` is free text with no profile reference (gap closed by 008 + S6). (c) `ON DELETE RESTRICT` on `reviews` interacts with `messages → reviews ON DELETE CASCADE`: after 006, hard-deleting a conversation that has review events will fail. That's acceptable, and arguably desired, since the app uses soft delete, but it must be documented. (d) No backfill: existing 567 reviews have no history; `review_integrity` already treats missing history as an ambiguous warning (`REVIEW_HISTORY_UNAVAILABLE`) |
| Dependency for Corpus v1.1 | **Blocking for authoritative G3 audit.** Prerequisite for 008 |
| Recommendation | Build a guarded runner (preflight, backup via SQLite backup API, restore proof, `BEGIN IMMEDIATE`, integrity and FK checks, approval token) mirroring Phase 1.3, then apply with separate approval (Phase 1A) |

### 007: `plans/training-readiness/007_model_training_registry.sql` (+ `.rollback.sql`)

| Aspect | Finding |
|---|---|
| Content | Additive `model_registry`, `training_jobs`, `training_attempts` with CHECKs and indexes |
| Consumers | **None.** No code under `app/` or `scripts/` reads or writes these tables. Live sources of truth are `training/models.json`, `training/jobs/<id>/job.json` and attempt folders (`app/training_control.py`, `app/runtime_control.py`) |
| Issues | (a) **Applying it would create a competing, empty source of truth** for models and jobs. (b) **Filename hazard:** if both files were copied into `migrations/`, `sorted()` would place `007_model_training_registry.rollback.sql` **before** `007_model_training_registry.sql` (`.r` < `.s`). Both would run and be recorded, which corrupts migration bookkeeping. Rollback scripts must never live under `migrations/`. (c) `training_jobs.status` vocabulary differs from the JSON job states in use |
| Dependency for Corpus v1.1 | **Not needed.** Training continues on the existing JSON control plane |
| Recommendation | **Do not apply** until a cutover design exists (dual-write or one-time import with JSON as the archive, plus a read-path switch). Rename the rollback file pattern to a non-`.sql` suffix or keep it in `plans/` permanently |

## 3. Dependency order (proposed)

```
006 (review_events, guarded runner) ──► 008 (manual-item lifecycle, reviewer profiles, generation batches)
005 (dataset registry, existing runner) ──► REG-10 canonical reads   [independent of 008; recommended before G4 lineage work]
007 ── on hold (no consumers; competing source of truth)
```

## 4. Proposal: migration 008 (DRAFT, not a file, not for execution)

Purpose: implement `03-review-lifecycle.md` and `05-security-prerequisites.md` S6, additively.

```sql
-- DRAFT 008_corpus_v11_review_lifecycle — documentation only; not for execution.
-- Preconditions: 006 applied; verified backup + restore proof; approval token.
BEGIN IMMEDIATE;

CREATE TABLE reviewer_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL UNIQUE,
  roles_json TEXT NOT NULL CHECK (json_valid(roles_json)),      -- ["author","reviewer","linguistic_lead","data_owner"]
  native_najdi INTEGER NOT NULL DEFAULT 0 CHECK (native_najdi IN (0,1)),
  pin_hash TEXT,                                                -- PBKDF2; DF-03
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL
);

CREATE TABLE generation_batches (
  batch_id TEXT PRIMARY KEY,
  tier TEXT NOT NULL CHECK (tier IN ('silver','bronze')),
  generator_version TEXT NOT NULL,
  generator_sha256 TEXT NOT NULL CHECK (length(generator_sha256)=64),
  g1_report_sha256 TEXT NOT NULL CHECK (length(g1_report_sha256)=64),
  config_json TEXT NOT NULL CHECK (json_valid(config_json)),
  seed INTEGER,
  started_by_profile_id INTEGER NOT NULL REFERENCES reviewer_profiles(id),
  status TEXT NOT NULL CHECK (status IN ('PREVIEW','RUNNING','COMPLETED','FAILED','CANCELLED')),
  counts_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(counts_json)),
  created_at TEXT NOT NULL
);

-- Additive lifecycle columns (one ALTER per table; repeated for direct_language_texts and preference_pairs)
ALTER TABLE manual_sft_items ADD COLUMN review_state TEXT NOT NULL DEFAULT 'LEGACY'
  CHECK (review_state IN ('LEGACY','DRAFT','PENDING_REVIEW','CHANGES_REQUESTED','APPROVED','REJECTED'));
ALTER TABLE manual_sft_items ADD COLUMN generation_batch_id TEXT REFERENCES generation_batches(batch_id);
ALTER TABLE manual_sft_items ADD COLUMN author_profile_id INTEGER REFERENCES reviewer_profiles(id);
-- New rows created by the service set review_state explicitly ('DRAFT' or 'PENDING_REVIEW').
-- The DEFAULT 'LEGACY' applies only to pre-existing rows at ALTER time. To stop any code path
-- (old or new) from creating a row that silently defaults to LEGACY and escapes the guard:
CREATE TRIGGER manual_sft_no_new_legacy BEFORE INSERT ON manual_sft_items
WHEN NEW.review_state = 'LEGACY'
BEGIN SELECT RAISE(ABORT,'new manual items must enter the review lifecycle'); END;
-- and a guard against converting an existing non-legacy row back to LEGACY:
CREATE TRIGGER manual_sft_no_relegacy BEFORE UPDATE OF review_state ON manual_sft_items
WHEN NEW.review_state = 'LEGACY' AND OLD.review_state != 'LEGACY'
BEGIN SELECT RAISE(ABORT,'review_state cannot return to LEGACY'); END;

CREATE TABLE manual_item_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_type TEXT NOT NULL CHECK (item_type IN ('sft','direct','dpo')),
  item_id INTEGER NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  from_state TEXT, to_state TEXT NOT NULL,
  version_number INTEGER NOT NULL CHECK (version_number >= 1),
  content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
  actor_profile_id INTEGER REFERENCES reviewer_profiles(id),
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('human','system','ai_suggestion')),
  actor_role TEXT,
  reason TEXT, correction_type TEXT,
  defect_tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(defect_tags_json)),
  rubric_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(rubric_json)),
  created_at TEXT NOT NULL,
  UNIQUE (item_type, item_id, sequence),
  CHECK (to_state != 'APPROVED' OR (actor_kind = 'human' AND actor_profile_id IS NOT NULL))
);
CREATE TRIGGER manual_item_events_no_update BEFORE UPDATE ON manual_item_events
  BEGIN SELECT RAISE(ABORT,'manual_item_events are immutable'); END;
CREATE TRIGGER manual_item_events_no_delete BEFORE DELETE ON manual_item_events
  BEGIN SELECT RAISE(ABORT,'manual_item_events are immutable'); END;

-- Eligibility backstop (repeated per table). content_sha256 is verified by the service;
-- the trigger enforces state, a human approval of the current version, and non-legacy scope.
CREATE TRIGGER manual_sft_eligibility_guard
BEFORE UPDATE OF training_eligible ON manual_sft_items
WHEN NEW.training_eligible = 1 AND NEW.review_state != 'LEGACY'
 AND (NEW.review_state != 'APPROVED' OR NOT EXISTS (
      SELECT 1 FROM manual_item_events e
      WHERE e.item_type='sft' AND e.item_id=NEW.id AND e.to_state='APPROVED'
        AND e.version_number=NEW.version_number AND e.actor_kind='human'))
BEGIN SELECT RAISE(ABORT,'training eligibility requires human approval of the current version'); END;
-- plus an equivalent BEFORE INSERT trigger: NEW.training_eligible=1 AND NEW.review_state!='LEGACY' → ABORT

-- review_tags vocabulary extension requires a table rebuild (CHECK constraint), following the
-- lossless-copy-with-assertion pattern of 004. Proposed new tags:
-- agreement_error, template_repetition, scenario_mismatch, register_mismatch, caricature

-- origin/source_type: new values 'synthetic_variant', 'llm_draft' are validated in the service
-- (ORIGINS at service.py:49). direct_language_texts.source_type has a CHECK and needs a rebuild
-- if Bronze/Silver direct texts are ever allowed (proposal: not allowed in v1.1).

COMMIT;
```

### 008 design notes
- **Lossless by construction:** only `ADD COLUMN`, `CREATE TABLE` and `CREATE TRIGGER`, plus a `review_tags` rebuild using the 004 assertion pattern. Existing rows get `review_state='LEGACY'` and keep every other value.
- **Self-approval** (author ≠ approver) is enforced in the service; a trigger would need joins across batch and author and is kept out of SQL for clarity. The proposal records it as a service-level invariant with tests.
- **Runner:** a guarded runner like Phase 1.3's, applied with an approval token after a verified backup. The SQL file stays in `plans/` until the explicit execution approval.
- **Rollback (before any consumer writes):** drop triggers → drop `manual_item_events` → drop `generation_batches` / `reviewer_profiles`. Added columns can't be dropped safely in older SQLite, so rollback after consumer writes = restore the verified backup (`11-rollback-plan.md`).

## 5. Acceptance criteria for any migration in this track
1. A rehearsal on a restore-proof copy: `integrity_check=ok`, `foreign_key_check` empty, row counts and per-column checksums of pre-existing tables identical.
2. Re-application changes zero rows.
3. Protected SHA-256 inventory (frozen datasets, exports, training evidence) identical before and after.
4. Applied only through a guarded runner with a separate explicit approval. Never by placing the file in `migrations/` ahead of approval.
