# English localization and public release audit

Decision: **NOT READY — BLOCKERS REMAIN** for public publication. The private development branch is prepared for owner review; this report does not authorize merge, deployment, a release, history rewriting or a final source license.

## Changes and localization accounting

The working branch is `dev/english-open-source-readiness`, based on commit `85c39ac3f4e15db916d46db22e05095cca10a286`. Main remains the original baseline.

**38 existing files were localized** (existing files whose Arabic presentation text was removed/replaced, excluding newly authored English guides). Additional files provide English documentation, request-boundary security, regressions and audit records. Files already in English were also sanitized where they disclosed private machine/backup details.

| Existing file | Arabic-bearing lines before | After |
|---|---:|---:|
| `README.md` | 2 | 0 |
| `app/clean_export.py` | 18 | 14 |
| `app/dataset_balancer.py` | 23 | 0 |
| `app/dataset_platform.py` | 46 | 1 |
| `app/dataset_quality.py` | 8 | 0 |
| `app/evaluation_guard.py` | 4 | 0 |
| `app/review_integrity.py` | 23 | 0 |
| `app/runtime_control.py` | 32 | 0 |
| `app/server.py` | 17 | 0 |
| `app/service.py` | 107 | 18 |
| `app/training_control.py` | 67 | 0 |
| `docs/architecture.md` | 27 | 0 |
| `docs/corpus-v1.1/01-behavior-spec.md` | 25 | 24 |
| `docs/corpus-v1.1/14-git-working-tree-inventory.md` | 1 | 0 |
| `docs/database-schema.md` | 24 | 0 |
| `docs/hermes-integration.md` | 16 | 0 |
| `docs/model-selection-guide.md` | 16 | 0 |
| `docs/next-training-execution-plan.md` | 15 | 0 |
| `docs/training-export.md` | 21 | 0 |
| `docs/training-preflight-runbook.md` | 22 | 0 |
| `docs/training-readiness-sprint-report.md` | 38 | 0 |
| `scripts/NajdiLab_Autostart.ps1` | 1 | 0 |
| `scripts/audit_v006_metrics_v3.py` | 7 | 2 |
| `scripts/ingest_test.py` | 4 | 2 |
| `scripts/inspect_multi_turn_stats.py` | 2 | 0 |
| `scripts/inspect_v006_schema.py` | 15 | 0 |
| `scripts/najdilab_training_adapter.py` | 5 | 0 |
| `scripts/verify_audit.py` | 23 | 22 |
| `static/app.js` | 184 | 1 |
| `static/index.html` | 169 | 0 |
| `static/localization.js` | 13 | 0 |
| `static/phase38-review.html` | 1 | 0 |
| `static/theme.js` | 1 | 0 |
| `tests/test_arabic_training_ui.py` | 5 | 0 |
| `tests/test_dataset_platform.py` | 8 | 7 |
| `tests/test_najdilab.py` | 117 | 110 |
| `tests/test_phase38_ui.py` | 4 | 3 |
| `tests/test_runtime_control.py` | 5 | 2 |

English is the default UI locale; the shell is LTR. Arabic conversations, editors, review content and multilingual notes use independent direction. All 113 existing HTML input/option values and the three legacy Arabic Phase 3.9 decision enums were preserved. API field names, schema/migration files and data identifiers were not renamed.

Arabic remains intentionally in **43 files**. The [complete exception inventory](arabic-localization-exceptions.md) gives every file, line and reason. Categories include corpus construction/training examples, actual historical corrections/evaluator annotations, normalization/Arabic detection vocabularies, synthetic Arabic tests/demo conversations, documentation's linguistic examples, and compatibility enum values. These protected values were not translated. Preserving an actual-data module does not clear it for public distribution.

## Confirmed security findings and fixes

| Confirmed baseline finding | Change and proof |
|---|---|
| Untrusted Host allowed DNS-rebinding reads/writes | Exact loopback authority/listening-port validation before all routes, static requests and unsupported methods; duplicate/malformed headers rejected |
| Cross-origin requests could read or reach mutations | Origin and Fetch Metadata checks reject foreign/null origins and cross-site requests; no permissive CORS responses |
| `text/plain` JSON could reach write handlers | JSON content type required for mutations; ambiguous body framing rejected and body size bounded |
| No CSRF protection on browser or ordinary native writes | Same-origin session bootstrap; token required on every non-ingest mutation and on browser ingest; existing full-training single-use authorization remains additional |
| Ingest accepted unauthenticated native requests | Owner-selected fail-closed default; configured bearer secret or Hermes raw-body HMAC required; explicit warned legacy compatibility switch only |
| Export-readiness fields entered `innerHTML` without escaping | Escaped both sample identifier and reason; hostile HTML and Arabic preservation regression |
| Missing-secret collector smoke script would attempt network | Script exits before network without configured secret; acceptance utility requires explicit disposable-write opt-in and configured Hermes checkout/secret |

Security regressions failed before fixes and passed after them. The implementation's focused security suite has 19 tests. Independent review passed 20 raw HTTP probes and four JavaScript behavior checks, then confirmed that CSRF cannot substitute for ingest authentication or override a different-port Origin. No unresolved confirmed web-boundary bypass was found by that review.

This remains a single trusted local-operator application. Native programs on that computer can obtain local request-intent sessions and access the local APIs; this is not multi-user identity/RBAC isolation. HMAC signing authenticates bytes but does not add freshness/replay protection. Resource/path diagnostics remain visible to trusted local clients. These are explicit deployment limits/potential risks, not claimed fixes or support for a shared/public network service.

## Tests, browser verification and data protection

| Check | Result |
|---|---|
| Baseline complete suite with authorized private fixture copies | 257 passed, 8 subtests |
| Final complete suite, `python -m pytest -q tests -p no:cacheprovider` | **301 passed, 68 subtests**, one pre-existing return-value warning |
| Same source without private operational fixtures | **278 passed, 23 explicitly skipped**, 68 subtests, one existing warning; historical private-artifact prerequisites are declared. Earlier source-only baseline was 267 passed / 24 failed and is preserved as failed-run evidence |
| Independent security review | 20 raw HTTP probes and four JS checks passed; no blocking finding |
| Independent localization/data-contract review | No unresolved substantive issue; broken PowerShell commands found and independently confirmed repaired |
| Real browser, synthetic-only instance | English/LTR navigation and controls; Arabic input/save/readback exact; Arabic editors RTL and English notes LTR; no console errors/warnings |
| Light/dark modal metadata | Observed low contrast fixed; 18 component color pairs checked at >=4.5:1 in both themes and visually rechecked |
| Original protected data/artifacts | **317 files** matched their initial SHA256 fingerprints; no originals changed |
| Protected data-bearing source | Corpus builder, real correction module and both historical evaluator annotation modules retained unchanged |
| API/migration compatibility | Schema/config files unchanged; machine-readable codes and legacy decisions retained |
| Syntax and onboarding | Python/JS parse checks and documentation links/API inventory passed; clean/repeated Windows and Ubuntu/WSL setup, launch/health/conflict/shutdown and synthetic backup/restore exercised; see installation-verification.md |

The full suite covers review lifecycle, export/Gold integrity, deterministic splits, Arabic masking/normalization, runtime gates, mocked training planning/authorization and evaluation safeguards. No real training, model download, evaluation workload, migration proposal, adapter deployment or production service restart was performed. Private fixture copies and a SQLite online snapshot were used in the isolated development checkout. The local backup volume was not accessed or modified.

The legacy `test_training_plan_mismatch_unit.py` test still returns an integer, producing `PytestReturnNotNoneWarning`; its assertions pass. Historical scripts also retain known limitations documented by the audit: an unfinished balancing helper, a legacy report-path mismatch, an audit variant missing a runtime import and a fixed autostart port. They were not run as workloads, and syntax/portability checks do not claim they are operationally correct.

### Preserved earlier code-only failures and their resolution

The earlier run below failed 24 cases. In the expanded task, 23 tests now declare their exact private-artifact prerequisites and report SKIP only for absent files (corrupt present files still fail). The missing-registered-path test was made self-contained with an empty temporary registry and now passes without private data. No original failed log was deleted and no private fixture was published. Historical failures:

- `tests/test_dataset_balancer.py::DatasetBalancerHttpTests::test_balance_endpoint_200_and_structured_404`
- `tests/test_dataset_platform.py::DatasetPlatformHttpIntegrationTests::test_missing_registered_path_reports_structured_error`
- `tests/test_dataset_platform.py::DatasetPlatformHttpIntegrationTests::test_real_endpoint_finds_v007_from_different_working_directory`
- `tests/test_dataset_platform.py::DatasetPlatformHttpIntegrationTests::test_v009_managed_draft_is_registered_and_readable`
- `tests/test_phase310_gates.py::Phase310GateTests::test_current_v009_gate_semantics_and_66_masks`
- `tests/test_phase310_gates.py::Phase310GateTests::test_stale_diagnostic_fingerprint_is_rejected`
- `tests/test_phase37_tool_hardening.py::Phase37Tests::test_report_generation_preserves_historical_phase3_artifacts`
- `tests/test_phase38_dataset.py::Phase38Tests::test_contamination_gates_and_near_duplicate_queue`
- `tests/test_phase38_dataset.py::Phase38Tests::test_conversation_overlap_detection_basis`
- `tests/test_phase38_dataset.py::Phase38Tests::test_coverage_targets_met`
- `tests/test_phase38_dataset.py::Phase38Tests::test_fresh_holdout_is_independent_eval_only`
- `tests/test_phase38_dataset.py::Phase38Tests::test_holdout_cannot_become_training_data`
- `tests/test_phase38_dataset.py::Phase38Tests::test_inherited_and_phase3_fingerprints_valid`
- `tests/test_phase38_dataset.py::Phase38Tests::test_native_tool_validation_and_loss_masks`
- `tests/test_phase38_dataset.py::Phase38Tests::test_review_freeze_gate_incomplete_rejected_and_contamination`
- `tests/test_phase38_dataset.py::Phase38Tests::test_v009_derived_without_v008_mutation_and_counts`
- `tests/test_phase38_ui.py::Phase38UiTests::test_approve_edit_reject_persistence_without_touching_real_queue`
- `tests/test_phase38_ui.py::Phase38UiTests::test_review_queue_contains_only_expected_new_records`
- `tests/test_phase39_api.py::Phase39ApiTests::test_invalid_record_id_is_structured_not_found`
- `tests/test_phase39_edits.py::Phase39Tests::test_audit_and_verification_queue_are_focused_and_incomplete`
- `tests/test_phase39_edits.py::Phase39Tests::test_exactly_seven_edits_and_twenty_nine_approvals`
- `tests/test_phase39_edits.py::Phase39Tests::test_freeze_readiness_stays_blocked`
- `tests/test_phase39_edits.py::Phase39Tests::test_native_tool_evidence_and_registry_remain_protected`
- `tests/test_phase39_mt06_repair.py::Mt06RepairTests::test_mt06_targets_turn_four_only_and_queue_is_updated`

## Privacy and history review

All 188 reachable historical file blobs across the original three commits were scanned, along with commit metadata and every current tracked/new candidate. Pattern and high-entropy scans found no actual credential material; matches were synthetic secret/phone sentinels and original author metadata. Manual review classified those matches.

**Confirmed release blockers remain:** historical author identifiers, 26 private Windows-path occurrences across historical blob versions, two historical local backup-location matches, and data-bearing source containing real correction/evaluation material and corpus-specific identity terms. Counts describe scan matches, not necessarily distinct people or files. Current prepared documentation no longer contains the disclosed private machine/backup values. Historical commit removal was not attempted; changing the latest file cannot remove old blobs. Sensitive exact findings are retained privately outside the repository.

## English documentation and license

README/quick start, installation, architecture, configuration, security policy, CONTRIBUTING, troubleshooting, backup/restore, dependency/attribution inventory and dated engineering documents are prepared in English. Linguistic documentation keeps its necessary Arabic examples. General paths are placeholders or checkout-relative; restoration guidance contains no private backup location.

Recommend **Apache-2.0** for the source if the owner wants an explicit contributor patent grant and can meet notice/modified-file obligations. **MIT** is simpler and retains copyright/permission notices but has no express patent grant. **BSD-3-Clause** adds source/binary notice obligations and non-endorsement, also without an express patent grant. No final LICENSE has been added. See [license options](license-options.md) and [dependency review](dependencies-and-attribution.md). Exact distributed dependency/model versions, optional components and dataset rights still need clearance; a project source license would not cover them automatically.

## Gates before publication and rollback

1. Owner selects and approves the source license/copyright attribution and contribution authority.
2. Owner decides the public disposition of history, identity/operational disclosures and protected actual-data modules. No automatic rewrite/force push is authorized.
3. Establish data consent/provenance and exact dependency/model/artifact rights, including applicable notices and optional copyleft components.
4. Retain the explicit public test strategy: synthetic checks run in a code-only checkout; 23 historical artifact checks report absence as SKIP and need authorized private copies for full historical verification. Do not call those skipped checks passed.
5. Follow and verify ingest configuration migration before any later deployment. Review the local-process and HMAC replay limits for the intended threat model.

Rollback of this undeployed work is to keep using the unchanged main/production checkout or revert the development commit. Do not discard private corpus/evidence or rewrite history. If a later deployment is approved, preserve its database/runtime snapshot and revert code/config together under that deployment's own procedure. No production rollback is needed for this task because nothing was deployed.

## Expanded request: installation and developer handover

Authoritative PROJECT_STATUS separates model-training, platform-board and Corpus design tracks; reconciles v008/v009 and later REJECT/freeze evidence; and records every OA/PRQ approval gate. English beginner shell, requirements, developer setup, component map, migration, dataset/training, API (101 implemented route branches) and maintainer guides are included. README links status and a verified synthetic UI preview. CHANGELOG/conduct/issue/PR templates and a lightweight CI workflow are prepared. No repository metadata, license, release or public conversion was performed.

Eight new setup regressions failed before implementation, then passed: read-only verification, repeated no-overwrite setup, example config, incomplete environment rejection, unsupported interpreter, no-demo default/explicit opt-in, injected permission failure and actual PowerShell venv/exit propagation. Core setup uses no external packages/downloads; optional ensurepip plus requirements-dev installation was separately exercised in the disposable Windows venv.

The final independent review found a wrong Ingest documentation field and wrong body-limit status; both were corrected and the Ingest example/idempotency was exercised successfully against a synthetic WSL instance. No additional setup/launcher/collector safety blocker was identified. Deferred inherited minor: CSP prevents widths from inline chart HTML; labels remain readable. Startup initializes state before detecting a port conflict; this inherited order remains documented and tests use disposable databases.

Security review scope also inspected resolved static/dataset paths and route identifiers, parameterized SQL/dynamic-table allowlists, argv-based subprocess boundaries and absence of multipart upload endpoints. No exploitable SQL/path/command injection was demonstrated in that review; this is not a claim of exhaustive formal proof. Runtime/model paths and code execution are trusted-local-operator capabilities. Exact optional-runtime dependency vulnerabilities are NOT_VERIFIED without the full pinned environment; no clean dependency-vulnerability bill is claimed. Logs can contain local paths/tracebacks and must remain private.

[Installation verification](installation-verification.md), [maintainer handover](maintainer-handover.md) and [documentation index](documentation-index.md) contain reproduction and limits. Source rollback is an ordinary revert or continued unchanged main; state rollback needs an independently verified private restore. Setup/launch changes are undeployed.

## Remote review artifact and CI proof

[Draft PR #1](https://github.com/abinadwan/NajdiLab/pull/1) contains the private development branch. Ordinary push/real clone/fsck/setup/source-only tests and actual cloned launcher health/shutdown passed. Main remains `85c39ac3f4e15db916d46db22e05095cca10a286`; visibility remains Private. No merge/Release/license/metadata/production rollout was performed.

[Hosted CI run](https://github.com/abinadwan/NajdiLab/actions/runs/40451855276): Windows 278 passed / 23 historical skips / 68 subtests; Ubuntu 277 passed / 24 skips / 68 subtests, including the one Windows-only test skipped on Linux. One pre-existing warning remains. Initial CI failures (Windows 8.3 temp aliases; newer Python chmod keyword forwarding through the fault-injection fixture) were diagnosed and corrected without production changes, then both jobs passed. These hosted checks add source-level Linux evidence; they do not certify bare-metal installations or ML workloads.
