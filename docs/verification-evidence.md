# Verification evidence and unresolved limits

These are dated observations, preserved to avoid converting old failures, skips or approvals into current claims. Earlier sections retain their original dates and scopes; the PR #13 section separately records verified hosted cleanup results for its exact head. The [initial cleanup record](cleanup-results.md) retains the local pre-push evidence. No installed update, private-data verification, real-model/GPU/owner acceptance, merge or publication approval is claimed here. A later commit requires its own CI results.

## Security and installation evidence — 2026-10-26/27

Baseline defects included cross-origin writes, DNS rebinding, JSON parsed from text/plain, missing browser CSRF/native ingest credentials, and unescaped export-readiness HTML. Reproductions failed before fixes and passed afterward: 19 focused security tests, independent 20 raw HTTP probes and four JS checks. CSRF cannot substitute for ingest credentials or permit another-port Origin. This is bounded testing, not formal proof or public-service certification.

The source-only run originally had 267 passed /24 failed. Exact private prerequisites were then declared: source-only Windows278 passed /23 absent-private-artifact skips /68 subtests; Ubuntu277 passed /24 skips /68 subtests (one Windows-only). Present-but-corrupt fixtures still fail. The private-fixture report recorded293 passed /68 subtests and317 protected artifact hashes; those originals were inaccessible to later audits and remain NOT_VERIFIED there. One old test returned an integer, producing PytestReturnNotNoneWarning; this was never model or production proof.

Windows11 Python3.12.10/SQLite3.49.1 and Ubuntu24.04/WSL Python3.12.3/SQLite3.45.1 exercised fresh/repeated install, paths with spaces, no-demo startup, health, port-conflict/shutdown and SQLite online backup/isolated integrity/FK/count verification. Windows8.3 temporary aliases and newer Python chmod fault-injection keyword forwarding caused initial hosted failures, then were corrected. Startup-before-port-bind was inherited debt. Existing full private backup, live migrations, real GPU/ML and broad OS coverage were not certified.

## Source-only Core evidence — 2026-10-27/28

Review found omitted privacy flags/stale revision could clear restrictions and enable eligibility. Atomic revision/flag preservation, contextual privacy/masks/holdout, constrained downloads and coherent backup/separate restore were implemented in candidate-specific wrappers. Initial dataset checks had5 failures/1 pass; the first fix retained1 failure; independent checks exposed context leakage, linked-root and incompatible holdout cases. Windows hosted acceptance first had5 failures, then2; explicit UTF8 fixture IO and owned staging-path canonicalization corrected them without weakening containment or exclusivity. A late unauthenticated legacy-ingest override was independently reproduced and then refused before parsing/writes.

Final dated candidate source `e03a640`,74 selected files plus manifest `cc94baf399dd66056d8a64b9150237cf5d14ffe651cd67fd9839547138c94044`: Windows/Ubuntu73 tests /68 subtests, builder11 tests /18 subtests, actual browser/harness4 groups covering22 steps PASS.31 findings:30 engineering closures,1 blocked rights/history group.270 baseline paths,136 protected original hashes and12 original media hashes were retained in that work; these are prior preservation observations, not assertions that a cleanup deleting source preserves those paths. WSL/production/private originals remained NOT_VERIFIED. Exact rights ledger remains [rights evidence](rights-evidence.md).

## Chat and Unsloth evidence — 2026-10-31/11-01

Implementation `fc70fd8` local Windows380 passed /24 skipped /68 subtests,8 Node tests;15 Unsloth checks covered DB→review→version→handoff, private context, changed holdout, locking and target-only loss. Local candidate59 passed /15 failed /57 subtests; the same15 failures reproduced on unchanged main (symlink privileges and retained instance lock), so it was not a local PASS. One earlier WinError10053 socket race was not hidden.

Dated hosted source checks [41242203217](https://github.com/abinadwan/NajdiLab/actions/runs/41242203217): Linux379/25 skips/68 subtests, Windows381/23 skips/68 subtests;8 Node tests and synthetic root-browser checks passed. Candidate [41242203310](https://github.com/abinadwan/NajdiLab/actions/runs/41242203310): both OS builder11/18,74 candidate tests/68 subtests and browser/manifest proof passed. These supersede only those earlier platform observations, not the local failure record or this cleanup's verification.

Reviews reproduced and fixed restricted earlier context escaping into a target, mutable SDK handles, mutable/unverified holdout inputs and remaining executable entrypoints. The migration005 schema-COMMIT/ledger-insert gap was reproduced; replay-safe additions preserve Chat after interrupted bookkeeping. Later changes use public SDK instance-bound methods and immutable local Ollama digests: [completion results](chat-completion-results.md). Real installed Gemma4, real LM Studio models, owner Windows acceptance and hardware capacity remain unverified. Native application capture is unsupported; Hermes sender filtering/disconnect remains UNVERIFIED and receiver BLOCKED.

## PR #13 hosted cleanup evidence — 2026-11-01

[Draft PR #13](https://github.com/abinadwan/NajdiLab/pull/13) targets `feat/chat-workspace-claude`. These results apply to cleanup head `f4cff7c5edfd8015f3027eecc9f367c0596239f9`, whose direct parent is PR #12 head `a04e2ea8e1db7fbc094a6ba5ffc30a99d16110f9`; they do not replace PR #12's historical security-fix results or establish success for a later documentation head.

Verified GitHub job metadata and log summaries: [Source checks run 41287022924](https://github.com/abinadwan/NajdiLab/actions/runs/41287022924) and [Source-only candidate run 41287022915](https://github.com/abinadwan/NajdiLab/actions/runs/41287022915). All four jobs completed with conclusion `success`. Windows used Python 3.12.10; Linux used Python 3.12.15.

| Check | Platform / GitHub job | Passed | Failed | Skipped | Subtests passed |
|---|---|---:|---:|---:|---:|
| Source `python -m pytest -q tests -rs` | Windows, `124790279590` | 417 | 0 | 31 | 59 |
| Source `python -m pytest -q tests -rs` | Linux, `124790279777` | 415 | 0 | 33 | 59 |
| Builder `python -m pytest -q public_source/tests/test_builder.py` | Windows, `124790279659` | 12 | 0 | 0 | 18 |
| Builder `python -m pytest -q public_source/tests/test_builder.py` | Linux, `124790279861` | 12 | 0 | 0 | 18 |
| Built Core `python -m pytest -q tests -rs` | Windows, `124790279659` | 78 | 0 | 0 | 68 |
| Built Core `python -m pytest -q tests -rs` | Linux, `124790279861` | 78 | 0 | 0 | 68 |

Windows source skips: **9 opt-in disposable real-Ollama checks + 22 absent-private-artifact checks = 31**. Linux has those same 31 plus **1 Windows PowerShell launcher check + 1 Windows drive-type boundary check = 33**. None counts as passed. The earlier local Windows source **416/32** and Core **75/3** results remain historical; hosted accounts supported the link cases skipped locally. Subtests are reported separately, not added to test totals.

Each source job also passed **5 integration-controller + 5 Chat-controller Node tests**, with zero failures/skips in either Node suite; root real-browser synthetic acceptance passed on both OSes. The source POSIX shell syntax step passed on Linux and was explicitly **SKIPPED on Windows**, not passed there. Each Core job passed its manifest-copy harness and **4 browser acceptance groups** (artifacts/backup, fresh-source recovery, dataset and review). All four jobs passed recursive local-link/generated-API documentation checks over **63 Markdown files**.

Both Core jobs verified **71 selected files** and manifest SHA256 `c8d81fa90d9158197284f1c52894135e81c0c557cc7e1c1ef5fed094787541e8`. This restricted Core profile does not contain full Chat/external handoff and remains `publication_approved=false`.

These are hosted synthetic engineering checks, including Windows/Linux source and isolated Core storage/browser proof. They performed no owner-operated Gemma4/LM Studio/GPU acceptance and do not validate missing private bytes. **Real Gemma4, real LM Studio, GPU/VRAM capacity and owner Windows acceptance remain NOT VERIFIED; Hermes remains BLOCKED.** No merge, installed update, training, deployment or publication approval follows. Use the [owner acceptance guide](chat-windows-acceptance.md) only with the separate approvals it requires. The approved scope remains Chat/review/dataset preparation and external Unsloth handoff.

## Dataset/provenance observations

Earlier v008 reports covered different scopes:30 selected records/24 evaluation records versus76 analyzed assets with2 conflicting-target blockers and52 warnings. v009 had66 gradient-bearing records (24 SFT,34 multi-turn,8 native tool) versus88 analyzed assets,0 blockers/26 warnings; its recorded validation fingerprint was `f86e83620522f99bafb3102697a92bfaf5d1c478f968fe779db6e16f48da1488`. These are dated observations, not a new validation of private bytes. Later source tests cannot close absent-private-artifact checks.

Historical human comparison ended REJECT (24/24 reviews); subsequent zero-step dry run did not imply optimizer work, promotion or rights clearance. Adapter evidence was inconsistent: baseline `6885fe30…`, WSL `c35e8832…`, working tree `b14c7c23…`; cited `bb2c52cf…` was unrecoverable, rejected-run `8c0de8ad…` remained evidence. No copy was reconciled by this cleanup. Old uncommitted live-code inventory11 modified/5 untracked also did not prove that Git matched the installed system. No deployment/reconciliation procedure is retained.

## Privacy, origin and rights

Pattern scans are bounded: no credential match is not a complete secret audit; embedded data in Python defeats extension-only scans. Earlier two backup-location matches were corrected to one independently reproduced location disclosure. Historical identity/path disclosures and unavailable refs/caches/clones remain separate concerns; deleting current files does not clean Git history. [History review](privacy-history-review.md) retains exact counts and strategy limits.

No confirmed copied application source was established, and no internet-wide similarity search was performed; absence of headers is not proof of originality. The rights ledger verifies74 mappings/hashes narrowly, records28 original creation methods UNKNOWN,74 input/material origins UNKNOWN,74 owner attestations required and0 cleared for redistribution. Apache-2.0 is only an approved future target; its inactive proposal anomaly, holder/year/authority, contributor/employer/AI-input/material/UI/asset/notices and exact public destination remain open. See [source provenance](source-provenance.md), [rights evidence](rights-evidence.md) and [release decision](public-release-decision.md).
