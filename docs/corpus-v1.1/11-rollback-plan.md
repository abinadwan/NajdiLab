# 11 — Rollback Plan

Status: **APPROVED DESIGN (Phase 1, owner approval 2026-10-23).** Principles: nothing is deleted to roll back data; quarantine instead. Every schema change has a verified pre-change backup and restore proof. Rollback paths are rehearsed before forward execution.

| Change | Pre-conditions | Rollback (before consumers write) | Rollback (after consumers write) | Verification |
|---|---|---|---|---|
| **Phase 1 docs** (this folder + two additive sections) | — | Remove `docs/corpus-v1.1/`; restore the two edited docs from git (`git checkout -- docs/architecture.md docs/master-execution-board.md`; both were clean at HEAD `bcdf4a7` before Phase 1) or delete the appended sections | Same | Docs inventory equals the pre-Phase-1 inventory |
| **1A-1 security code** | Committed baseline (1A-0) | `git revert` of the security commit | Same; no data impact | Full suite + security tests |
| **1A-2 adapter deploy** | R2–R5 complete; deploy creates `.backup-<stamp>-<token>` | Redeploy the backup through the same hash-verified path | Same | `latest-check.json` script hash = restored hash |
| **1A-3 migration 006** | SQLite backup API snapshot + restore proof + hash recorded | One transaction: drop triggers, then `review_events` (only if no rows were written) | Stop only the NajdiLab process (explicit approval), restore the verified snapshot, integrity and FK check, restart NajdiLab only. **Hermes, Ollama and OpenClaw are never stopped** (Phase 1.3 runbook pattern) | integrity ok; FK empty; row counts and checksums equal the snapshot |
| **Phase 2 migration 008** | As for 006 | Drop triggers → `manual_item_events` → `generation_batches` → `reviewer_profiles` (added columns stay, inert) | Restore the verified snapshot (as above). Decisions made after the snapshot are exported first as a JSONL report so they can be re-entered by humans | Same |
| **Lifecycle / identity code** | — | `git revert`; the DB triggers keep blocking eligibility (fail-closed) | Same | Export gate still blocks unapproved generated items |
| **G2 detector rule set** | Rule sets versioned | Pin the previous rule-set version; mark G3 samples drawn under the bad version as invalidated | Same | Report shows the active rule-set version |
| **Generation batch** | Batch recorded in `generation_batches` | Cancel the batch; items stay `PENDING_REVIEW` / `REJECTED` (never deleted) | Ignore or exclude the batch's items through existing soft states with a reason | No item from the batch is `training_eligible=1` |
| **Dataset version** | Frozen versions immutable | Don't use the version; derive a new Draft from the previous Frozen version | Same | Training jobs reference the intended dataset fingerprint |
| **Training** | Existing single-use authorization | Cancel the job or attempt (existing); adapters stay as evidence | Same | Evaluation gate never promotes without an explicit human decision |

Protected throughout (never modified by any rollback): Corpus v1.0 evidence, frozen datasets and exports, raw `messages`, historical review decisions, rejected adapters and training evidence, Phase 3 artifacts.
