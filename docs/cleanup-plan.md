# Dataset-only repository cleanup: audit and implementation record

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](user-guide.md) for present operation.

## Authority and verified base

The owner's 2026-11-01 scope is Chat Workspace → Review/correction → Dataset Quality → Dataset Versioning → External Unsloth Export. This is the existing project, not a rewrite. GitHub was read before editing: PR11 Draft/open/unmerged at aa328ffa24350097b50619b331cf1b2eff97fb8d; PR12 Draft/open/unmerged at a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9. Source/candidate runs 41242700517/41242700524 and 41276046497/41276046509 respectively completed successfully. PR12 Windows/Linux source jobs were individually checked.

An independent clone under the Codex project workspace was branched as refactor/remove-legacy-training from the exact PR12 SHA. Existing feature branches, main and the installed Documents copy were not changed. No push, PR, merge, deployment, owner inference, WSL operation or service/configuration modification is authorized or performed.

## Initial read-only audit findings, reported before implementation

All tracked paths, Python imports/functions, scripts, frontend assets, Markdown (including nested Corpus/plan/Core/.github trees), CI/install/public-source policy and SQL dependencies were inventoried. Retirement was incomplete: training/runtime controllers still owned acquisition, WSL staging/workers, jobs/attempts/logs, authorization, execution/recovery and deployment. Trainer/benchmark/GGUF implementations remained callable beneath early executable refusal. Base/Adapter comparison UI and APIs remained. Documentation still described conflicting products.

REMOVE: those controllers and execution scripts, runtime-evaluation reports and comparison UI/APIs, retirement shims, training-only tests, unused training registry proposal and rollback SQL, obsolete operational/planning Markdown and misleading media.

REFACTOR: pure supervision-mask verification from the trainer; native-record, quality and freeze gates from the controller; pure tool-schema/serialization from the execution module; dataset catalog from phase/job status. Dataset-only tests mixed into execution suites must survive.

KEEP: own Chat, LM Studio/Ollama inference providers, raw history, human review/correction, manual records, quality/dedup/holdout checks, immutable versions, external Unsloth handoff, privacy/provenance/security and candidate isolation.

PROTECT: all applied migrations001–006 and persisted eligibility/privacy keys; historical private databases/datasets/exports/models/backups and their evidence; backup contracts. No data or schema migration is required. The removed plans SQL was outside the startup loader and had no application consumers; it was not executed or rolled back.

The complete base-file classifications/hashes and removed route patterns are in [inventory](cleanup-inventory.json). This records absent historical paths as evidence, not supported operational references.

## Behavior and ownership decisions

- Extract pure helpers to app/dataset_masks.py and app/dataset_validation.py. Move tool-schema/canonicalization to app/dataset_tools.py; remove controller/generation/benchmark execution. No legacy wrappers or aliases remain.
- Keep persisted training_eligible, exclude_from_training, split/readiness/count/fingerprint metadata and external completion-only contracts. They describe dataset selection/interoperability; renaming them would create an unnecessary compatibility migration.
- Keep Chat engine/worker/workspace/integrations and Unsloth export implementation byte-identical. A Chat SDK transport worker is inference IPC, not a training worker.
- Rename HTTP dataset selection/manual-authoring paths to dataset-records and manual-data. Remove execution/phase3/status routes completely; unknown requests return ordinary404. The Core candidate's unused execution-extension shim is also deleted.
- Offline mask CLI takes an existing local tokenizer directory with local_files_only=True and trust_remote_code=False. AutoTokenizer is optional validation tooling; no weights, model discovery/download, inference or training stack is included.
- Keep dataset remediation review and historical contamination-source reads: they validate/review datasets and protect old evidence without evaluating a running model.

## Implementation and proof sequence

- [x] Verify remote base/CI and isolated branch; audit before edits.
- [x] Add failing boundary checks; extract shared data checks before deleting their owners.
- [x] Remove backend execution and retired routes; migrate dataset routes and retained tests.
- [x] Remove frontend views/handlers/CSS and update visible dataset terminology.
- [x] Delete/consolidate obsolete Markdown; preserve rights/security/migration limitations and synchronize diagrams/indexes.
- [x] Run synthetic Windows, Node/browser, docs, import, schema and policy checks; retain failures/skips distinctly.
- [x] Rebuild/verify source-only candidate and run candidate regressions/browser checks on final mapped files.
- [x] Final inventory, independent review, source-only local commits and final evidence.

## Rollback and limits

Source rollback means reverting these local cleanup commits on a separate review branch, or creating a fresh checkout of the verified base. Do not launch old source against private data, restore databases, remove migration ledger rows or rewrite immutable exports as part of rollback. Earlier source reintroduces removed interfaces; review before any later installation.

No native Linux execution environment is available here and WSL is excluded. Shell syntax and portable tests can run on Windows; base hosted Linux success does not establish cleanup-head Linux success. Real installed-model/GPU/owner acceptance and publication/history rights remain separate unverified gates. See [results](cleanup-results.md), [migration safety](database-and-migrations.md), [privacy](privacy-history-review.md) and [prior evidence](verification-evidence.md).
