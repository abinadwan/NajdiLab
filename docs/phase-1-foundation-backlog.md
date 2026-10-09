# Phase 1 — Platform Foundation Remediation backlog

Status: active, low-risk foundation slice. Phase 4 remains **BLOCKED** and Phase 3 remains **REJECT**.

| Priority | Workstream | Phase 0 evidence | Dependency | Acceptance criteria |
|---|---|---|---|---|
| P0 | Platform phase audit | Status was repeated in prose/UI; operational truth exists in manifests, jobs and reviews | None | Read-only derived status; missing evidence is `UNKNOWN`; no implied success |
| P0 | Sample decisions | Review overlays and immutable sources already exist | Status source | 24 Phase 3 decisions and final REJECT remain byte-identical; lifecycle is explicit |
| P1 | Duplicate/similarity detection | Exact dedup and near-duplicate reporting exist | Dataset catalog | Cross-root IDs conflict visibly; no silent merge; similarity report remains read-only |
| P0 | Dataset version unification | SQLite registry and filesystem roots can diverge | None | One catalog joins both sources, emits each ID once, and reports path/ID conflicts |
| P1 | Python/VRAM/WSL training environment | Training scripts have optional ML dependencies and local model paths | Catalog + gates | Preflight reports Python, runtime and VRAM evidence; no training starts implicitly |
| P1 | Human evaluation, Najdi stability and capabilities | 24/24 Phase 3 review ended REJECT; later remediation artifacts are gated | Status + catalog | Frozen review decisions preserved; explicit dialect/capability measures; Phase 4 stays blocked |

No SQLite migration or backfill is included. Any future production migration requires a verified database snapshot, a fixture rehearsal, rollback SQL, and explicit user approval.
