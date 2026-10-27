# Public core release scope and prioritized implementation backlog

Date: 2026-10-27. **Proposed for owner review; no feature migration is authorized or implemented by this document.** Based on PR #2 `d5e8c2d` and stacked PR #3 `555647f`; exact comparisons and evidence are in [feature parity](public-core-feature-parity.md). This “Phase 4” is the public-core scope review, not historical training Phase 4 or a software version number.

## Recommended minimum viable public release

Position the first release as **NajdiLab public core: local conversation review and dataset preparation**. Do not assign a release version until the owner chooses it. Deliver a source-only, single trusted operator tool that installs without ML frameworks and completes this journey:

1. Start an empty isolated checkout, optionally seed independently fictional Arabic examples with explicit consent to modify a disposable instance.
2. Collect an authorized completed turn through authenticated native Ingest, or create it through documented core APIs. Inspect the user prompt, context and immutable original response in the browser.
3. Approve, correct, exclude or restore a review through explicit controls. Inspect the saved correction, reviewer assertion, eligibility and privacy/evaluation flags. Preserve original text across saves/restarts.
4. Inspect pending/reviewed/eligible records and readiness failures. Keep demo inclusion explicit and off by default for ordinary dataset preparation; never infer consent from eligibility.
5. Prepare a new local version only after existing integrity/privacy/dedup/split gates pass. Inspect files, hashes, counts, quality, balance and holdout findings. Export/download only the selected local artifacts with containment protections and a private-data warning.
6. Back up SQLite and exports; restore into a different disposable location and verify integrity/FKs and originals/overlays. Understand that backup does not capture external runtimes or all research assets.

This minimum improves the candidate's usefulness without requiring model acquisition, a GPU, Hermes/Ollama, a production directory, proposed SQL or historical research. Documented API ingestion is sufficient initially; a bulk importer/manual SFT editor is not a release prerequisite. Preparation creates a derived local dataset; it is not a published/frozen research Gold certification or training authorization. Current two-row demo cannot satisfy existing split gates; provide a separately explicit sufficient synthetic walkthrough rather than weakening gates.

## Included, deferred and private scope

| Capability | First release requirement | Current status / boundary |
|---|---|---|
| Standard-library Python, SQLite, install/reinstall/start/stop | Include | IMPLEMENTED foundation; keep Python 3.11+/SQLite 3.24+ floor and explicit tested versions |
| Loopback Host/Origin/CSRF/framing/ingest credentials | Include with tests and clear trust model | IMPLEMENTED core; local single-operator only, replay/legacy limitations disclosed |
| Native conversation ingest and read APIs | Include | IMPLEMENTED; document exact supported contract and filter differences |
| Contextual review, correction, approve/exclude/restore, saved readback | Include | PARTIAL: existing APIs, minimal UI; B02 closes gaps |
| Explicit eligibility/privacy/evaluation/demo controls | Include | PARTIAL / release-blocking UI gap: current save omits flags/staleness token; no automated PII/consent guarantee; demo inclusion must be explicit |
| Version prepare/list/detail, readiness, quality/balance/holdout inspection | Include | PARTIAL; B03 adds safe read surfaces, no freeze/derive mutation needed |
| Selected artifact handoff and isolated backup/restore | Include | PARTIAL; CLI backup exists, safe version download/manifest readback missing |
| Candidate-specific guides, UI screenshot, architecture and notices | Include after rights review | MISSING compared with original gallery; no original-UI parity claim |
| Manual SFT/direct/preference CRUD, bulk review, rich analytics/themes | Defer to subsequent core iteration | Reusable generic logic; not minimum end-to-end requirement |
| Derive, overlap remediation, freeze and canonical registry/events | Defer; schema/state review gate | Existing library logic and proposed SQL are different readiness levels |
| Generic model metadata/config and offline step planning | Defer to non-executing optional preparation iteration | Reusable algorithm concepts, excluded mixed source must be isolated first |
| Generic evaluation identity validation and human comparison | Defer to evidence-only optional iteration | Guard library partly present; no generic comparison UI/schema today |
| Runtime registration/probing, staging, zero-step runtime Dry Run | Exclude from first release | New optional adapter security/rights/environment review required |
| Downloads, workers, Smoke/Full/resume, merge/GGUF/deployment | Exclude from first release | BLOCKED until separate engineering and execution approvals; never enabled by a UI preview |
| Corpus v1.1 generation, proposed 005–007 schemas, multi-user RBAC | Exclude from first release | PLANNED/BLOCKED; no schema migration in this scope |
| Historical review/evaluation/phase-specific modules and records | PRIVATE_ONLY permanently in default source profile | Preserve original bytes, provenance, human decisions and rejection evidence |

A reviewer must assess the **built manifest and actual candidate UI**, not the original root README/gallery, before accepting scope. First release must state the reduced API explicitly; do not call it a drop-in replacement for the private application.

## What remains private and why

| Material | Reason / retained boundary |
|---|---|
| Original conversations, historical corrections and reviewer/evaluation annotations | Personal/research content; consent, privacy and copyright evidence incomplete. Do not paraphrase them into synthetic fixtures |
| Frozen v008/v009, holdout evidence and historical evaluation records | Research reproducibility/immutability and leakage constraints; source licensing would not grant data rights |
| phase3/35/36/37/38/39/39a/310 modules and fixed curation/evaluator utilities | Historical state loading, embedded records and fixed operational workflow; preserve in private repository, no transitive public imports |
| Original training/runtime/platform-state implementations as presently coupled | Mixed reusable logic with model/environment/report assumptions and potential subprocess side effects; extraction requires review, not wholesale publication |
| Model weights/tokenizers/templates, adapters, checkpoints, merged/quantized outputs | Exact model/component rights and provenance NOT_VERIFIED; possession/training success is not redistribution permission |
| Operational databases, logs, exports, backup destinations and credentials | Runtime/private state, not public source. Locally generated datasets remain private by default too |
| Sensitive audit evidence and historical Git metadata/blobs | Current file sanitation cannot remove historical disclosures; preserve privately with restricted access |
| Unapproved visual assets/borrowed source | Ownership/license evidence unresolved; existence in a private repository is not a distribution grant |

See [distribution policy](dataset-model-distribution-policy.md), [privacy/history](privacy-history-review.md), [provenance](source-provenance.md), [third-party matrix](dependency-licensing-matrix.md) and [asset register](asset-provenance.md). Generic Arabic linguistic vocabularies are not private solely because they are Arabic. Each selected file still needs rights review.

## Prioritized implementation plan

**Goal:** complete a useful isolated review-to-dataset workflow without private research imports or model execution.

**Architecture:** retain separate candidate server/UI and reviewed reusable service modules. Extend only explicitly selected public-source files; keep all original implementations unchanged. No plugin auto-discovery or production-root probing. Use existing schemas and existing review/export gates; missing training/research remains structured unavailable.

**Tech stack:** Python standard library, SQLite, framework-free HTML/CSS/JavaScript; pytest for development only. No new runtime dependency, external font/icon library, model runtime or schema change is proposed for the minimum scope.

**Spec:** [feature parity and API/UI matrices](public-core-feature-parity.md), [boundary contract](public-private-boundary.md), and first-release requirements above.

**Global constraints:** preserve all originals, private datasets and historical records; no protected-source edits, blocked migrations, training, runtime/production access, visibility/history/license changes or publication. Existing main and both Draft PRs stay intact. A later implementation starts from a reviewed current base and receives its own authorization.

**Review focus:** untrusted Arabic/HTML text must display safely without changing originals; repeated/stale correction saves must not silently discard overlays; demo/privacy/evaluation eligibility must be explicit; traversal/symlinked artifacts must not escape candidate roots; absent runtime/evidence must never become ready or authorized. Tasks below assign tests for each.

| ID / priority | Deliverable and dependencies | Required acceptance proof | Rollback / owner gate |
|---|---|---|---|
| B01 / P0 | Approve reduced product/API scope and compatibility boundary; before all migrations | Owner accepts included/deferred table, 404/503/501 distinctions, no public-network/training promise | No source change to roll back; approval records scope only, not publication |
| B02 / P0 | Contextual review/decision UI, saved review inspection and explicit flags; after B01 | Arabic prompt/context/original visible; approve/correct/exclude/restore and saved readback/restart; safe DOM; original hashes stable; demo/eligibility/privacy choices visible | Revert candidate UI/server/pins as one reviewed unit; preserve local DB/overlays; no original file edits |
| B03 / P0 | Readiness/version/quality inspector and read-only missing core routes; after B02 | Empty/error/blocked states actionable; dedup/holdout findings, manifest/hash/counts visible; tiny demo blocks and sufficient independent fixture passes | Revert new routes/UI/pins; retain generated local versions privately; no freeze/derive mutation |
| B04 / P0 | Explicit artifact handoff and backup/restore walkthrough; after B03 | Selected version/file only, hash match, no traversal/encoded/symlink escapes; no raw arbitrary path; isolated restore integrity/FKs/original/correction proof | Disable/revert new download handler; keep exports/backups; never restore over live evidence |
| B05 / P0 | Candidate-specific docs, diagram, screenshot, adequate opt-in synthetic walkthrough and reviewed distribution map; after B02–B04 | Actual candidate UI captured with fictional data; local links/assets; documented exact routes/install; deterministic builds and explicit exclusions for new docs | Revert new assets/docs/pins; keep original gallery intact; asset rights remain owner gate |
| B06 / P0 | Scope acceptance/security/CI matrix and release manifest review; after B02–B05 | Exact candidate Windows/Linux tests, imports/unknown-source rejection, security/RTL/readiness/backup, no hidden extensions, no private fixture dependency | Forward revert failed feature unit, not integrity checks; no release if any required test fails |
| B07 / P0 release gate | Ownership/license/notices, exact selected-file provenance and approved clean-snapshot strategy; parallel B02–B06 | Exact manifest reviewed for privacy/rights; holder/contributors and Apache decision confirmed; required notices; separately approved publication destination | Keep repository/candidate private; no destructive history action; scope approval is insufficient |
| B08 / P1 | Manual SFT/direct/preference management, bulk and analytics/theme enhancements; after MVP | Synthetic provenance/version history, bulk mixed IDs, archived/ignored/eval-only exclusion, escaping and confirmations | Revert new candidate surfaces; preserve source DB records; no migrations by implication |
| B09 / P1 | Read-only leakage/selection detail, then separately reviewed derive/overlap/freeze workflow | Parent/frozen hash stability, stale fingerprint/token denial, duplicate versions, partial write/concurrency and recovery tests | Disable mutations, retain lineage/evidence; do not delete versions or activate proposed registry SQL |
| B10 / P2 | Generic metadata registry/config/step-plan and offline preflight; after B03/B06 plus separate design review | Arbitrary fictional model/revision metadata, no downloads/probes, invalid config deny, unknown evidence not READY; no fixed runtime defaults | Revert new generic modules/map; keep metadata private; no original training module import |
| B11 / P2 | Generic evaluation evidence and human decision schema/UI; after B10 and schema approval if needed | Synthetic comparison only, explicit identities, no fallback, blinded mapping stability, stale evidence and final-decision tests | Disable new generic routes; preserve decisions/evidence; never migrate historical cases implicitly |
| B12 / P3 BLOCKED | Optional runtime adapters, real Dry Run/Smoke/Full/recovery and model operations | New threat/rights review, explicit runtime registration, mocks first, preserved distinct execution authorizations, private authorized evidence | Remain unavailable absent separate owner engineering and operation approvals; no runtime operation in this plan |

### Next implementation phase: B02–B06, public core workflow completion

After B01 approval, implement candidate-only review and read-only dataset inspection first. Do not port training screens or rewrite original server imports. Each task below ends with a focused reviewable commit; changed selected files require reviewed SHA256 pin updates, and new source paths require explicit include/exclude policy entries. Never automatically accept every new file.

#### B02: contextual review with explicit decisions

Files: modify `public_source/static/index.html`, `app.js`, `style.css` and, only for supported core routing, `public_source/server.py`; add candidate-only browser/contract tests under `public_source/tests/`; update `public_source/policy.json` after review. Original `app/service.py` remains unchanged.

Interfaces: consume existing GET conversation detail/review-queue/reviewed and POST review action contracts. Produce a candidate UI that displays existing context/original/correction and sends explicit decisions/flags. No invented legacy API compatibility.

- [ ] Write failing contract/browser cases for question/context display, saved overlay readback, approve/exclude/restore, explicit demo/privacy/evaluation eligibility and unchanged originals after repeat save/restart. Include Arabic plus HTML-like input, empty corrections and stale/current overlay behavior. Set sensitive/personal/evaluation/exclusion flags before editing and assert no silent clearing; send `expected_updated_at` and assert stale saves fail with no writes. Restored records require re-review before eligibility.
- [ ] Run the new focused cases in an exact candidate and retain RED evidence.
- [ ] Implement the UI using safe DOM values and current supported service contracts; show original and correction separately, prefill saved corrections, provide actionable API errors. If stale-update protection requires original protected code changes, stop that individual change and document the patch/approval requirement.
- [ ] Run focused tests plus exact-candidate regression/security; review pins and commit the isolated unit.

#### B03: inspect eligibility, readiness and version diagnostics

Files: candidate server/UI/test files as above; no changes to original dataset modules or schemas. Proposed new read-only routes mirror original GET `/api/v1/exports/dedup-report`, version detail, `/eval-sets` and `/release-validation` only after their response/path exposure review. Existing readiness/health/quality/balance routes remain the baseline.

Interfaces: consume `service.dedup_report(db_path=DB_PATH, include_demo=False) -> dict`, `dataset_platform.dataset_version_detail(version: str) -> dict`, `eval_leakage(version: str) -> dict`, and `dataset_quality.validate_candidate_release(directory: Path, *, source_version=None, config=None) -> dict`. Resolve the last function's directory from a validated candidate-local version, never an HTTP-supplied arbitrary path. Normalize safe errors at the candidate boundary. Results are diagnostics, never training/publication authorizations.

- [ ] Write failing tests for empty versions, tiny demo split failure, privacy/eval-only/ignored/stale blocks, duplicate/unknown version and tampered diagnostics; assert no writes from new GET routes and no private imports.
- [ ] Run RED cases; implement read-only dispatch/inspector with bounded public-safe errors, contextual findings, paths/excerpts treated as private operator data and explicit demo choice.
- [ ] Provide independently fictional sufficient records through a separately confirmed disposable setup; prove existing split/conversation/holdout gates are unchanged. Do not silently expand the current seed on startup.
- [ ] Verify safe rendering/RTL, version manifests/hashes, core regression and policy closure, then commit. If a necessary invariant cannot be proven with existing protected logic, document it as blocked rather than bypass it.

#### B04: constrained artifact handoff

Files: candidate server/UI/tests, candidate README and approved backup guide; do not change original backup or export code without separate approval. Proposed interface: GET `/api/v1/dataset-versions/{version}/files/{filename}`, with an explicit manifest-approved basename and containment under the resolved version root; no arbitrary path parameter or directory archive upload.

- [ ] Write failing tests for manifest/hash readback, unknown file, dot/encoded traversal, symlink escape, cross-origin/Host rejection and no access to DB/settings/backups outside selected files.
- [ ] Run RED tests; implement bounded selected-file delivery and private-data warning. No auto-upload, public share or training action.
- [ ] Run an offline synthetic backup/restore rehearsal in another directory; compare counts, originals/overlays, SQLite integrity/FKs and version hashes. Document backup limitations.
- [ ] Re-run exact-candidate/security checks, review policy and commit. A blocker here leaves artifact handoff unavailable; it does not authorize broad filesystem serving.

#### B05–B06: accurate package and release acceptance evidence

Files: candidate README, new candidate-specific docs/media, candidate tests/workflow and reviewed policy; retain original README/gallery/diagrams as original-profile references.

- [ ] Add contract/browser failures that assert the selected profile, enabled/disabled actions, no implicit extensions, installation portability and unsupported methods/routes. Cover all first-release acceptance steps and new surfaces rather than copying original-suite counts.
- [ ] Implement missing documentation/manifest classifications and explicit demo walkthrough; capture actual new UI with independent fixtures, label artwork/screenshot provenance and scope. No AI dashboard mockups or historical records.
- [ ] Build twice from reviewed source, compare manifests, verify pristine output, install and run exact candidate tests on Windows/Linux; verify all baseline hashes and zero deletions. Treat unavailable platforms/private fixtures as SKIP/NOT_VERIFIED.
- [ ] Review final selected bytes, static dependencies, sensitive paths/credentials and notices. Commit evidence, retain failed attempts, leave all legal/publication gates open until B07 and explicit publication approval.

## Generic training and evaluation boundaries

Pure configuration validation, step calculation, quality gating, metadata records and evaluation identity contracts are reusable **ideas/logic**, not private by definition. Original `training_control.py` combines these with hardcoded compatibility branches, catalog assumptions, model discovery/acquisition and runtime/output defaults. `runtime_control.py` adds subprocess, staging, workers and approvals. Extract new generic modules in candidate space with explicit caller-supplied evidence, no default historical model/runtime and no import of those original modules. Confirm provenance/rights for any copied implementation and record changes.

Keep offline plan status separate from original zero-optimizer Dry Run, which can involve real staging/runtime work. A config form, registered model, estimated VRAM or READY dataset is never execution approval. Missing model/runtime/template/evidence returns UNKNOWN/BLOCKED, not a guessed compatibility PASS. Smoke, Full, recovery and deployment retain separate authorization requirements in any later adapter. Evaluation's supplied-evidence guard must not be marketed as independent proof that an adapter was loaded or a replacement for human review.

## Owner approval gates and release decision

| Gate | Current status | Required decision / evidence |
|---|---|---|
| Reduced first-release product scope | AWAITING_APPROVAL | Approve B01 and B02–B06 next phase; no request to migrate protected code |
| Useful core UI/API completion | PARTIAL | Complete P0 acceptance; full original parity explicitly deferred |
| Protected original integration | BLOCKED | Separate exact-patch and private parity approval if later required |
| Historical Git privacy | BLOCKED | Choose/approve separately reviewed clean source snapshot; do not make current history public |
| Source/asset ownership and exact third-party rights | NOT_VERIFIED | Confirm authority, selected-file provenance and matching notices; exclude uncleared optional components |
| Source license and attribution | AWAITING_APPROVAL | Apache-2.0 remains recommendation; holder/year/scope and original-repository notice require approval, no active root LICENSE |
| Private datasets/models/evaluations | PRIVATE_ONLY / rights NOT_VERIFIED | Keep excluded; separate consent/provenance/model permissions for any future distribution |
| Production authentication transition | BLOCKED | Separate operational review/approval; candidate work does not deploy it |
| Publication | BLOCKED | All mandatory gates plus explicit exact-manifest/destination/publication approval |

Recommended original attribution remains **NajdiLab — original source https://github.com/abinadwan/NajdiLab**, subject to ownership/license approval. Required copyright/license/NOTICE preservation differs from voluntary visible README/About credit; no universal mandatory homepage backlink is asserted. See [license proposals](proposals/licensing-approval.md).

**Verdict: NOT READY — BLOCKERS REMAIN.** The smallest safe next decision is approval of the reduced scope and candidate-only B02–B06 implementation. B07 rights/history work proceeds independently. This phase creates no new feature, model/runtime access, license grant, publication, merge or existing-PR change.

Rollback for this analysis is a normal forward revert of its documentation commit, leaving source/candidate pins, both Draft PR heads, original records and assets intact. Future feature rollback must preserve any new user-created local records, and must never reset shared history, erase failed evidence or overwrite a live database.

## Phase5 accepted engineering scope

Owner-authorized B02–B06 are complete for local Core: review/correction/explicit flags/conflict handling, contextual privacy/eligibility/dedup/holdout, conversational SFT preparation, version/manifests/quality/balance inspection, selected verified JSONL retrieval, private coherent backup/separate restore and candidate-specific guides/visuals. Exact Windows/Ubuntu candidate73tests/68subtests plus builder11/18 and real browser PASS. The initial proposal/backlog above remains historical decision evidence. [Milestones/commits/rollback](public-core-phase5-execution.md) and [verification](public-core-phase5-verification.md) are authoritative.

B07 rights package is complete as a decision aid, not cleared for publication. B08 manual/direct/preference workflow, generic model configuration/offline plans/evaluation, full event audit/migration improvements and broader trust models remain deferred B08–B12. Actual training/acquisition/export/deployment and private research never enter the first release automatically. Owner's next review is exact rights/holder/year/notices/history/snapshot disposition, not an automatic migration or training approval. Publication remains blocked.
