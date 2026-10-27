# NajdiLab public release decision

Date: **2026-10-27**. Verdict: **NOT READY — BLOCKERS REMAIN**.

## 1. Executive summary and baseline

This combined review is on `dev/open-source-final-readiness`, based on current remote main `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. GitHub reconciliation found PR #1 already merged, the former branch deleted and no open PR. The prior local package `5ac0f2b99bef445e119e4bdb7fb5289464947de9` was found, its diff reviewed and incorporated as `5d9fde8` after confirming its parent tree matched main. One new coordinated Draft PR is authorized by the unified task. The old commit remains preserved. Main and Private visibility are unchanged; no speculation about the prior merge's authorization is made.

At reconciliation the real clone was clean, `git fsck --full` succeeded, and 224 tracked files received SHA256 baselines outside the repository. No local concurrent edits existed in that clone. This says nothing about uncommitted production work; the historical live-tree reconciliation remains open. Initial snapshot retrieval through the connector was superseded by the successful full clone after sandbox network access was granted.

The application/security implementation is preserved. Research-bearing source remains private and unchanged. The safely resolved work is a concrete, evidence-backed owner decision package, more precise rights inventory, distribution boundary and inactive licensing drafts. No claim of completed private-data separation or permission to redistribute is made.

| Gate | Status | Evidence | Required action |
|---|---|---|---|
| Privacy | BLOCKED | PRIV-03/06/07/09 in [audit](privacy-history-review.md) | Clear identities, operational context and every candidate public file |
| Git history | BLOCKED | 7 reachable commits / 328 blobs; 26 personal Windows-path matches | Approve a publication strategy; keep current repo private |
| Real-data separation | BLOCKED | Protected modules imported by application; [policy](dataset-model-distribution-policy.md) | Implement isolated public interfaces/replacements; preserve private originals |
| Security | COMPLETE within tested local scope; deployment BLOCKED | Clean-clone full suite and source review; section 12 | Retain local single-operator scope; separately approve/test Ingest transition |
| Third-party rights | NOT_VERIFIED | [Dependency matrix](dependency-licensing-matrix.md) | Exact distribution manifest, provenance and matching notices |
| Source license | AWAITING_OWNER_APPROVAL | Inactive [approval package](proposals/licensing-approval.md) | Confirm ownership/holder/year/scope and select license |
| Attribution | AWAITING_APPROVAL | [NOTICE draft](proposals/NOTICE.txt) and README wording | Approve public attribution and contributor authority |
| Test coverage | COMPLETE for available source; private/Windows coverage NOT_VERIFIED | 277 passed, 24 skipped, 68 subtests; section 13 | Run absent historical checks privately and Windows checks on Windows |
| Publication | BLOCKED | Unclosed privacy/data/rights/license gates above | No public conversion, release, merge or history rewrite |

## 2. Resolved publication preparation gaps

- Independently reconciled the stale draft/main baseline and protected the requested implementation.
- Classified historical personal paths separately from harmless examples; qualified the earlier backup-match count rather than repeating it as verified fact.
- Established the public source/private research distribution policy and mapped direct import blockers to a concrete replacement plan.
- Expanded dependency inventory into purpose/version/origin/license/redistribution/commercial/compatibility/uncertainty evidence, including tagged license-text checks and optional AGPL concerns.
- Prepared complete inactive Apache-2.0 text, NOTICE/copyright fields, attribution wording and contributor guidance without activating a license.
- Reproduced available regressions from a genuine source-only clone and recorded skips accurately. Prior localization/install implementation was not repeated.

## 3. Remaining publication blockers

Public release requires rights/consent disposition of real data embedded in tracked source; a functional public replacement or approved exclusion plan; historical identity/operational disclosure disposition; source ownership and license approval; borrowed-code/static-asset provenance; and exact rights/notices for the actual shipped contents. Security test success does not close those gates.

Private original artifacts are absent from this clone. Their historical integrity and rights cannot be certified here. No frozen v008/v009 record, human review, historical evaluation, conversation, checkpoint or adapter was edited, deleted, translated, reclassified or replaced.

## 4. Historical Git privacy findings

See the [redacted audit](privacy-history-review.md) for scope, evidence classes and limitations. All 328 reachable blobs and commit metadata were enumerated. Personal Windows paths appear in 26 historical matches; author/committer identities and historical backup-location disclosure remain accessible. Three historical home-path candidates require owner review. Counts concern unique blob versions, not people. The earlier two-backup-match claim was not reproduced as two distinct disclosures: one location-bearing match was confirmed, while broad matching also caught harmless loopback text.

Current generalized path examples and synthetic fixtures are not automatically sensitive. Linguistic Arabic vocabulary and API compatibility enums remain intact. Real correction/reviewer content is classified by provenance, not language. No known token/private-key candidate matched the limited pattern scan; arbitrary secrets, unreachable objects, hosted artifacts and external clones are not exhaustively cleared. Sensitive exact evidence stays outside tracked content with restrictive permissions.

**Sanitizing the latest files does not remove information accessible through earlier commits.** `.gitignore` cannot sanitize tracked data or history.

## 5. Recommended history publication strategy

Recommend **B: a separately reviewed clean source snapshot in a new public lineage**, retaining this private repository unchanged for provenance. A snapshot must first exclude or safely replace research-bearing source and pass complete rights/privacy review. Publishing this repository with all its history is not equivalent.

[Strategy comparison](privacy-history-review.md#publication-strategy-comparison) covers A (retain specifically cleared history), B (clean snapshot) and C (reviewed rewrite), privacy exposure, attribution, clone disruption, rollback and owner approvals. A preserves lineage but retains old disclosures; C disrupts commit IDs/clones and cannot erase all external copies. No strategy was executed. Obtain specific approval for the exact public manifest, destination and attribution; a rewrite/force-push requires additional explicit approval.

## 6. Private-data separation status

**Blocked, plan prepared.** `scripts/complete_review_queue.py`, both v007 evaluator-report builders, `app/phase38_dataset.py`, historical repair material in `app/phase39_edits.py`, and the repair assertion in `tests/test_phase39_mt06_repair.py` contain protected research evidence. Analytical utilities also contain corpus-specific identifier checks. None was generalized in place. Current server/freeze/resolution imports mean deleting these files would break functionality.

The [distribution policy](dataset-model-distribution-policy.md#protected-source-separation-plan) proposes reusable public interfaces, private optional manifests/builders, structured unavailable responses and independently synthetic tests, while preserving historical checks privately. This architecture is **not yet implemented**. Do not archive current HEAD for public distribution.

## 7. Dependency licensing matrix

The authoritative [matrix](dependency-licensing-matrix.md) separates source-only references from bundled code/binaries and records matching license-text evidence. Tagged texts checked: Python 3.12.14, PyTorch v2.12.1, Transformers v5.5.0, PEFT v0.21.1, bitsandbytes 0.50.2, TRL v0.24.0 and pytest 9.1.1. They are not certifications of historical installed wheels. The attempted Unsloth `2026.9.12` license ref returned 404; its historical artifact remains NOT_VERIFIED. Current Unsloth text explicitly distinguishes Apache core paths and optional AGPLv3 Studio/CLI paths.

Accelerate, NumPy, Hugging Face client, Ollama and SQLite current texts are discovery evidence only. safetensors returned a relocation response and is not marked verified. CUDA/native bundles, Hermes origin/revision, GGUF tooling, static/copied-source provenance and complete transitive rights remain NOT_VERIFIED. No training packages or weights were downloaded. The project lacks a complete pinned ML environment and attribution bundle. Default source-only scope avoids bundling these runtimes; copied/adapted code must still be reviewed.

## 8. Dataset/model/research rights

Default: source-only plus cleared synthetic examples. Private datasets, frozen records, evaluations, training outputs, weights, adapters and merged/quantized models remain excluded. See [asset policy](dataset-model-distribution-policy.md). Model possession, training success and a source catalog license field do not establish redistribution rights.

The Gemma repository/revision is recorded in the matrix; its exact model/template/tokenizer permissions were not independently retrieved. Historical Ministral/quantized references lack complete revision/terms evidence. Private data needs consent, provenance, copyright/privacy and intended-use review, including third-party people and quoted works. No NajdiLab source license would automatically cover these assets.

## 9. Apache-2.0 recommendation and alternatives

Recommend Apache-2.0 only after ownership and component compatibility are confirmed. It permits free and commercial usage, modification and source/object redistribution under standard notice requirements, provides a limited express contributor patent grant with litigation termination, and disclaims warranties/liability subject to law. It does not compel publication of all private modifications or grant general trademark rights.

MIT offers shorter permissive terms with copyright/permission retention and no express patent grant. BSD-3-Clause adds explicit binary notice and non-endorsement conditions, also without an express patent grant. None resolves private-data rights. Full obligations, compatibility caveats and inactive drafts: [approval package](proposals/licensing-approval.md). No root LICENSE was created.

## 10. Attribution wording and legal obligations

Proposed original-project notice: **NajdiLab — original source https://github.com/abinadwan/NajdiLab**. Copyright holder/year require owner confirmation. Preserve relevant original and third-party notices; supply the license, prominently identify changed files and reproduce applicable NOTICE attribution in the locations Apache section 4 permits.

Recommended visible README/About credit is distinct from mandatory notices. Apache-2.0 does not universally require a homepage backlink in every derivative product. Stronger mandatory public advertising credit would require a separate nonstandard-terms/compatibility decision. The [inactive NOTICE](proposals/NOTICE.txt), [README wording and contributor guidance](proposals/licensing-approval.md) add no such restriction and make no present license grant.

## 11. Required owner decisions

1. Review the single combined Draft PR from current main; merged PR #1 remains historical.
2. Approve strategy B or select another history strategy; decide public attribution versus personal metadata and operational disclosures. Keep current repository private pending closure.
3. Approve exact public file scope and a separately reviewed implementation of protected-source separation; retain every original research asset privately.
4. Confirm copyright holder/year, authority over contributions and source license. Review third-party provenance and actual shipped notices before activation.
5. Establish private data/model rights evidence and a named private security-reporting/maintainer contact before public launch.
6. Approve any later controlled production Ingest credential transition separately. No deployment authorization is inferred here.

## 12. Security verification and limitations

The unchanged implementation and full available regression suite cover Host/port validation, Origin/Fetch Metadata checks, CSRF, DNS rebinding boundaries, authenticated bearer/HMAC Ingest, JSON/body framing and limits, safe rendering regression, path containment and secret-key redaction. Source inspection confirmed these checks precede routing, static paths resolve under the static root, and startup still invokes the existing migration loader.

Trust model remains **single trusted local operator on loopback**. No multi-user RBAC or shared/public hosting security is claimed. Local programs can obtain request-intent sessions. HMAC authenticates bytes without freshness/replay protection; universal idempotency is not guaranteed. Operational diagnostics/logs can disclose private paths. The migration loader remains non-atomic/unguarded and production Ingest credential transition is pending. Optional dependency vulnerabilities are NOT_VERIFIED without an exact runtime inventory. No live Hermes/Ollama change, production restart, runtime probe, schema migration or training was performed. Regression tests use disposable temporary state.

## 13. Test results and preservation evidence

Current combined-branch execution and diagram/installation details supersede earlier local delivery assumptions: [unified verification](unified-readiness-verification.md).

Environment: Linux, Python 3.12.14, SQLite 3.53.1; pytest 9.1.1 installed into an isolated tools directory. Commands run from the real source-only clone; private historical fixtures were not supplied.

| Check | Result | Evidence / limit |
|---|---|---|
| Clean-clone baseline: `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs` | PASS: **277 passed, 24 skipped, 68 subtests**, one existing warning | 23 historical-artifact skips plus one Windows-only skip; no historical proof inferred |
| Complete final available suite | PASS: **277 passed, 24 skipped, 68 subtests**, one existing warning | Same command plus private JUnit output; 4.84 seconds; no model workload |
| Security, Arabic preservation, installation regressions | PASS as included in full suite | No independent live production/browser recertification claimed |
| `python scripts/install.py --check` | PASS | Read-only Python/SQLite/source-layout smoke; no application startup or database initialization |
| `python -m compileall -q app scripts tests` | PASS | Syntax only; does not execute training |
| `sh -n run.sh scripts/install.sh` | PASS | Shell syntax; no native Windows smoke in this task |
| `python scripts/check_docs.py` | See [fresh documentation evidence](unified-readiness-verification.md) | Local links and generated API inventory |
| `git fsck --full` | PASS | Full real clone; no history mutation |
| Tracked operational-artifact filename check | PASS: zero matched | Databases/JSONL/weights/archives/caches excluded; real data in Python still blocks release |
| Current/history privacy review | COMPLETE WITH BLOCKERS | PRIV-01–09; limited secret patterns are not exhaustive clearance |
| Baseline source preservation | PASS: all **132** app/script/test/static/config/migration files unchanged | All 224 baseline files fingerprinted; only publication documentation/proposals intentionally edited |
| Original private Gold/v008/v009/reviews/checkpoints/adapters/conversations | **SKIP — unavailable** | Earlier 317-file hash result is prior reported evidence, not freshly verified here |
| Fresh Windows installation, live browser, optional ML/runtime vulnerability scan | **SKIP — not performed** | Prior dated results retained, not claimed rerun |

An initial connector-only snapshot run without socket permission failed (4 failed, 19 errors, 254 passed, 24 skipped): HTTP tests could not bind local sockets. A prior pytest attempt also failed before the runner was installed. These environmental failures are retained privately; the real-clone run with sandbox network permission passed. No source change was used to conceal them. One existing PytestReturnNotNoneWarning remains in the legacy training-plan unit test.

## 14. Unverified assumptions

Owner/employer/contributor rights; frontend/copied-source provenance; exact historical runtime artifacts and model terms; data consent; off-clone production changes; historical original hashes; deleted/unreachable Git objects and hosted logs/caches; all future public refs; platform breadth and full dependency vulnerabilities. Generalized source paths do not certify live runtime configuration. The source-only suite cannot reproduce historical training/evaluation results.

## 15. Safe rollback

This task changes publication documentation/proposals only. Keep the private original graph and protected files unchanged. Revert a remediation commit with an ordinary forward revert if needed; do not reset/force-push shared history. Main already contains the prior merge, so the old advice to use unchanged pre-readiness main is stale. Neither documentation rollback nor a clean snapshot recovers information once disclosed publicly.

No production rollback is needed because nothing was deployed. Any future state/config rollback requires a separately approved, verified private snapshot and rehearsed restore; never restore over live evidence. Private audit material must remain outside release artifacts. Do not delete original private assets as a publication shortcut.

## 16. Exact recommended next actions

1. Review this package while the repository remains private; review the combined Draft PR and its fresh verification.
2. Approve copyright/license/attribution fields and obtain the contribution/provenance declarations; proposals remain inactive until then.
3. Review the protected-source replacement plan, implement it in isolation, and prove public imports/routes/tests with synthetic Arabic fixtures while verifying private hashes separately.
4. Build an explicit allowlisted source manifest; review every included source, fixture, document and asset. Collect exact third-party notices only for components actually shipped. Keep models/runtimes/data external by default.
5. Approve strategy B and prepare a separate clean snapshot without `.git`, private audit evidence or excluded assets. Test the exact snapshot from scratch, including Arabic/security/installation checks; privately run historical checks with authorized originals.
6. Obtain a final owner publication decision after every gate closes. Only a separately authorized action may create a public repository/release or activate the license. Do not merge, rewrite history, train, migrate databases or deploy production Ingest as part of this review.

## 17. Unified README, architecture and handover acceptance

The README now opens with an evergreen introduction, idea/problem and intended users before contents/status. It includes a source-grounded architecture diagram and lifecycle diagram, technology/version table, official downloads, distinct Windows/POSIX commands, system requirements, source tree, environment variables, security limits, status/roadmap and maintainer links. No software release number was invented. SQLite's enforced floor is 3.24; current tested build is 3.53.1, with historical Windows 3.49.1 / WSL 3.45.1 distinguished.

Architecture, setup, installation, requirements, documentation index, status, changelog and maintainer handover were updated by extension rather than redundant replacement. Read-only setup and disposable POSIX install/reinstall/health/conflict/Arabic Ingest/backup/restore/shutdown were freshly exercised. Current Windows/WSL execution is unavailable; earlier results remain historical. Exact commands, diagram/link validation, warning/skip counts and CI evidence are in [unified verification](unified-readiness-verification.md). A polished README does not close private-data, history, ownership/license or redistribution gates.

No safe edit was established that could remove real historical research from imported source without affecting protected evidence or functionality. The precise public-replacement plan therefore remains BLOCKED for owner approval and separate implementation. The smallest next action is review of rights/history/copyright decisions and that isolation plan, not training or deployment.

## 18. Coordinated GitHub delivery

All combined changes are delivered through [Draft PR #2](https://github.com/abinadwan/NajdiLab/pull/2), branch `dev/open-source-final-readiness`, targeting main `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. PR #1 remains a historical merged review; no competing current PR was created. The original local `5ac0f2b` is preserved and its reviewed content incorporated. Independent remote clean-clone tests and CI evidence are in [unified verification](unified-readiness-verification.md). Main remains unchanged and the repository Private. This delivery does not activate any license or close privacy/data/rights gates.

## 19. Visual documentation and provenance continuation

New [diagram gallery](architecture-diagrams.md), [real synthetic screenshot gallery](screenshots.md), [user guide](user-guide.md), [source provenance](source-provenance.md), [third-party register](third-party-attributions.md), [asset register](asset-provenance.md) and [fresh verification](visual-documentation-verification.md) extend the same Draft PR #2. The new editable SVG distinguishes SQLite from dataset files and optional/blocked flows; the supplied conceptual illustration and existing Mermaid/images are preserved. No confirmed copied/adapted third-party application source was established, but ownership cannot be proved from available history. The owner image's underlying artwork/AI/third-party-symbol rights require confirmation. No asset license or redistribution grant is inferred.

Fresh available tests: 277 passed / 24 skipped / 68 subtests; 89 Markdown checks. Synthetic capture preserved the fictional original and correction separately, without private data or training. All 136 protected source/config/schema/test/plan files match baseline, and all baseline paths remain. Narrow SVG viewing needs zoom/scroll; unconfigured training and missing evaluation evidence remain explicit screenshot limitations. Publication verdict remains **NOT READY — BLOCKERS REMAIN**; the existing history/privacy/data/rights/source-license gates are unchanged.

## 20. Isolated source-only candidate engineering

A separate stacked branch implements a deterministic allowlisted core profile without changing historical application sources. [Boundary](public-private-boundary.md) and [candidate report](public-source-isolation-report.md) specify the reduced API/UI, explicit unavailable private interface, synthetic data, exact-candidate tests and original-source approval gate. Technical operation does not clear history privacy, ownership, source license or third-party/data/model rights. Publication remains **NOT READY — BLOCKERS REMAIN**. PR #2 remains intact.
