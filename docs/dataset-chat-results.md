# Dataset-first Chat execution ledger and results

> Evidence as of `aa328ff`. Ollama sending, hardware recommendations and the LM Studio handle path changed afterward; see the [completion report](chat-completion-results.md). This ledger is retained unchanged as the record of that point.

Plan: [implementation plan](superpowers/plans/2026-10-31-dataset-chat.md). Base: `d992b0a`. Prepared for a **draft PR**, not merge/installation approval. Evidence collected across 2026-10-31 / 2026-11-01 (Asia/Riyadh).

Initial audit and design complete. Native worktree tool rejected a nested repository root; a separate Git linked worktree was created within the authorized workspace instead. No changes to the older #10 checkout.

Ruling: proceed with the owner's explicit implementation scope without another generic design approval; defer only destructive data choices. Preserve historical implementation modules during staged retirement rather than remove data-dependent imports. Ollama sending fails closed pending an exact supported preflight; this is a material remaining limitation.

## Delivered / remaining

Delivered: read-only audit/KEEP-REMOVE-DEPRECATE map; dataset-first UI/API/CLI retirement; saved raw multi-turn Chat and transactional opt-in pending review segments; exact LM Studio admission/instance binding; explicit context rollover; Stop/error/restart/archive safeguards; read-only device snapshot; privacy-locked source export and immutable Unsloth prompt/completion handoff; architecture/roadmap/rollback/API docs.

**Not complete:** Ollama sending (exact public preflight unverified), numeric per-model memory recommendation (KV/placement/overhead evidence unavailable), actual engine/model acceptance, owner Windows acceptance and any approved allocation experiment. Native application capture remains blocked/unsupported; Issue #9 stays open. No user data, existing migrations, exports, models, services or configurations were removed/modified. No training/merge/deploy/installed update ran.

## Local evidence

| Check | Observed result |
|---|---|
| Full Windows Python3.12 suite with optional SDK in isolated .venv | **380 passed, 24 skipped, 68 subtests, one pre-existing warning** on implementation head fc70fd8 |
| Chat lifecycle after final atomic rollover correction | 20 passed; injected insertion failure leaves original OPEN; restart never replays unfinished receipt |
| Actual SDK1.5.0/helper with disposable synthetic WebSocket engine | bound count/predict specifiers; replacement at prediction boundary refused; no model load/unload/preset/history harvesting |
| Node controllers | 8 passed (3 Chat, 5 Integrations) |
| New Unsloth checks | 15 passed: DB→review→version→handoff, private/excluded prefixes, frozen/changed holdout, write-lock, target-only loss |
| Source-only builder/verify | 11 passed / 18 subtests; 74-file candidate verified; manifest-only harness passes |
| Local candidate suite | 59 passed / 15 failed / 57 subtests; **same 15 failures reproduced on unchanged main**: Windows symlink privilege unavailable and existing fixture retains `.core-instance.lock` during cleanup. This is not a local candidate PASS |
| Prerequisites, compile, JS syntax, docs/API/whitespace | pass; migrations001–004 preserved |

One baseline socket race (WinError10053) was observed before implementation; no security policy was weakened to mask it. No owner GPU/stress probe ran.

## Fresh review / fixes

Independent review found four Important issues and no Critical issue; all were reproduced and corrected:

1. Private/excluded prior context survived into a later target: now whole-window refusal, privacy provenance/attestation and one BEGIN IMMEDIATE across recheck and full source snapshot.
2. SDK symbolic handles could retarget inference: every template/token/context/predict operation now uses an immutable instance-reference specifier. Pinned private session helpers are a compatibility limitation; unknown SDK versions fail closed.
3. GGUF/Ollama exporter and direct benchmark CLI were still executable: now refuse before dependencies, with other trainers. Importable historical validation helpers/reports remain deliberately retained.
4. Leakage analysis used mutable/unverified holdout: every quality input is hash-verified, privately snapshotted, then rechecked before handoff publication; evaluation_holdout.jsonl is explicitly an evaluation file.

Manual browser proof found an initially preselected training checkbox on PENDING rows; it now reflects the server's false flag until human choice. Windows browser test exercised raw text, OFF→ON consent, exactly one PENDING pair and restored history, using synthetic engines only. [UI evidence](images/screenshots/chat-workspace-synthetic.png). Hosted root-browser checks also cover escaping, rollover/no draft replay, Stop, Ollama refusal and retired views; result pending below.

Ruling: shared candidate files (`dataset_platform.py`, `review_integrity.py`, `service.py`, `install.py`) were repinned at their owning layers for holdout/privacy/snapshot/startup behavior. New Chat files and migration005 remain excluded; no publication scope expands. Cost if wrong: candidate regression requires restoring reviewed pins; hosted candidate checks remain a merge gate.

## Hosted final-head gate

Implementation head **fc70fd83722f07fbd5361b9147f4c88d7543c155** has all four jobs green:

- [Source checks](https://github.com/abinadwan/NajdiLab/actions/runs/41242203217): Linux **379 passed / 25 skipped / 68 subtests**; Windows **381 passed / 23 skipped / 68 subtests**. Eight Node controller tests and the real hosted root-browser acceptance pass on both. One existing Python warning remains. Host-specific symlink/OS and private artifact availability explain skip differences; no critical Chat case is skipped in hosted proof.
- [Source-only candidate](https://github.com/abinadwan/NajdiLab/actions/runs/41242203310): both OS builder **11 passed / 18 subtests**, **74 candidate tests / 68 subtests**, manifest verification, manifest-only harness and candidate browser acceptance pass. This supersedes the local candidate environment failures as hosted-platform evidence, without concealing those local failures.
- Browser evidence is attached as workflow artifacts. It uses only synthetic own sessions/engines. It is neither actual LM Studio model acceptance nor native app history capture.

A final migration recovery check reproduced the existing loader's schema-COMMIT/ledger-insert crash gap. New migration005 is now idempotent, so replay preserves completed Chat data if that ledger insert was interrupted. Migrations001–004 remain unchanged. The regression failed before the correction and passes after it; final-head CI is tracked in PR checks. [Draft PR #11](https://github.com/abinadwan/NajdiLab/pull/11) stays unmerged; no installed update or publication is approved.

## Rollback / retention

[Owner procedure](chat-workspace.md#backup-and-rollback): restore reviewed source with additive data/tables retained; never overwrite a live DB or erase exports. Parent source restores old training interfaces, so review before launching a rollback. Physical erasure/historical export purging remains a separate retention choice.
