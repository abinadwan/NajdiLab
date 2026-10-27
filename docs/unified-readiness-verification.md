# Unified readiness verification — 2026-10-27

Scope: `dev/open-source-final-readiness`, based on remote main `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. PR #1 was already merged and the old branch deleted before this task. No open PR existed at reconciliation. The local commit `5ac0f2b99bef445e119e4bdb7fb5289464947de9` was present; its parent tree exactly matched main. Its 14-file documentation diff was reviewed and incorporated as `5d9fde8`; the old branch/commit remain preserved. The initial working tree was clean and there was one local worktree. No governance conclusion about who authorized the earlier merge is inferred.

## Environment and reproducible checks

Current host is a Linux container, Python 3.12.14, SQLite 3.53.1, Git 2.52.0; it is not a fresh Windows or WSL machine. Python minimum 3.11 and SQLite minimum 3.24 are enforced by `scripts/local_runtime.py`; SQL UPSERT in the dataset registry motivates that SQLite floor. No measured CPU/RAM/disk/VRAM minimum is claimed.

| Check / exact command | Current result | Scope and limits |
|---|---|---|
| `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs --junitxml=/workspace/private-audit/unified-tests.xml` | **277 passed, 24 skipped, 68 subtests passed**, 4.84 seconds | pytest 9.1.1 installed separately. One pre-existing PytestReturnNotNoneWarning; 23 private-artifact skips and one Windows-only skip |
| Security/English/Arabic/review/dataset/training authorization tests | Included in the full-suite result above | Temporary/mocked state; no real training or production access. Test count is not multiplied by listing categories |
| `python scripts/check_docs.py` | PASS: 82 Markdown files | Local Markdown file links and generated API inventory |
| README opening / contents anchors / version labels | Reviewed and mechanically checked | No badges/legal table before introduction; software/dataset/Corpus/runtime versions distinguished |
| `python -m compileall -q app scripts tests`; `sh -n run.sh scripts/install.sh` | PASS | Syntax, not runtime certification of historical tools |
| `python scripts/install.py --check`; `git diff --check`; `git fsck --full` | PASS | Read-only setup check; Git integrity/whitespace |
| Current Windows PowerShell installation | **SKIP** | No Windows/PowerShell runtime here; commands inspected against unchanged scripts |
| Current WSL installation | **SKIP** | No access to WSL or NajdiTrain; do not use a training environment for onboarding |
| Original private data/hash validation | **SKIP** | Original 317 private artifacts unavailable; prior result is historical only |
| Optional ML dependency execution / GPU/model tests | **SKIP** | No training packages, weights, training, model export or deployment |

To reproduce in a new authorized clone: select this review branch, follow README setup, bootstrap ensurepip only for development, install requirements-dev.txt, run the full suite with `-rs`, then `python scripts/check_docs.py`. Use a fresh checkout and a free local port; setting a new port alone does not isolate state. The absolute PYTHONPATH/JUnit paths above describe this execution workspace, not a prerequisite on another developer's computer. Logs contain no real corpus inputs and remain private outside the checkout.

## Fresh isolated installation rehearsal

A temporary source-only copy in a path containing spaces used `sh scripts/install.sh` twice, `sh run.sh` on a dynamically selected loopback port, and synthetic-only authenticated Ingest. Observed PASS:

- Setup/repeated setup created no database; an existing synthetic `.env` sentinel was preserved.
- Actual launcher health returned 200; demo messages were absent before synthetic ingestion; a second launch on the occupied port failed.
- A synthetic Arabic request was authenticated; stored user text matched exactly and two message rows were present.
- `scripts.backup.create_backup` created an online SQLite snapshot. ZIP CRC, isolated restore, integrity_check, foreign_key_check and row counts passed.
- SIGINT stopped only the disposable process group with exit 0. Reinstall after shutdown preserved database bytes.

This uses existing migrations only in disposable state, never blocked/proposed SQL or production. The private reproduction script and service logs are retained outside tracked source. Installation regressions in the suite also cover unsupported interpreter, incomplete venv and injected permission failures. No production database, backup destination, service or external runtime was operated.

Prior Windows 11 evidence: Python 3.12.10 / SQLite **3.49.1**. Prior Ubuntu 24.04/WSL2: Python 3.12.3 / SQLite **3.45.1**. These are from [installation verification](installation-verification.md), not reruns. PowerShell/browser exact versions were not established. The prior hosted CI run is historical until fresh Draft PR checks complete.

## README and diagrams

The README was reviewed against HTTP/security/service/dataset/runtime modules and the existing guides. It now starts with the concept/problem/capabilities, then navigation/status. Two Mermaid flowcharts show optional runtime boundaries, original/overlay preservation, zero-step Dry Run, distinct Smoke/Full approvals and blocked future model release. Both diagrams parsed and rendered successfully with Mermaid **12.2.0** using the installed ESM package served over loopback HTTP and Chromium. Both rendered PNGs were visually inspected: labels, original/overlay flow, optional boundaries and blocked release links were legible at desktop size. The architecture is wider than the sequential workflow; mobile/GitHub-specific visual behavior was not independently tested. All **18 README contents anchors** and the required introduction-first opening passed a mechanical check.

The screenshot is the existing synthetic Arabic text-storage example. It was visually inspected in the preceding audit, with no EXIF marker detected; no real-data screenshot was added. Original artwork/frontend authorship still needs owner confirmation; visual privacy review is not copyright clearance.

## Official external references

All **19 distinct non-repository HTTPS links in README returned HTTP 200** with redirect following during this run: Python, SQLite, Git, MDN, Python HTTP docs, Microsoft PowerShell/WSL, Ubuntu, NVIDIA driver/CUDA, PyTorch, Transformers, Unsloth, PEFT, Accelerate, bitsandbytes, Hugging Face Hub, Ollama and pytest. Repository access/Private visibility was verified through the connected GitHub service. Loopback URLs describe local operation, not public downloads. A reachable link is not an artifact-license or package-compatibility guarantee.

## Preservation, rights and release scope

All **132** tracked app/script/test/static/config/migration files matched the initial SHA256 inventory after the full test run. This task modifies documentation/proposals only, avoiding unproven changes to research-bearing source. The historical privacy review (7 commits/328 blobs at its baseline) remains applicable; new history introduced here contains documentation only and must pass final staged review. Personal historical paths, protected research modules and rights/license approvals remain blockers. See [decision](public-release-decision.md), [history](privacy-history-review.md), [matrix](dependency-licensing-matrix.md) and [data/model policy](dataset-model-distribution-policy.md).

The tagged license evidence and exact returned-text hashes from the preceding audit are preserved, not misrepresented as new binary verification. Current upstream terms do not certify older installed wheels; Unsloth optional AGPL scope and unverified historical artifact terms remain explicit. No active root LICENSE is added.

## Failures and limitations retained

Initial Mermaid CLI setup failed because its default cache directory was unavailable; retry used a workspace-local cache. The installed CLI rejected an older width option; its documented size option was used. The default file-URL renderer was blocked by browser policy, so rendering was attempted using the same locally installed Mermaid package over loopback HTTP. Earlier missing-pytest/socket-restricted failures remain in the preceding audit; none is erased or counted as passing. No global policy, production runtime or package setting was changed.

## Final results and delivery

Local final documentation, diagram, hash, syntax and installation checks passed as recorded above. Hosted CI will be inspected on the Draft PR; no historical CI pass is claimed for a new commit. No automatic merge, public conversion, source license activation or deployment follows. Ordinary source revert is the rollback; private-state recovery remains a separate verified restore, not a reason to rewrite history.
