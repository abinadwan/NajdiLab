# NajdiLab project status

## Dataset-first feature branch status (2026-10-31)

Current scope: **local Chat → human review → quality/version → external Unsloth**. See [roadmap](docs/roadmap.md), [audit](docs/scope-audit-2026-10-31.md) and [actual verification/limits](docs/dataset-chat-results.md). Independent branch from main `d992b0a`; PR #10 closed/draft/unmerged, Issue #9 open. No merge, installed update or third-party app change performed.

Training UI/execution APIs and executable training/GGUF/benchmark workflows are retired; historical data/reads remain. Chat completion/consent/context and external handoff are implemented with synthetic checks. Draft follow-up branch `feat/chat-workspace-claude` adds Ollama Chat with per-turn admission proof, verified on the real 0.40.13 binary with a synthetic model, and labeled evidence-tiered context suggestions ([report](docs/chat-completion-results.md)). Installed-model Ollama, real LM Studio and owner acceptance are NOT TESTED. This is a review candidate, not a claim that every requested capability is complete.

The historical tracks below remain evidence only; old training/phase readiness is not the active product roadmap.

**Settings integrations branch (2026-10-31, pending review/merge):** LM Studio/Ollama read-only local discovery, session-only consent/model selection, synthetic tests and verified local revocation are implemented. Hermes remains a BLOCKED conversation source: unsafe sender-side assumptions are withdrawn and the HTTP receiver refuses before body reading. No external sender disconnect is claimed. No new schema or installed-runtime changes. [Behavior/limitations](docs/integrations.md), [verification](docs/integrations-validation.md), [post-merge Windows procedure](docs/integrations-windows-update.md). Real installed-service acceptance is not claimed; main integration requires owner approval and green CI. Historical status below remains dated evidence.

**Current repository state (2026-10-30):** `main` is the default branch; the four former development branch refs have been deleted. [PR #5](https://github.com/abinadwan/NajdiLab/pull/5) merged the four stacked development branches into private `main` as merge commit `fdebe50aaf1a20d2f2478eed8fc979cac8372347`; their branch refs were then deleted. PRs [#2](https://github.com/abinadwan/NajdiLab/pull/2), [#3](https://github.com/abinadwan/NajdiLab/pull/3) and [#4](https://github.com/abinadwan/NajdiLab/pull/4) are closed; PR #5 is merged. For installation use [`main` installation instructions](docs/installation.md), not a deleted development branch. **Publication is still NOT READY — BLOCKERS REMAIN.** Private integration did not activate a license, clear rights/history/privacy gates, train models, migrate production or deploy services. See the [publication decision](docs/public-release-decision.md) and [Phase5 verification](docs/public-core-phase5-verification.md). Earlier branch/main/PR statements below are dated historical evidence.

**Historical reconciliation — 2026-10-27 (retained as evidence):** The baseline then was main at `85c39ac3f4e15db916d46db22e05095cca10a286`, with preparation on `dev/english-open-source-readiness`; this is no longer an active branch instruction. At that time publication was **NOT READY — BLOCKERS REMAIN** and no production change was claimed. The 2026-10-30 repository state above supersedes this baseline for GitHub checkout/PR guidance, not for historical engineering or release decisions.

NajdiLab is a local Arabic/Najdi data-review, immutable dataset and controlled training/evaluation platform. The English interface preserves Arabic content and API/data compatibility. Three independent tracks use overlapping phase numbers; they must not be combined.

## Platform and model-training track

Historical completion means recorded evidence exists, not that a source-only clone contains private artifacts or reproduces an old training run.

| Stage | Status | Evidence and scope |
|---|---|---|
| Phase 1 Dataset Review and Integrity | COMPLETE (historical) | [Engineering record](docs/historical-project-status.md); overlay review, Gold gates and protected originals |
| Phase 2-A Training Control Plane | COMPLETE (historical) | Job/model/configuration controls; [training control](app/training_control.py) |
| Phase 2-B Runtime and Smoke Execution | COMPLETE (historical) | Engineering record; this does not authorize a new Smoke |
| Phase 2-C Production Training | COMPLETE (historical) | Recovered historical attempt after max_steps boundary defect; the resulting adapter was subsequently rejected |
| Phase 3 Evaluation and Human Comparison | COMPLETE (historical), decision REJECT | 24/24 historical human reviews; adapter preserved as rejected evidence |
| Phase 3.5–3.7 Failure analysis and hardening | COMPLETE (historical) | Failure clusters, separate holdout and native tool contracts; early statements that v009 did not exist describe that earlier point |
| Phase 3.8–3.10 Remediation/review/freeze | COMPLETE (historical) | v009 derived, seven edits verified, 66 supervision masks, frozen despite legacy '-draft' identifier |
| Phase 3.11 Native tool compatibility / Round 2 Dry Run | COMPLETE (historical evidence); adapter reconciliation BLOCKED | Recorded Dry Run consumed 66 records: 24 SFT + 34 multi-turn + 8 native-tool; **zero optimizer steps and no training attempt** |
| Round 2 Smoke / retraining | NOT_STARTED; AWAITING_APPROVAL | Fresh model/runtime/dataset fingerprints, live preflight and distinct Smoke/Full approvals required |
| Phase 4A Merge / GGUF / deployment | BLOCKED | Historical decision REJECT; no new model approval, merge or deployment authorized |

### Dataset versions and conflicting snapshots

| Version | Evidence-backed interpretation | Next gate |
|---|---|---|
| v008 / gold-v008-split-clean | Frozen parent. Earlier validation recorded 30 train / 24 eval and CLEAN separation. Later 2026-10-09 quality sprint: 76 analyzed assets, two conflicting-target blockers and 52 warnings. Counts cover different scopes; newer quality gate supersedes earlier readiness, not immutability. | BLOCKED for new training under that gate; preserve bytes; derive a candidate if approved |
| v009 / gold-v009-remediation-draft | Initially proposed/non-frozen; later Phase 3.10 froze it. 66 gradient-bearing records, direct-language/preference assets separate. Sprint analyzed 88 assets, zero blockers, 26 warnings, VALID release validation. | Fresh quality/model/runtime checks and separate training authorization; no retraining claimed |

Sources: [engineering record](docs/historical-project-status.md), [readiness sprint](docs/training-readiness-sprint-report.md), [next-training snapshot](docs/next-training-execution-plan.md). Old Phase 3 AWAITING APPROVAL table is superseded by its later REJECT record. Recorded WSL success does not prove deployed adapter equals repository adapter: [K2](docs/corpus-v1.1/06-adapter-drift-k2.md) remains open. No fresh runtime probe or training was run here.

## Platform engineering board track

[Master board](docs/master-execution-board.md) is a dated engineering snapshot. Phases 1.3–8 describe platform capabilities, not model-release approval.

| Work | Status | Reason |
|---|---|---|
| Registry 005 / REG-09 | BLOCKED | Owner approval, loader guard, rehearsal and restore proof required |
| Review events 006 | BLOCKED | Proposed SQL under plans; not production activation |
| Training registry 007 | BLOCKED | ON HOLD; competing registry decision OA-09 |
| Quality/dedup/reproducible validation | COMPLETE (source capabilities) | Synthetic regression tests; operational artifacts private |
| Evaluation lineage / mobile matrix | IN_PROGRESS (historical partial) | EVAL-13–15 / UX-10–11 incomplete; not advanced by localization |

## Corpus v1.1 design track

[Phase 1 closure](docs/corpus-v1.1/17-phase1-approval-package.md) is authoritative: design approved 2026-10-23, C1–C8 complete; **Phase 1A NOT AUTHORIZED**. This branch does not implement that roadmap or close its approvals.

| Work | Status | Exact prerequisite |
|---|---|---|
| Phase 1 design and ADRs | COMPLETE | Documentation approval only; linguistic lists provisional |
| Phase 1A baseline / K12 | AWAITING_APPROVAL | OA-01 reconciliation of recorded 16 live uncommitted items; this clone does not reconcile production |
| Migration loader guard | NOT_STARTED; BLOCKED | OA-05 / PRQ-MIG-01; startup still auto-applies existing migrations |
| Adapter reconciliation | BLOCKED | OA-02; differing recorded adapter hashes and unrecoverable variant |
| Security S1–S4 | IN_PROGRESS across environments | Request controls implemented/tested in this branch under separate audit authorization; deployment/Corpus acceptance not performed |
| Identity/RBAC, lifecycle and 008 | NOT_STARTED; BLOCKED | 006, 008, S6–S8 and separate approvals; CSRF is not reviewer identity |
| G2, candidate review, Gold/Silver generation, pilot, release/training | NOT_STARTED | [Roadmap](docs/corpus-v1.1/09-implementation-roadmap.md); no generated batch or training authorized |
| Native linguistic validation | BLOCKED | PRQ-LANG-01 / OA-11: at least two native reviewers and a linguistic lead |

## Preparation evidence, blockers and debt

English UI/docs, Arabic direction/data invariants, Host/Origin/CSRF/JSON controls, authenticated Ingest and escaped export-readiness rendering are implemented in this development branch. Setup/launch and handover additions are in [worklog](docs/worklogs/english-open-source-readiness.md). Exact final counts/commands: [verification](docs/verification-and-readiness-report.md), [installation matrix](docs/installation-verification.md). No production migration, training, history rewrite or backup-volume change occurred.

- TARGET APPROVED / NOT ACTIVE: owner approved Apache-2.0 only as the target for a future clean Core release (2026-10-28); copyright holder/year/authority, exact scope, contributor/third-party rights and NOTICE remain unresolved. No active LICENSE or redistribution grant.
- BLOCKED: disposition of personal paths/backup/author metadata in history and real curation/evaluator source. Latest-commit cleanup cannot sanitize history.
- NOT_VERIFIED: exact dependency/transitive, asset, model and data redistribution rights; [review](docs/dependencies-and-attribution.md).
- BLOCKED for deployment: Ingest secret transition and operational approval; production unchanged.
- NOT_VERIFIED in source-only installs: historical artifact checks explicitly skip if required files absent; maintainers with authorized private copies must run the full suite.
- Debt: non-atomic unguarded migration loader; no multi-user RBAC; HMAC has no replay freshness; incomplete legacy utility certification; adapter drift; mobile/native Linux breadth.

## Resume safely

Next task: review the integrated private `main` source and outstanding ownership/license/history/data disposition plus the security migration plan. The deleted development branches are not checkout targets. Do not start Corpus Phase 1A or training automatically. Follow [maintainer handover](docs/maintainer-handover.md): clone reviewed revision, install locally, test, identify exact blocked gates, make a scoped branch and update status/worklog. Proposed SQL stays outside migrations. Roll back by ordinary revert plus verified private restore; never restore over live state.

## Public-source isolation engineering track

Separate `dev/public-source-isolation` is stacked on the unmerged documentation PR #2. A narrower candidate profile stages a new server/UI and reuses core logic unchanged; original research/training application remains preserved. Historical/model actions are unavailable in the candidate, not newly authorized. [Specification](docs/public-private-boundary.md) and [exact-candidate report](docs/public-source-isolation-report.md) record implementation and remaining gates. No license or publication approval.

## Public core Phase 4 — analysis and scope review, 2026-10-27

Both Draft PRs remain intact: #2 at `d5e8c2d`, #3 at `555647f`; main unchanged and repository Private. The separate analysis branch `dev/public-core-release-scope` inventories 19 original navigation views, the legacy redirect, 27 backend modules and all 101 route branches. The candidate exposes 22 original method/path patterns through 20 branches: 19 implemented core contracts and 3 reduced contracts; the remaining original routes are 42 missing, 27 blocked and 10 private historical workflows. These counts describe API disposition, not UI parity or release readiness.

Proposed first release: local collection/review/correction/eligibility and dataset preparation/inspection, with safe artifact handoff and backup. Generic model configuration/offline planning/evaluation are deferred; real training/runtime/model operations remain unavailable. [Parity evidence](docs/public-core-feature-parity.md) and [scope/backlog B01–B12](docs/public-core-release-scope.md) identify dependencies, acceptance tests, rollback and approvals. No feature migration, protected-source edit or candidate-policy change is made. Fresh Linux candidate: 22 passed / 13 subtests; original: 277 passed / 24 skipped / 68 subtests, one existing warning. Windows/browser/visual results from previous tasks remain historical. Publication: **NOT READY — BLOCKERS REMAIN**.

## Public core Phase 5 — authorized candidate implementation

Dedicated branch `dev/public-core-workflow-completion` starts at scope analysis `dc5c82e`; [Draft PR #4](https://github.com/abinadwan/NajdiLab/pull/4) targets the analysis branch. PR #2/#3 and protected originals remain unchanged. Goal0 baseline commit `0a95f54`; atomic review boundary `fa2170b` fixes mandatory stale-token and field preservation in candidate code only. Contextual conversation/review UI is under acceptance; dataset/artifact/docs/cross-platform milestones follow. Current authoritative [execution](docs/public-core-phase5-execution.md), [issues](docs/public-core-phase5-issue-register.md), [verification](docs/public-core-phase5-verification.md). Engineering work grants no license or publication permission.

## Public Core Phase5 — final authorized engineering acceptance (2026-10-27)

**ENGINEERING PASS — RELEASE GATES REMAIN** for the local source-only Core; publication **NOT READY — BLOCKERS REMAIN**. This supersedes only earlier candidate implementation checkpoints, not historical training/Corpus decisions. Original full-platform source/research/runtime status remains preserved.

Completed approved B02–B06: contextual review and atomic flag/stale protection, strict dataset readiness/quality/version/holdout inspection, constrained manifest-verified JSONL retrieval, coherent private backup/new-location restore, separate actual Core documentation/screenshots/SVG and real Windows/Ubuntu acceptance. Final selected sourcee03a640,74files plus manifest, exact73tests/68subtests, builder11/18 and actual browser/harness PASS on each OS. Native legacy override is explicitly refused in candidate code; original security module/production untouched.

B07 produced exact source/asset/rights inventory and inactive owner/license/attribution decisions, not permission to publish. All31 findings are recorded:30 engineering verified closures,1 blocked legal/history group. All270 baseline paths,136 protected source hashes and12 original media hashes retained/unchanged; inaccessible private originals/frozen versions NOT_VERIFIED. PR#2/#3/main remain unchanged, repository Private, implementation Draft#4 stacked on analysisdc5c82e.

Authoritative [execution/rollback](docs/public-core-phase5-execution.md), [verification/actual CI](docs/public-core-phase5-verification.md), [finding register](docs/public-core-phase5-issue-register.md), [rights/owner package](docs/public-core-phase5-rights.md), [Core user entry point](docs/public-core-user-guide.md). Next action is owner review of rights/holder/year/notices/history/snapshot scope, not training, Corpus Phase1A, license activation or publication. Deferred manual/model/evaluation/full audit/network-hardening work remains a separately scoped B08–B12 decision.
