# Public release remediation worklog

Date: 2026-10-27. Scope: privacy/history, protected source, dependency/data/model rights and inactive license/attribution proposals. Baseline: `ae0ebb634459a8cadb742143a49f65c755f2b290`; local development branch clean before changes. GitHub already had merged PR #1 and deleted the branch; no main change by this task.

- Retrieved PR/repository metadata and the required existing audit/security/ignore/license/Arabic reports.
- Recovered a real full clone after requesting sandbox network access; initial connector-only snapshot had 223 verified text blobs and omitted its JPEG, so it was superseded, not called a clean clone.
- Fingerprinted all 224 tracked files privately; all 132 application/script/test/static/config/migration files remain byte-identical.
- Audited 7 reachable commits and 328 blobs. Independently confirmed 26 historical personal Windows-path matches; documented the qualified backup count, metadata and real-data blockers without publishing values.
- Preserved protected real-data modules; mapped import dependencies and proposed an isolated public replacement plan instead of fabricating historical fixtures.
- Retrieved tagged/current upstream license texts, recorded exact returned hashes, distinguished binary/transitive clearance and identified optional AGPL scope. No ML runtime/weight download.
- Added source-only asset policy, dependency matrix, redacted history review, release decision and inactive license/copyright/NOTICE/README/contributor drafts. Corrected stale top-level baseline statements by explicit historical supersession, preserving original reports.
- No production work, private data changes, migration deployment, training, Hermes/Ollama changes, history rewrite, main merge, publication or active license.

## Final verification

Final real-clone suite: **277 passed, 24 skipped, 68 subtests, one existing return-value warning**, exit 0 (5.06 seconds), matching the baseline. Command: `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs --junitxml=/workspace/private-audit/final-tests.xml`; output remains private. Historical artifact checks contribute 23 skips; Windows-only installation check contributes one. Private originals are unavailable; their 317 prior reported hashes are not reverified here. Skips are not passes.

Documentation check: **PASS, 81 Markdown files**, links/API inventory resolve. Read-only installation smoke, Python compile checks, shell syntax, Git object integrity and whitespace checks passed. Tracked operational-artifact filename check found zero matches. After testing, all 132 protected source/config/static/migration/test/script SHA256 values still match the baseline. No application code was changed. Initial missing-pytest/socket-restricted attempts are retained as environmental failures, not hidden or counted as passes. Full details and limitations are in [release decision](../public-release-decision.md).

## Delivery and rollback

Remote branch restoration/new draft is pending owner direction because PR #1 was already merged. Local changes remain reviewable. Rollback is an ordinary revert of the documentation commit; protected implementation/history and private originals are preserved. Do not reset main or erase research evidence.

## Unified task continuation

The subsequent unified task explicitly authorizes the new branch/push/Draft PR, superseding the earlier delivery pause. Current main remains `2015a085`; the original `5ac0f2b` was preserved and its exact diff incorporated as `5d9fde8` on `dev/open-source-final-readiness`. No open PR existed at reconciliation.

README introduction/order, technology matrix, official links, installation, source tree, architecture/workflow diagrams and current status were consolidated without changing application code. Architecture, installation, developer/maintainer setup, requirements, index and changelog were extended; prior dated reports were retained with supersession notes. Reason: stale deleted-branch instructions and an introductory legal warning obstructed developer onboarding. Expected behavior/data/security remain unchanged.

Fresh suite: 277 passed / 24 skipped / 68 subtests, existing warning. New isolated POSIX setup/reinstall/health/conflict/authenticated synthetic Arabic/backup-restore/shutdown passed. All 132 protected source hashes unchanged. 82 Markdown files, 18 contents anchors and 19 external HTTPS links passed. Both Mermaid 12.2.0 diagrams parsed/rendered and were visually inspected on desktop; mobile/GitHub rendering is not independently certified. Exact commands, failures/retries and platform limits: [unified verification](../unified-readiness-verification.md). Private originals, current Windows/WSL and optional ML execution remain unavailable/not performed.

Publication verdict remains NOT READY — BLOCKERS REMAIN. History/public snapshot, protected research separation, ownership/license and exact artifact/provenance decisions still need owner approval. Rollback is an ordinary revert of documentation commits; no source/data/runtime rollback is required. No history rewrite, main change, production work or license activation.

Remote delivery: one [Draft PR #2](https://github.com/abinadwan/NajdiLab/pull/2), targeting unchanged main. Independent remote clean clone of `f91007b` passed 82-doc checks and 277 tests / 24 skips / 68 subtests. CI evidence is linked in the unified report. No sensitive audit evidence or new binary was staged; all changes are documentation/proposals.

## Visual documentation and provenance continuation — 2026-10-27

Baseline: clean `15c7517`, current main `2015a085`, same draft PR #2 and Private visibility; 232 tracked paths fingerprinted, 85 tracked Markdown files, existing favicon/preview preserved. No concurrent changes. Reason: add a maintainable visual entry point and evidence-based origin/rights review without losing current documentation.

Design: original editable SVG with seven layers, solid/optional/blocked connection legend and separate SQLite/filesystem stores. Kept the supplied conceptual JPEG unchanged; documented registry, runtime-input and evaluation shortcuts. Added diagram gallery, seven real-browser synthetic screenshots, one fictional Arabic correction walkthrough, provenance/attribution/asset registers and README/index cross-links. No external icon/font artwork was added to the SVG. Owner-image AI/icon rights remain unknown. All additions are documentation/media plus the isolated diagram generator; no application code, config, schema or fixtures changed.

Capture used a disposable source copy, no-demo launcher, three independently fictional Arabic turns, private ephemeral Ingest secret and a free loopback port. UI correction saved normally; six messages, unchanged original, separate FULL_CORRECTION verified. Empty quality/training/evaluation states were shown honestly; no Gold/model work executed. All screenshots visually reviewed; process stopped via SIGINT. Original owner image has orientation/resolution/color-space/dimension EXIF only; GPS pointer absent.

Verification: fresh 277 passed / 24 skipped / 68 subtests (5.11 seconds), existing warning; 89 Markdown checks, 19 TOC anchors, seven Mermaid parse/renders, SVG XML/local references/accessibility/regeneration, 68 text boxes with no overlaps/outside bounds, minimum text contrast 6.72:1, matching asset hashes. Desktop and 390px previews rendered; narrow SVG needs scroll/zoom. No paths deleted; all 136 protected files including planned SQL match baseline; original README/architecture content and Mermaid retained. No private-original hash certification is claimed. Source provenance found no confirmed copied/adapted app source; prehistory/ownership and exact third-party artifact terms remain unverified. See [visual verification](../visual-documentation-verification.md).

Approval/rollback: remain on this unmerged draft; public history, real-data separation, source license, underlying code/asset ownership and redistribution rights still require decisions. Rollback by ordinary forward revert of continuation commits; no reset, force-push, private-data deletion or production recovery action. Never activate the license or publish because visuals look complete.

## Source-only isolation engineering continuation

Stacked branch from `d5e8c2d` preserves PR #2/main and private baseline hashes. Decision: new candidate-specific HTTP/UI/extension files with byte-identical reusable core, rather than edits to original protected modules. Added hash-pinned allowlist, deterministic manifest, fail-closed validation, explicit fresh-only synthetic fixture loader and exact-candidate installation/API/security/dataset/backup/import tests. Existing lifecycle test requiring proposed SQL was excluded from the candidate after a collection failure; no blocked SQL/source was changed. Tiny-demo export failed existing split rules, so independent contract data was expanded, not the rules. Builder and forbidden-artifact RED failures and socket-restricted failed attempts are retained privately. Rollback is ordinary revert of additions/docs; original implementations, data and training approvals stay untouched. Results: [candidate report](../public-source-isolation-report.md).

Isolation proof: 35-file candidate manifest; exact candidate suite 22 passed / 13 subtests / zero skips; builder suite 5 passed / 3 subtests; original suite 277 passed / 24 skipped / 68 subtests, existing warning. 91 Markdown checks passed. All 250 baseline paths and all 136 protected hashes unchanged. Real browser loaded the separate candidate UI and persisted a fictional correction while retaining the original; instance stopped. Builder deterministic manifests matched; unknown/tampered source/output, forbidden artifacts and dynamic imports were rejected. Current failures/skips are retained in the report; no training, model download, private data mutation or production action.

Final builder portability proof: six tests plus three subtests now pass. A newly added CRLF input regression failed first, then passed after canonical UTF-8/LF hashing/output and LF manifest writing; raw original-source hashes are preserved separately. No original .gitattributes/source change was needed. Prior five-test builder result is retained above as intermediate evidence.

Independent-review closure: four import-binding/alias adversarial probes first failed; checker now resolves package children and rejects imported dynamic helpers. Added unchanged launch wrappers to resolve installer-output mismatch. The reviewer rechecked and reported no remaining Critical/Important findings in scope. Final candidate has 37 files; exact suite 22 passed / 13 subtests / zero skips (1.49s), builder 7 passed / 7 subtests. Linux startup exercises the installed-venv shell wrapper; Windows uses its venv interpreter. Previous 35-file/intermediate results remain recorded.

Stacked Draft PR #3 opened against the unchanged PR #2 documentation branch. Implementation `8763b6e` passed hosted candidate run 40479629375 on Windows and Ubuntu (each builder 7 passed/7 subtests; exact candidate 22 passed/13 subtests, zero skips), and preserved-source run 40479629227 (Ubuntu 277/24 skips/68 subtests; Windows 278/23 skips/68 subtests, existing warning). No build artifact uploaded. CI evidence/report updates are excluded from the candidate and do not change its pinned bytes. Same Private/no-merge/no-license/no-production boundaries apply.
