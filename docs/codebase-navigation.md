# Codebase navigation

| Component | Responsibility |
|---|---|
| app/server.py, http_security.py | Loopback request boundary, JSON/CSRF/ingest checks, routes and static delivery |
| app/chat_workspace.py, chat_engine.py, chat_engine_worker.py | Own complete Chat receipts, consent, exact context admission and bounded local engine access |
| app/integrations.py, hardware.py | Session-only connector consent and explicitly labeled device evidence |
| app/db.py, migrations/ | SQLite originals/overlays/manual/Chat metadata; startup migration caveats |
| app/service.py, review_integrity.py, review_lifecycle.py | Ingest, review/manual data, export readiness and optional event contracts |
| app/clean_export.py, dataset_platform.py | Deterministic dataset selection, files, versions, manifests and freeze |
| app/dataset_masks.py, dataset_validation.py, dataset_tools.py | Shared dataset supervision, validation and pure tool-schema/canonicalization helpers |
| app/dataset_quality.py, dataset_balancer.py | Read-only diagnostics, duplicate/holdout/balance checks |
| app/dataset_registry.py, platform_state.py | Prepared dataset registry and local dataset catalog; no platform execution status |
| app/phase38_dataset.py, phase39_edits.py, phase39a_resolution.py, phase310_freeze.py | Dataset-specific remediation/review/freeze evidence; private records require rights/privacy care |
| app/unsloth_export.py | Immutable external conversational handoff and provenance |
| static/ | Framework-free HTML/CSS/JS; English controls, independent Arabic direction |
| scripts/ | Setup, launch, private backup, documentation and dataset validation utilities |
| public_source/ | Separately built and hash-reviewed reduced Core profile |
| tests/, docs/ | Synthetic verification and explicit evidence/limitations |

Private operational directories are not source artifacts. Local model services are externally managed; no trainer/runtime deployment path is supplied. [Architecture](architecture.md), [migrations](database-and-migrations.md), [review](review-and-quality.md).
