# 16 — UI-First Confirmation

Status: **CONFIRMED BY OWNER AS A DESIGN REQUIREMENT (P1-08, 2026-10-23).** Every routine workflow in the Corpus v1.1 track is operated through NajdiLab with explicit human oversight. CLIs and scripts may exist for tests, rehearsal and recovery, but they're never the routine path and never bypass the server-side gates.

| Workflow | NajdiLab surface | Exists today? | Human control point | Server-side enforcement |
|---|---|---|---|---|
| Gold authoring | `/data/add`, `/data/manual` | Yes (taxonomy and author fields added in Phase 5) | Author submits explicitly | Lifecycle state `DRAFT → PENDING_REVIEW` (Phase 2) |
| Editing / correction | `/data/manual` (versions), candidate review page | Editing yes; lifecycle-aware correction in Phase 2/4 | Edit resets approval; correction recorded with type and tags | Version-bound approval; DB trigger blocks stale eligibility |
| Silver/Bronze generation | **New** `/data/generate` | No (Phase 6) | Preview → explicit **Run** by the data owner (re-auth) | Refuses without a recorded G1 pass; outputs forced to `PENDING_REVIEW`, `training_eligible=0` |
| Automated checks (G2) | `/datasets/health` + candidate view | Health yes; linguistic codes in Phase 3 | Findings route items to review | G2-D blocks approval/export; G2-H advisory |
| Review and approval (G3) | **New** `/review/candidates` (generalized from `/evaluation/remediation-review`); existing `/review` for conversations | Partly | Named reviewer decides; author ≠ approver | Role matrix (S8); human-only approval; immutable events |
| Dataset management | `/datasets/versions`, `/datasets/health`, `/datasets/balancer`, `/datasets/eval`, `/exports` | Yes | Derive, export and freeze are explicit actions; freeze needs data-owner re-auth | Export gate (HTTP 409) blocks unapproved generated items |
| Training authorization | `/training/setup`, `/training/jobs` | Yes | Dry run → single-use authorization → start, each explicit | Existing fingerprint-bound token + data-owner role |
| Evaluation and promotion | `/evaluation/human-review` | Yes | Explicit APPROVE / NEEDS_RETRAINING / REJECT | Existing gate; nothing automatic |
| Migration status | System page (read-only) | No (Phase 1A with the loader guard) | Apply is a data-owner action via the guarded runner | Loader guard L1–L7 |
| Adapter deployment | Existing `deploy-adapter` action | Yes (uncommitted G-B code) | Explicit, data-owner only | Hash-verified, backup-preserving, refuses during active training |

**Never automatic:** generation runs, approval, freezing, training, merging, GGUF/Ollama export, deployment, migration application.
