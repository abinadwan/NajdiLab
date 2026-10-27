# NajdiLab project status

Current publication decision: **NOT READY — BLOCKERS REMAIN**; see [public-release-decision](docs/public-release-decision.md) and [fresh verification](docs/unified-readiness-verification.md). Unified preparation branch: `dev/open-source-final-readiness`, based on remote main `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. PR #1 was already merged and its former branch deleted before this work; that is a governance/process finding, with no inference about authorization. The prior local `5ac0f2b` decision package was inspected and incorporated on the new branch. Earlier original-main/unmerged-PR statements below are historical. No production reconciliation or deployment is implied.

Last reconciliation: **2026-10-27**. This is the authoritative development handover, not operational approval. Stable source baseline: main at `85c39ac3f4e15db916d46db22e05095cca10a286`. Preparation branch: dev/english-open-source-readiness. Publication: **NOT READY — BLOCKERS REMAIN**. Production has not received this branch.

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

- AWAITING_APPROVAL: source license/copyright-holder identity; Apache-2.0 recommended, no final LICENSE.
- BLOCKED: disposition of personal paths/backup/author metadata in history and real curation/evaluator source. Latest-commit cleanup cannot sanitize history.
- NOT_VERIFIED: exact dependency/transitive, asset, model and data redistribution rights; [review](docs/dependencies-and-attribution.md).
- BLOCKED for deployment: Ingest secret transition and operational approval; production unchanged.
- NOT_VERIFIED in source-only installs: historical artifact checks explicitly skip if required files absent; maintainers with authorized private copies must run the full suite.
- Debt: non-atomic unguarded migration loader; no multi-user RBAC; HMAC has no replay freshness; incomplete legacy utility certification; adapter drift; mobile/native Linux breadth.

## Resume safely

Next task: owner review this branch and license/history/data disposition plus security migration plan. Do not start Corpus Phase 1A or training automatically. Follow [maintainer handover](docs/maintainer-handover.md): clone reviewed revision, install locally, test, identify exact blocked gates, make a scoped branch and update status/worklog. Proposed SQL stays outside migrations. Roll back by ordinary revert plus verified private restore; never restore over live state.
