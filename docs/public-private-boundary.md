# Public/private candidate boundary and engineering specification

Status: implemented isolated candidate profile, not an approved publication. Stacked branch `dev/public-source-isolation` starts at PR #2 head `d5e8c2d`; PR #2 and its branch are not modified. Original source/research/documentation remain preserved. Baseline tracked-file SHA256 inventory is private outside Git.

## Components and explicit interfaces

- Reuse byte-identical core `app/db.py`, `service.py`, review integrity/lifecycle, clean export, dataset platform/quality/balancer and generic evaluation validation. The dataset platform's indirect dependency `scripts/select_v007_windows.py` is reusable selection logic, not the data-bearing correction/evaluator builders. No name-based assumption alone is a rights clearance.
- A **new** `public_source/server.py` is staged as candidate `app/server.py`; it is not a rewrite of the original server. A small new candidate UI exercises supported review/dataset APIs and does not carry historical identifiers or dataset-specific screens. Original UI, screenshots and diagrams remain unchanged in the repository.
- `Extension.handle(method, path, payload) -> (status, JSON object)` is the explicit boundary. Default `UnavailableExtension` returns 503 / `EXTENSION_UNAVAILABLE`. No environment plugin import, automatic filesystem discovery or production-path search exists. A host could inject an adapter programmatically into the new server, but no private adapter or automatic loader is shipped. Original historical implementations remain in the private repository without changes.
- Candidate `/api/v1/phase*`, `/api/v1/training/*` and `/api/v1/evaluation/*` routes are unavailable. Core `/training-dataset` is dataset eligibility output, not model training. Native Ingest, conversation/review operations, version preparation/health/quality, analytics and static UI are supported. Unimplemented routes return structured 404; this is intentionally a core profile, not full original-UI/API parity.
- Reused request boundary preserves Host/Origin/Fetch Metadata, CSRF, JSON framing and Ingest credential checks. Server adds bounded body parsing, static containment and generic error responses. Training/model acquisition/runtime execution is not imported or implemented. Original training authorization rules are untouched; unavailable is never translated into authorized.

## Protected inventory and import closure

Protected real-data modules include `app/phase38_dataset.py`, `app/phase39_edits.py`, `scripts/complete_review_queue.py`, both `build_v007_*report.py` evaluator scripts and the historical assertion in `tests/test_phase39_mt06_repair.py`. Corpus-specific identity checks in audit/influence/verify/balancing utilities are excluded. `phase3_review.py` loads historical evaluation state; it and phase35/36/37/310/39a analysis/freeze/resolution modules are excluded too. Training/runtime/platform-state implementations are excluded conservatively because they discover historical state or include fixed runtime/model references. See [Arabic inventory](arabic-localization-exceptions.md), [privacy review](privacy-history-review.md) and [distribution policy](dataset-model-distribution-policy.md).

Direct coupling: original server imports phase3/38/39, training/runtime/platform state. Phase39 and Phase39a import phase38; Phase310 imports phase38/39 plus training; Phase35/36/37 import phase3. All remain unchanged. Builder statically resolves the entire selected Python import set, permits only selected modules or standard-library imports (pytest only for separate development tests), rejects unresolved dependencies and direct dynamic exec/eval/import calls. Exact-candidate subprocess import assertions confirm no historical/training/runtime/platform-state modules enter sys.modules. Text patterns alone are not comprehensive privacy proof; the hash-pinned selection and exclusion review are the stronger boundary.

## Previously protected source approval gate

No original protected file is edited. Compatibility changes to the original application are **BLOCKED / OWNER_APPROVAL_REQUIRED**, not silently applied. The exact first required patch would replace these original `app/server.py` imports:

```diff
-from .phase3_review import Phase3ReviewError, get_review as get_phase3_review, save_case as save_phase3_case, submit_final_decision as submit_phase3_decision
-from .phase38_dataset import get_review as get_phase38_review, save_review as save_phase38_review, freeze_gate as phase38_freeze_gate
-from .phase39_edits import apply_phase39, PHASE39, get_post_edit_verification, save_post_edit_verification
+from .research_gateway import research_extension
```

This patch alone is **not complete or executable**: each historical GET/POST route and exception branch must then delegate through the interface; direct PHASE39 file access must also be removed. It changes missing-extension behavior to structured 503 and requires private compatibility tests/owner approval before modifying that protected file. The isolated server avoids this blocked edit entirely. Similar original platform/training/runtime rewiring is deferred; no approval or private parity is claimed.

## Synthetic mode and installation

The new library-card fixtures are independently fictional, not copied/paraphrased from private records. `scripts/synthetic_demo.py --confirm-disposable` in a built candidate requires a candidate manifest and absent DB. Without the flag, or with existing DB, it refuses before changing data. Startup never calls the fixture loader or legacy demo seeding. Setup creates a no-pip venv without database creation; first launch applies only existing 001–004 migrations against candidate-local state. No planned SQL, historical dataset builder or runtime command runs during installation.

## Deterministic builder

Run `python public_source/build.py --output <separate-new-directory>` from the engineering checkout. `policy.json` maps individually approved source paths + canonical UTF-8/LF SHA256 to destination paths and explicitly classifies every other tracked/unignored source path as excluded. Those are **technical candidate approvals**, not legal redistribution approvals. Unknown/missing paths, changed selected hashes, unresolved imports, unsafe paths/symlinks, duplicate destinations and known sensitive-path/credential patterns fail closed. Ignored operational directories are not read or copied. Output must be nonexistent, outside this checkout and not through symlink parents. Builder stages atomically, emits deterministic sorted `MANIFEST.json` (no timestamps/absolute paths; UTF-8/LF bytes on all platforms), then independently verifies all names and bytes. It creates a directory only: no archive upload or release.

`--verify <pristine-candidate>` rejects extra/missing/changed files and symlinks and repeats content/import checks. A used candidate has caches/state and is deliberately no longer pristine. Preserve a clean copy. Manifest SHA256 is reproducibility/integrity evidence, not cryptographic authenticity against an attacker replacing both files and manifest. Re-pin selected files only after source review; no automatic policy regeneration is part of normal building.

## Data compatibility, rollback and remaining gates

Original schema/core service/data contracts are reused unchanged. Synthetic exports are isolated and cannot overwrite v008/v009 originals because none are supplied. Candidate dataset preparation does not authorize training or publication. Private historical test evidence is not reproduced by synthetic examples.

Rollback is an ordinary revert of this new branch's additions and documentation updates; original implementations/data stay unchanged. Generated candidate directories remain private disposable artifacts; do not delete live assets. Privacy/history, ownership/source license, copied/static provenance and exact third-party/model/data rights remain **NOT READY — BLOCKERS REMAIN**. Technical functionality does not close those legal/publication gates.

## Conservative source disposition inventory

All unselected paths are explicitly excluded in policy.json. This inventory records known protected content without reproducing values. “Excluded” is a candidate distribution decision, not deletion or reclassification of original evidence.

| Original paths | Reason / dependency exposure | Candidate disposition |
|---|---|---|
| `app/phase38_dataset.py`, `app/phase39_edits.py` | Fixed corpus construction, historical correction/repair/reviewer material; imported by original server, phase39a and phase310 | Excluded unchanged |
| `scripts/complete_review_queue.py` | Real fixed review IDs, correction manifest and identity terms; imported by its original test | Excluded unchanged |
| `scripts/build_v007_eval_report.py`, `scripts/build_v007_epoch2_report.py` | Historical evaluator ratings/annotations linked to review IDs | Excluded unchanged |
| `tests/test_phase39_mt06_repair.py` | Repeats historical original/corrected target assertions; imports phase39 | Excluded unchanged |
| `scripts/audit_v006_metrics.py`, `scripts/audit_v006_metrics_v2.py`, `scripts/audit_v006_metrics_v3.py`, `scripts/dataset_influence_audit.py`, `scripts/build_gold_v007_balanced.py`, `scripts/gold_v007_balancing.py`, `scripts/gold_v007_balancing_new.py`, `scripts/measure_v006_overlap.py`, `scripts/verify_audit.py` | Corpus-specific identity/search checks or operational research utility; not core import dependencies | Excluded unchanged |
| `scripts/export_v007_e1_ollama.py` | Historical evaluation prompts and fixed artifact workflow | Excluded unchanged |
| `app/phase3_review.py`, `phase35_analysis.py`, `phase36_readiness.py`, `phase37_hardening.py`, `phase310_freeze.py`, `phase39a_resolution.py` | Historical loaders/analysis; indirect phase imports and state coupling | Excluded unchanged |
| `app/server.py`, `platform_state.py`, `training_control.py`, `runtime_control.py` | Private/historical imports, fixed report/model/runtime discovery references | Excluded unchanged; new entry point only in candidate |
| Other original tests/scripts/docs/media | Historical IDs, artifact expectations, incomplete rights, out-of-profile behavior or unnecessary distribution surface | Excluded by default; original files preserved and discoverable |
| Core service/clean-export/quality/selection language vocabularies and synthetic examples | Reviewed as reusable logic or synthetic content, not a presumption that Arabic is private | Individually hash-pinned; rights still pending |

The direct/reverse import relationships above are baseline findings; future code changes require a new policy review. A successful static closure check is not formal proof against arbitrary Python metaprogramming; literal entry points are checked, dynamic imports/execution are rejected, and selected bytes are pinned.

Canonical source pins normalize CRLF checkout newlines to LF; they do not change source meaning. Output and manifest always use LF. A regression converts all selected text to CRLF and proves identical candidate manifests, preventing Windows checkout conversion from changing builds. Raw protected-file preservation uses the original checkout hashes separately.
