# Codebase navigation and ownership

Responsibilities below identify where changes belong, not assigned people.

| Component | Responsibility |
|---|---|
| app/server.py | Routes, response wrappers, bounded JSON, loopback and static delivery |
| app/http_security.py | Host/Origin/Fetch Metadata, CSRF and Ingest credential boundary |
| app/db.py + migrations/ | WAL/connections/transactions/redaction and startup schema |
| app/service.py | Ingest, review overlays, immutable originals, manual data and exports |
| app/review_integrity.py | Staleness/decision integrity and export blocking |
| app/dataset_platform.py | Filesystem version inventory, health, derive/freeze/release |
| app/dataset_quality.py + dataset_balancer.py | Read-only quality/dedup/balance diagnostics |
| app/dataset_registry.py + review_lifecycle.py | Prepared registry/event policy; not proof of activated production migrations |
| app/native_tool_data.py + tool_runtime.py | Tool schemas, authority, protocol contracts |
| app/training_control.py | Model/config/job/preflight and authorization |
| app/runtime_control.py | WSL runtime commands, staging, workers, attempts/recovery |
| app/evaluation_guard.py + phase3* | Provenance/comparison/review/remediation; some source holds protected data |
| static/ | Plain HTML/CSS/JS; English LTR chrome, independent Arabic direction; no bundler |
| config/ | Generic catalogs/capabilities/defaults; installation paths belong in ignored state |
| migrations/ | Startup-executed 001–004 only; no proposed SQL as incidental cleanup |
| plans/ | Unapproved SQL/proposals, outside loader |
| scripts/ | Setup/launch/backup and explicit audit/ML utilities; historical imports may have effects |
| tests/ | Synthetic regression and explicit private historical-artifact checks |
| docs/ | Current guides/status plus dated historical records, Corpus design and ADRs |

Generated data/datasets/exports/training/reports/checkpoints/backups are private state, not source assets. WSL models/environments and Hermes are optional external integrations with separate authorization. See [architecture](architecture.md) and [handover](maintainer-handover.md).
