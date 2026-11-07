# Dataset-only cleanup results — 2026-11-01

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](user-guide.md) for present operation.

**PASS: repository cleanup and available synthetic Windows checks.** This verdict is not installed-model acceptance, fresh Linux-host qualification, publication or deployment approval. No push/PR/merge/deployment or installed-copy update was performed.

## Audit and source isolation

[Initial read-only audit, decisions and implementation](cleanup-plan.md) were reported before edits. [Dependency inventory](cleanup-inventory.json) classifies all 354 base paths as REMOVE/REFACTOR/KEEP/PROTECT, records Git SHA256/import/declaration evidence, removed route patterns and a legitimate-terminology allowlist. Base PR #12 is a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9; PR #11/#12 remained Draft/open/unmerged when checked. Both base source/candidate workflows were successful; PR #12 HEAD was rechecked unchanged after work. Cleanup HEAD has no hosted CI because no push is authorized.

Working copy: isolated NajdiLab-training-cleanup under the Codex project workspace. Branch: refactor/remove-legacy-training. Existing main/feature branches and Documents installation were not modified. Local commits and their exact ancestry are available with `git log`; the final delivery response records HEAD.

## Removal and shared ownership

Deleted controllers and scripts contained training configuration/registries/acquisition, WSL probing/staging/workers, authorization/smoke/full jobs and attempts/logs/recovery, adapter deployment/validation, trainer/collator/model-loading code, model benchmarks/comparison and GGUF/merge workflows. No disabled implementation, early-refusal wrapper or execution compatibility endpoint remains. The unused Core extension interface is removed as well.

Pure supervision checks moved from the trainer to app/dataset_masks.py. Native dataset validation, quality_gate and freeze_readiness_gate moved from the controller to app/dataset_validation.py. Pure capability schemas, call parsing and canonicalization moved to app/dataset_tools.py; controller execution/generation/benchmark helpers were removed. app/platform_state.py now owns only the dataset catalog. Dataset gate and mask tests mixed into deleted execution suites were retained under current dataset suites.

The offline validator is scripts/validate_dataset_masks.py: explicit existing local tokenizer directory, local_files_only=True, trust_remote_code=False, no weights or inference. Its optional AutoTokenizer dependency is validation tooling, not an application training runtime. The v007 dataset builder uses that explicit validator without a fixed WSL/model path. Unused live-inference probing and unsupported training-configuration conclusions were removed from old dataset analysis scripts.

## API and interface

All 47 execution/status route arms documented in the machine inventory are removed, including training datasets/quality aliases, model registration/discovery/acquisition, runtime checks/staging/workers, jobs/attempts/logs/metrics, smoke/full authorization/execution/recovery/cancel, adapter deployment/verification, Base/Adapter human comparison and platform training-phase status. Former requests return ordinary 404 after ordinary request security; no 410 shim/read-only job compatibility implementation remains.

Dataset selection is now GET /api/v1/dataset-records. Manual creation uses POST /api/v1/manual-data/sft, /direct and /preference. No obsolete aliases are registered. Quality-findings, release-validation, health, review, version and Unsloth endpoints remain; [generated complete API inventory](api-routes.md) is synchronized.

Removed training/retired views, path mappings/redirects, Base/Adapter comparison controls/handlers/state, training/job/model/preflight styles and unused localization entries. Dataset-visible labels now describe records, eligibility and export readiness. Persistent schema flags and DOM bindings remain compatible. Dataset remediation review remains available. Chat JS has only an archive-confirmation wording change; inference protocol/security implementation is preserved.

## Regression results

| Check | Passed | Failed | Skipped | Extra evidence |
|---|---:|---:|---:|---|
| Final application pytest suite, Windows Python 3.12, pinned SDK 1.5.0 | 416 | 0 | 32 | 59 subtests passed |
| Final built Core candidate suite, Windows | 75 | 0 | 3 | 68 subtests passed |
| Candidate builder | 12 | 0 | 0 | 18 subtests passed |
| Node Chat/integration controllers | 10 | 0 | 0 | both controller files |
| Focused post-edit boundary/gates/quality/localization/docs | 27 | 0 | 0 | final source helpers/imports |
| Root real-browser synthetic acceptance | 1 suite | 0 | 0 | raw HTML/Arabic, consent/PENDING, history, rollover, Stop, Ollama approval, absent training views/routes |
| Candidate real-browser synthetic acceptance | 4 groups | 0 | 0 | review, dataset, explicit artifacts/backup/restore, fresh-source resume |
| Candidate manifest-copy harness | 1 group | 0 | 0 | rejects non-candidate, tamper, traversal before execution |

Application 32 skips:9 explicit real-Ollama opt-in checks,22 absent-private-artifact checks and1 Windows symlink capability check. Optional SDK synthetic tests ran after installing only into this isolated checkout's venv. Candidate 3 skips are actual Windows symlink privilege limitations; unsupported link checks are not passes. Linux symlink behavior remains unverified locally.

Additional proof: all 63 current Markdown files checked recursively, including .github/public_source; local file links and generated API inventory resolve. Python compilation, JS syntax/controller checks, application prerequisite check, git diff whitespace checks and three POSIX shell syntax checks pass. Both architecture SVGs regenerate/parse deterministically; main SVG rendered and inspected with 38 labels/no overlap/out-of-bounds. Six applied migration contents and preserved Chat/security/export/backup sources match base hashes. Synthetic forward/repeat migration application preserves rows and passes integrity/FK checks. No training-only package remains in requirements.

No native Linux runtime was available; WSL operations were excluded. Git Bash syntax-only checks passed for run.sh/install.sh/backup.sh. Base hosted Windows/Linux success is dated base evidence, not a cleanup-head result.

## Failures retained and resolved

Initial restricted-sandbox base run:355 passed,140 failed,37 skipped; loopback was denied with WinError10013. Unchanged isolated base with loopback:447 passed,0 failed,37 skipped/68 subtests. The first cleaned run without optional SDK:405 passed,0 failed,36 skipped/59 subtests. Counts differ because execution tests were removed and dataset/boundary coverage added; they are not like-for-like performance scores.

New boundary checks first failed on retained controller source and registered endpoints, then passed after removal. Recursive-doc regression first missed public/.github links, then passed after checker expansion. Builder fallback initially included ignored browser artifacts (9 passed / 2 failed); its focused failing regression now passes after treating .test-tmp as disposable, matching Git inventory. Root/candidate browser tests initially expected deleted retired/503-shim behavior; updated absence/404 assertions pass.

Initial candidate Windows suite 58 passed/15 failed, with symlink privilege failures and fixture lock teardown (57 subtests). Fixture-only changes now stop/wait on the exact owned Windows PID tree before resetting synthetic storage, fail closed on shutdown/path errors, and probe link capability before touching fixture originals. Four lifecycle regressions and an independent delta review pass. Existing production storage/backup/restore guards remain unchanged. Staging-backup coverage is separate from skipped link checks. Final rebuilt candidate 75 passed/0 failed/3 explicit skips. No owner service was stopped; read-only diagnostic matching found no surviving task-owned synthetic servers.

## Security, compatibility and remaining limits

PR #12 immutable local Ollama digest binding, local-only/version enforcement, exact admission/rollover, Stop metadata cancellation, model/session identity and atomic consent/persistence are unchanged and covered by synthetic regressions. app/chat_engine.py, chat_engine_worker.py, chat_workspace.py, integrations.py and unsloth_export.py are byte-identical to the base. Hermes stays BLOCKED. Consent defaults/restart OFF; complete opted-in pairs remain PENDING and ineligible until review. Human correction, raw immutability, quality/dedup/leakage, versions, privacy and completion-only handoff remain covered.

No protected database, dataset, export, weight, checkpoint, backup or applied migration was deleted. migrations 001–006 are unchanged; no migration was added/applied to private data, renumbered, reversed or put into startup. The removed planned training SQL lived outside migrations/ and has no active consumers; removing source proposals does not remove any existing table or owner's manually applied history. Dataset registry/review-event proposal files remain unchanged. Persistent training_eligible/exclude_from_training and split/count/readiness/fingerprint/export keys remain. No destructive schema decision is needed.

Legacy dataset metadata terminology is an explicit compatibility allowlist, not retained orchestration. Negative tests, ignored/private-path guards, source/rights evidence and historical holdout/provenance reads also legitimately mention removed concepts without executing them. The current Core map has 71 selected files; its restricted profile still excludes Chat/external handoff and is not advertised as the full application.

Known unchanged limits: actual installed LM Studio/Ollama/Gemma4 acceptance and hardware safety are unverified; Ollama resolver support is pinned 0.40.13; exact real tokenizer/template behavior needs external acceptance. Missing private remediation artifacts are not validated by synthetic tests. Existing migration filename-ledger/crash-gap caveats, trusted single-operator reviewer identity/manual-history limits, HMAC freshness, historical-export privacy/retention and unresolved rights/history/publication gates remain documented. Source cleanup does not sanitize historical Git or certify linguistic truth/consent/redistribution rights. See [migration safety](database-and-migrations.md), [review](review-and-quality.md), [Chat limits](chat-completion-results.md), [privacy](privacy-history-review.md), [rights](rights-evidence.md).

## Rollback

No application update or data migration occurred, so rollback requires source only. Preserve this branch and evidence. Create another isolated checkout at a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9, or revert the cleanup commits on a separately reviewed branch. Do not reset shared history, overwrite installed code, launch old source against private data, delete ledger rows, remove exports/backups or perform a database restore. Old source reintroduces removed interfaces; inspect it before any separately authorized installation. [Backup/restore contract](backup-and-restore.md) remains independently applicable.

## Complete changed-file inventory

Paths below are deliberately retained as removal/refactor evidence. They are not operational links to deleted files. Full base dependency classifications and hashes are in cleanup-inventory.json.

### Files deleted (including extracted/renamed originals)

- `app/evaluation_guard.py`
- `app/generation_hardening.py`
- `app/phase35_analysis.py`
- `app/phase36_readiness.py`
- `app/phase37_hardening.py`
- `app/phase3_review.py`
- `app/runtime_control.py`
- `app/tool_runtime.py`
- `app/training_control.py`
- `docs/corpus-v1.1/01-behavior-spec.md`
- `docs/corpus-v1.1/02-component-reuse-map.md`
- `docs/corpus-v1.1/03-review-lifecycle.md`
- `docs/corpus-v1.1/04-quality-gates.md`
- `docs/corpus-v1.1/05-security-prerequisites.md`
- `docs/corpus-v1.1/06-adapter-drift-k2.md`
- `docs/corpus-v1.1/07-migration-review-005-007.md`
- `docs/corpus-v1.1/08-risk-register.md`
- `docs/corpus-v1.1/09-implementation-roadmap.md`
- `docs/corpus-v1.1/10-test-plan.md`
- `docs/corpus-v1.1/11-rollback-plan.md`
- `docs/corpus-v1.1/12-traceability-matrix.md`
- `docs/corpus-v1.1/13-decision-register.md`
- `docs/corpus-v1.1/14-git-working-tree-inventory.md`
- `docs/corpus-v1.1/15-migration-loader-guard.md`
- `docs/corpus-v1.1/16-ui-first-confirmation.md`
- `docs/corpus-v1.1/17-phase1-approval-package.md`
- `docs/corpus-v1.1/README.md`
- `docs/corpus-v1.1/adr/ADR-001-najdilab-single-source-of-truth.md`
- `docs/corpus-v1.1/adr/ADR-002-conversational-sft-objective.md`
- `docs/corpus-v1.1/adr/ADR-003-tiers-as-provenance.md`
- `docs/corpus-v1.1/adr/ADR-004-human-approval-required-for-eligibility.md`
- `docs/corpus-v1.1/adr/ADR-005-g2-deterministic-only.md`
- `docs/corpus-v1.1/adr/ADR-006-security-before-generation.md`
- `docs/corpus-v1.1/adr/ADR-007-bronze-deferred.md`
- `docs/corpus-v1.1/adr/ADR-008-corpus-v1-archive-only.md`
- `docs/corpus-v1.1/adr/ADR-009-adapter-reconciliation-by-verification.md`
- `docs/corpus-v1.1/adr/ADR-010-migration-loader-guard.md`
- `docs/corpus-v1.1/adr/ADR-011-naturalness-without-quotas.md`
- `docs/data-03-04-06-09-review-management.md`
- `docs/data-07-08-review-integrity-export-readiness.md`
- `docs/dataset-and-training.md`
- `docs/dataset-chat-results.md`
- `docs/historical-project-status.md`
- `docs/images/architecture/najdilab-system-architecture-preview.png`
- `docs/images/architecture/owner-conceptual-architecture.jpg`
- `docs/images/screenshots/conversation-review.png`
- `docs/images/screenshots/correction-overlay.png`
- `docs/images/screenshots/dashboard.png`
- `docs/images/screenshots/dataset-health.png`
- `docs/images/screenshots/human-review.png`
- `docs/images/screenshots/training-data.png`
- `docs/images/screenshots/training-setup.png`
- `docs/installation-verification.md`
- `docs/master-execution-board.md`
- `docs/model-selection-guide.md`
- `docs/next-training-execution-plan.md`
- `docs/phase-0-audit.md`
- `docs/phase-1-foundation-backlog.md`
- `docs/phase-1.3-registry-runbook.md`
- `docs/phase-2-4-current-state-audit.md`
- `docs/public-core-feature-parity.md`
- `docs/public-core-phase5-execution.md`
- `docs/public-core-phase5-issue-register.md`
- `docs/public-core-phase5-rights.md`
- `docs/public-core-phase5-verification.md`
- `docs/public-source-isolation-report.md`
- `docs/scope-audit-2026-10-31.md`
- `docs/superpowers/plans/2026-10-26-english-open-source-readiness.md`
- `docs/superpowers/plans/2026-10-31-dataset-chat.md`
- `docs/superpowers/plans/2026-10-31-integrations.md`
- `docs/superpowers/specs/2026-10-31-dataset-chat-design.md`
- `docs/superpowers/specs/2026-10-31-integrations-design.md`
- `docs/tool-runtime-contract.md`
- `docs/training-export.md`
- `docs/training-preflight-runbook.md`
- `docs/training-readiness-sprint-report.md`
- `docs/unified-readiness-verification.md`
- `docs/verification-and-readiness-report.md`
- `docs/visual-documentation-verification.md`
- `docs/worklogs/english-open-source-readiness.md`
- `docs/worklogs/public-release-remediation.md`
- `plans/training-readiness/007_model_training_registry.rollback.sql`
- `plans/training-readiness/007_model_training_registry.sql`
- `public_source/docs/initial-profile.md`
- `public_source/extensions.py`
- `scripts/build_v007_epoch2_report.py`
- `scripts/build_v007_eval_report.py`
- `scripts/export_v007_e1_ollama.py`
- `scripts/najdilab_training_adapter.py`
- `scripts/phase3_benchmark.py`
- `scripts/run_gold_v004_controlled.py`
- `scripts/run_gold_v006_controlled.py`
- `scripts/run_gold_v007_balanced.py`
- `scripts/run_gold_v007_epoch2.py`
- `scripts/smoke_train_najdi_sft.py`
- `scripts/train_najdi_sft.py`
- `scripts/validate_training_masks.py`
- `tests/test_arabic_training_ui.py`
- `tests/test_model_selection_contract.py`
- `tests/test_phase311_training_adapter.py`
- `tests/test_phase35_analysis.py`
- `tests/test_phase36_readiness.py`
- `tests/test_phase37_tool_hardening.py`
- `tests/test_phase3_benchmark.py`
- `tests/test_phase3_review.py`
- `tests/test_runtime_control.py`
- `tests/test_safe_adapter_deployment.py`
- `tests/test_safe_adapter_deployment_simple.py`
- `tests/test_training_adapter.py`
- `tests/test_training_control.py`
- `tests/test_training_plan_mismatch_regression.py`
- `tests/test_training_plan_mismatch_unit.py`
- `tests/test_training_registry_migration.py`

### Files refactored or rewritten

- `.github/ISSUE_TEMPLATE/feature_request.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `PROJECT_STATUS.md`
- `README.md`
- `SECURITY.md`
- `app/dataset_platform.py`
- `app/native_tool_data.py`
- `app/phase310_freeze.py`
- `app/phase38_dataset.py`
- `app/phase39_edits.py`
- `app/platform_state.py`
- `app/server.py`
- `docs/api-reference.md`
- `docs/api-routes.md`
- `docs/arabic-localization-exceptions.md`
- `docs/architecture-diagrams.md`
- `docs/architecture.md`
- `docs/asset-provenance.md`
- `docs/backup-and-restore.md`
- `docs/chat-workspace.md`
- `docs/codebase-navigation.md`
- `docs/configuration.md`
- `docs/database-and-migrations.md`
- `docs/database-schema.md`
- `docs/dataset-model-distribution-policy.md`
- `docs/dependencies-and-attribution.md`
- `docs/dependency-licensing-matrix.md`
- `docs/developer-setup.md`
- `docs/documentation-index.md`
- `docs/github-presentation.md`
- `docs/images/architecture/generate_architecture.py`
- `docs/images/architecture/najdilab-system-architecture.svg`
- `docs/installation.md`
- `docs/integrations.md`
- `docs/maintainer-handover.md`
- `docs/open-source-readiness.md`
- `docs/public-core-release-scope.md`
- `docs/public-core-user-guide.md`
- `docs/public-private-boundary.md`
- `docs/public-release-decision.md`
- `docs/roadmap.md`
- `docs/screenshots.md`
- `docs/source-provenance.md`
- `docs/system-requirements.md`
- `docs/third-party-attributions.md`
- `docs/troubleshooting.md`
- `docs/user-guide.md`
- `public_source/CONTRIBUTING.md`
- `public_source/README.md`
- `public_source/build.py`
- `public_source/docs/api.md`
- `public_source/docs/architecture.md`
- `public_source/docs/generate_architecture.py`
- `public_source/docs/images/core-architecture.svg`
- `public_source/policy.json`
- `public_source/server.py`
- `public_source/static/app.js`
- `public_source/static/index.html`
- `public_source/tests/artifacts.py`
- `public_source/tests/browser.cjs`
- `public_source/tests/contract.py`
- `public_source/tests/datasets.py`
- `public_source/tests/support.py`
- `public_source/tests/test_builder.py`
- `scripts/build_gold_v007_balanced.py`
- `scripts/check_docs.py`
- `scripts/dataset_influence_audit.py`
- `scripts/generate_api_reference.py`
- `scripts/verify_audit.py`
- `static/app.js`
- `static/chat.js`
- `static/index.html`
- `static/localization.js`
- `static/phase1.css`
- `static/rtl-overhaul.css`
- `static/styles.css`
- `static/theme.css`
- `tests/chat-browser.cjs`
- `tests/test_backend_localization.py`
- `tests/test_chat_http.py`
- `tests/test_dataset_quality.py`
- `tests/test_dataset_scope_ui.py`
- `tests/test_najdilab.py`
- `tests/test_phase310_gates.py`
- `tests/test_phase38_dataset.py`
- `tests/test_platform_state.py`
- `tests/test_script_portability.py`

### Files added (extractions, consolidated documentation and regressions)

- `app/dataset_masks.py`
- `app/dataset_tools.py`
- `app/dataset_validation.py`
- `docs/cleanup-inventory.json`
- `docs/cleanup-plan.md`
- `docs/cleanup-results.md`
- `docs/dataset-export.md`
- `docs/review-and-quality.md`
- `docs/rights-evidence.md`
- `docs/verification-evidence.md`
- `scripts/validate_dataset_masks.py`
- `tests/test_dataset_boundary.py`
- `tests/test_dataset_gates.py`
- `tests/test_dataset_ui.py`
- `tests/test_dataset_validation_extraction.py`
- `tests/test_docs_integrity.py`
- `tests/test_native_dataset.py`


Candidate final manifest SHA256: `c8d81fa90d9158197284f1c52894135e81c0c557cc7e1c1ef5fed094787541e8`; 71 selected files, publication_approved=false. The manifest is integrity evidence, not authenticity or rights clearance.
