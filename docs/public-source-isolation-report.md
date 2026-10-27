# Source-only candidate engineering report

Verdict: **NOT READY — BLOCKERS REMAIN** for publication. This report distinguishes engineering operation from rights clearance. The [boundary specification](public-private-boundary.md) is authoritative for this profile; [prior release decision](public-release-decision.md), [history review](privacy-history-review.md), [provenance](source-provenance.md) and [asset/data rights](dataset-model-distribution-policy.md) remain applicable.

## Baseline and preservation

Branch `dev/public-source-isolation` is stacked on PR #2 head `d5e8c2d60a84822e4587a7fd47688ed65f29e491`. PR #2 was open/draft; no edits, merge, closure or supersession of that PR are authorized or performed. Main remains `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. File SHA256 inventory is retained privately outside Git before implementation. Existing research, source, schema/config, screenshots, diagrams, ADRs and historical documents are preserved. No original application/test/script file is changed; additions live under public_source plus new CI and documentation updates.

## Engineering outcomes

The builder creates a separate source-only directory from a hash-pinned explicit file mapping; exclusions classify every other source path. It omits Git, historical modules, operational files, credentials, databases, backups, weights/adapters/checkpoints, runtime/model implementations and sensitive audit evidence. It stages a new HTTP entry point, explicit unavailable-extension boundary, minimal core UI, independent synthetic library-card fixtures and candidate contract tests. Original research/training implementations remain unchanged and are not candidate dependencies.

This deliberately narrower core profile is not a full replacement for the original application's research UI/API. It supports local ingestion/review/correction/eligibility, dataset preparation and health/quality diagnostics, plus backup. Historical/training routes fail clearly with 503; unimplemented core routes return 404. No training authorization is weakened: execution is absent rather than implicitly permitted. No production discovery/plugin auto-loading occurs. Any integration patch to the original protected server is documented and **BLOCKED / OWNER_APPROVAL_REQUIRED** individually; isolated work continues without it.

The two-row opt-in demo is intentionally small. The exact-candidate contract separately creates enough independently fictional numbered card conversations to satisfy existing train/evaluation split constraints. It does not bypass the minimum size, conversation separation, eligibility or review-integrity rules to obtain a passing export.

## Reproduction

From the engineering source checkout, Python 3.11+/SQLite 3.24+:

```text
python public_source/build.py --output <separate-new-directory>
python public_source/build.py --verify <separate-pristine-directory>
python -m pytest -q public_source/tests/test_builder.py
```

Use an actual new output path outside the repository, not the literal placeholder. From the built candidate: `python scripts/install.py`, optional **before first launch** `python scripts/synthetic_demo.py --confirm-disposable`, then `python scripts/launch.py` (or its local venv). Open the candidate loopback URL. No model/runtime installation is required. Read its self-contained README for supported endpoints, test commands and limits.

Full exact-candidate tests: install only requirements-dev.txt in a disposable environment, then `python -m pytest -q tests -rs` **with the built candidate as working directory**. Do not mistake the original repository's tests for this result. Preserve a pristine build for hash verification; generated runtime files intentionally invalidate pristine verification. There is no archive upload/publish command.

## Verification results

Local results (fresh execution):

| Verification | Result | Evidence / limitations |
|---|---|---|
| Exact built candidate, `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs` from candidate root | **22 passed, 13 subtests, zero skips**, 1.49 seconds | Includes independent install/start/stop, synthetic Arabic, overlay/original, export/quality/health, auth/CSRF/Host/Origin/framing/path tests and backup/restore |
| Engineering builder tests, `python -m pytest -q public_source/tests/test_builder.py` | **7 passed, 7 subtests**, zero skips | Two builds have identical manifest bytes; tamper/extra/unclassified/hash/import/dynamic-import/artifact cases reject; simulated CRLF input produces identical LF candidate manifests |
| Preserved original suite, same pytest command from original repository | **277 passed, 24 skipped, 68 subtests**, one existing return-value warning, 5.74 seconds | 23 absent private-artifact checks and one Windows-only skip; historical results not recreated |
| `python scripts/check_docs.py` | **91 Markdown files PASS** | Internal links and existing API inventory unchanged |
| Hash/no-loss comparison | **250 baseline paths retained; all 136 protected source/config/test/schema/plan hashes unchanged** | Private originals outside this environment NOT_VERIFIED; no deletions |
| Real candidate browser | **PASS** | Chromium loaded exact new UI, showed two independently fictional turns, saved correction without page errors; DB original/correction verified; disposable process stopped |
| Static manifest/import/privacy scans | **PASS for reviewed pinned set** | No private/phase/training/runtime/platform-state imports; no Git/binaries/databases/secrets packaged. Not exhaustive legal/privacy proof |
| Windows/native platform operation | **NOT_VERIFIED locally; hosted CI below** | Local host Linux container; no production Windows/WSL/NajdiTrain access |

Generated candidates and private logs remain outside tracked source. No candidate package is uploaded. Hosted CI is linked in the implementation Draft PR after the branch is pushed. Environment: Linux container, Python 3.12.14, SQLite 3.53.1; pytest 9.1.1 separately installed. Windows/Linux CI is configured for both the builder and exact candidate, without artifact upload. Original historical-artifact tests remain separate and may skip; synthetic candidate success does not reproduce historical results.

Tests exercise repeated install/no DB, default demo refusal, explicit synthetic setup, refusal to overwrite an existing DB, startup/health/static UI, native auth/Host/Origin/CSRF/JSON/path boundaries, unavailable private/model routes, correction persistence and original preservation, eligibility, version split/export/health/quality, consistent backup/CRC/restore/integrity/FKs, shutdown, isolated imports and builder determinism/tamper/unknown-source/import/artifact rejection. A real browser check exercises the actual new candidate UI separately.

## Failed evidence retained

- Initial builder tests failed because the builder did not exist (three expected RED failures), then passed after implementation.
- A new cross-platform newline test first failed; canonical UTF-8/LF pinning/output and LF manifest writing resolved the portability defect without editing .gitattributes or original files.
- Added adversarial tests exposed forbidden artifact/private-module paths not being independently denied; explicit hard denials were added and the cases rerun.
- First candidate test collection failed because a selected historical lifecycle test required proposed 006 SQL. That test was excluded from the candidate rather than shipping/activating blocked SQL; original test and SQL remain unchanged.
- The first end-to-end export attempt failed because the tiny synthetic demo did not meet existing split constraints. Additional independently fictional contract-only records exercise valid preparation without changing the gate.
- An original-suite attempt without sandbox socket permission failed HTTP cases (4 failed / 19 errors); this is environmental evidence, not an application pass. A rerun with socket permission is recorded separately.

Private logs retain these attempts. They contain synthetic data only and are not packaged. No failed result is relabeled as historical research success.

## Release and compatibility gates

| Gate | Status | Required action |
|---|---|---|
| Isolated import boundary | Implemented; verification below | Maintain explicit map and tests; no hidden dynamic private loader |
| Private implementation preservation | PASS: original files unchanged | Owner approval before any original protected-source compatibility edits |
| Core profile/API parity | Intentionally partial | Review additional routes separately; do not promise original research parity |
| Synthetic candidate operation | PASS locally; hosted checks separately | Keep explicit opt-in/fresh-state safeguards |
| Original private datasets/evaluations | SKIP — unavailable | Maintain private hashes; do not claim fresh original-data verification |
| Historical Git privacy | BLOCKED | Owner history decision; source candidate does not sanitize earlier commits |
| Source ownership/license | AWAITING_APPROVAL | Confirm ownership, copyright and active license scope |
| Third-party/model/data rights | NOT_VERIFIED | Exact distribution manifest/provenance/license review; models excluded |
| Publication | BLOCKED | Explicit owner approval after every applicable gate closes |

## Rollback and safe next actions

Review the stacked implementation Draft PR independently of PR #2. A normal forward revert of this branch's additions/docs is sufficient; original app/source/state is untouched. Do not force-push/reset shared branches, delete research, restore over live data, access external production directories or publish the generated candidate. Keep generated builds private. If owner later authorizes private integration, implement the separately reviewed gateway patch and private parity checks; do not infer that approval from the working core candidate.

## Independent review and final local candidate

A focused independent reviewer found an import-binding validator gap (`from app import` missing children and imported/aliased dynamic-import helpers). Four adversarial cases failed before the checker was tightened, then passed. A launch-instruction mismatch was resolved by including the unchanged run.sh/run.ps1 wrappers; Linux contract now launches via run.sh into the installed venv and Windows via its candidate venv interpreter. Review recheck reported no remaining Critical/Important findings in scope. Arbitrary Python metaprogramming is not a claimed sandbox guarantee.

Final local profile: **37 files**. Exact reviewed-candidate suite: **22 passed, 13 subtests, zero skips**, 1.49 seconds. Final builder suite: **7 passed, 7 subtests, zero skips**. Original suite remains 277 passed / 24 skips / 68 subtests with its existing warning. Earlier 35-file profiles and intermediate builder counts are retained as development evidence, not final delivery counts. Pristine verification rejects generated caches after use as designed; keep a fresh build for manifest proof. Core dataset diagnostics may include candidate-local paths; do not share live outputs without review.

## Hosted verification and stacked delivery

[Draft PR #3](https://github.com/abinadwan/NajdiLab/pull/3) targets `dev/open-source-final-readiness`, preserving PR #2 at `d5e8c2d` and unchanged main. Implementation head `8763b6e536915b1407890135f5477adf42335fd8` passed all four hosted jobs:

- [Source-only candidate run 40479629375](https://github.com/abinadwan/NajdiLab/actions/runs/40479629375): Windows builder **7 passed / 7 subtests**, exact candidate **22 passed / 13 subtests**, zero skips; Ubuntu same counts, zero skips. Both built and verified the manifest before executing the candidate in its own directory. No artifact upload.
- [Preserved-source run 40479629227](https://github.com/abinadwan/NajdiLab/actions/runs/40479629227): Ubuntu **277 passed / 24 skipped / 68 subtests**; Windows **278 passed / 23 skipped / 68 subtests**, each with the existing warning. These are original-source regression checks, distinct from the candidate suite.

Subsequent evidence-only document updates do not alter candidate-selected bytes or manifest. Exact-head check status remains visible in PR checks. Repository remains Private; no generated package is published, no PR is merged, no license activated. Owner rights/history decisions and original-protected-source compatibility patches remain blocked as documented.
