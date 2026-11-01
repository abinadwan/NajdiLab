# Chat Windows acceptance — owner-operated

**Status: real Gemma4, real LM Studio, GPU/VRAM capacity and owner Windows acceptance are NOT VERIFIED.** Hosted synthetic CI is separate evidence: [PR #13 results](verification-evidence.md#pr-13-hosted-cleanup-evidence--2026-11-01). Nothing in this guide, a suggested context or green CI grants operational approval. Use short synthetic prompts, never personal conversations. Stop at the first differing result and record it; do not weaken a guard to obtain a reply.

The reviewed scope remains Chat → human review/correction → dataset quality/versioning → external Unsloth handoff. Hermes stays BLOCKED. No internal training, model acquisition, adapter deployment or cloud inference is an acceptance step.

## Approval gates

Obtain separate owner approval for each activity before performing it:

1. Preparing/running the isolated source copy and its synthetic checks.
2. Starting the optional disposable real Ollama binary fixture, even though it is CPU-only and uses generated synthetic weights.
3. Loading an actual model in Ollama or LM Studio, naming the provider, model and chosen context. The UI load checkbox records consent only after that approval; it is not approval to stress the GPU.
4. GPU-intensive checks, repeated long generation, or increasing context/reserve beyond the approved trial. An idle-memory estimate does not authorize this.
5. Deleting the isolated test directory after results are preserved and its exact path is reviewed. Setup or model-load permission does not include deletion permission.

This documentation correction performs none of these owner-operated activities.

## 0. Pin the approved cleanup source and isolate its database

Use Windows PowerShell 5.1 or later, an approved Python 3.11+ installation and Git. The commands below are PowerShell 5.1 compatible. Run them in a dedicated shell; do not reuse the installed NajdiLab directory, its database, exports, backups or configuration.

The branch is `refactor/remove-legacy-training`, targeting `feat/chat-workspace-claude`. The recorded PR #13 CI below covers cleanup source commit `f4cff7c5edfd8015f3027eecc9f367c0596239f9`; a later documentation head needs its own CI and owner approval. Replace the placeholder with the exact full commit approved for this acceptance session. Do not silently test the latest branch tip or substitute PR #12.

```powershell
$ErrorActionPreference = 'Stop'
$ApprovedCommit = '<OWNER-APPROVED FULL 40-HEX COMMIT SHA>'
if ($ApprovedCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Set the exact owner-approved cleanup commit before continuing.'
}
$AcceptanceRoot = Join-Path $env:TEMP ('najdilab-acceptance-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $AcceptanceRoot) { throw 'Acceptance path already exists.' }
git clone --branch refactor/remove-legacy-training --single-branch https://github.com/abinadwan/NajdiLab.git $AcceptanceRoot
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
git -C $AcceptanceRoot merge-base --is-ancestor $ApprovedCommit origin/refactor/remove-legacy-training
if ($LASTEXITCODE -ne 0) { throw 'Approved commit is not in the reviewed cleanup branch.' }
$ReviewedCleanupCommit = 'f4cff7c5edfd8015f3027eecc9f367c0596239f9'
git -C $AcceptanceRoot merge-base --is-ancestor $ReviewedCleanupCommit $ApprovedCommit
if ($LASTEXITCODE -ne 0) { throw 'Approved commit predates the reviewed cleanup source.' }
git -C $AcceptanceRoot checkout --detach $ApprovedCommit
if ($LASTEXITCODE -ne 0) { throw 'Approved checkout failed.' }
$ActualCommit = git -C $AcceptanceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $ActualCommit -ne $ApprovedCommit) { throw 'Commit mismatch.' }
$TrackedState = @(git -C $AcceptanceRoot --no-optional-locks status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $TrackedState.Count -ne 0) { throw 'Acceptance copy is not clean.' }
Set-Location -LiteralPath $AcceptanceRoot
$TestData = Join-Path $AcceptanceRoot 'data'
if (Test-Path -LiteralPath $TestData) { throw 'Expected a new clone without an existing database.' }
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Isolated venv creation failed.' }
$TestPython = Join-Path $AcceptanceRoot '.venv\Scripts\python.exe'
& $TestPython -m pip install -r requirements-chat.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Acceptance dependencies failed to install.' }
$env:NAJDILAB_DISPOSABLE_OLLAMA = '0'
$env:NAJDILAB_NO_DEMO = '1'
$env:NAJDILAB_PORT = '8870'
Remove-Item Env:\NAJDILAB_ALLOW_LEGACY_INGEST -ErrorAction SilentlyContinue
& $TestPython -c "from app.db import DB_PATH; print(DB_PATH)"
if ($LASTEXITCODE -ne 0) { throw 'Database path inspection failed.' }
```

Confirm the printed database path is exactly `$AcceptanceRoot\data\najdilab.db`. This app uses the checkout-local database; do not invent a database-path environment override, copy an installed DB, restore private data or link the clone's data directory elsewhere. Fresh migrations may run only against this new isolated database. Preserve the printed path and full commit SHA with the results. Before every later stage, recheck the commit and tracked-file status; stop if either differs.

Record provider versions and the baseline process/loaded-model state without starting or stopping an unrelated service. Read-only GPU observation, when available:

```powershell
nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,memory.free --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

If NVIDIA tooling or per-process counters are unavailable, record NOT AVAILABLE rather than zero. Do not start LM Studio/Ollama or load a model just to populate this baseline.

## 1. Synthetic source checks and optional disposable binary checks

With the disposable opt-in still OFF, run only after approval for the isolated checks:

```powershell
& $TestPython -m pytest -q tests -rs
if ($LASTEXITCODE -ne 0) { throw 'Record the source-check failure and stop.' }
```

Record actual passed, failed, skipped and subtest counts separately, including skip reasons. A skipped real-engine test is NOT VERIFIED, not a pass. Local account privileges can produce different symlink skips from hosted CI.

Only after separate approval for starting the installed binary, the optional fixture starts its own `ollama.exe` process on a private loopback port, with an empty model directory, GPUs hidden and tiny generated synthetic weights. It does not use the owner's running model/server. It does not qualify Gemma4, a real LM Studio model or VRAM capacity.

```powershell
try {
    $env:NAJDILAB_DISPOSABLE_OLLAMA = '1'
    & $TestPython -m pytest -q tests/test_chat_ollama_real.py -rs
    if ($LASTEXITCODE -ne 0) { throw 'Record the disposable-binary failure and stop.' }
}
finally {
    $env:NAJDILAB_DISPOSABLE_OLLAMA = '0'
}
```

Record skipped checks as NOT VERIFIED if the binary or opt-in prerequisites are absent. Repeat approved disposable checks after an Ollama update, but do not bypass the source-reviewed v0.40.13 allowlist to make a new version work.

## 2. Local binding and Stop security acceptance

Use the scripted loopback fixtures in `tests/test_chat_ollama.py` for adversarial cases; the source-check command above includes them. **Never reproduce cloud retargeting by changing the owner's real tags, connecting a cloud provider or sending a real cloud inference request.** Fake cloud names/metadata are fixture inputs, not permission to contact a cloud engine.

| Case | Expected evidence |
|---|---|
| Immutable local digest binding | Every scripted refusal/count/final Ollama Chat request uses `sha256:<64-hex manifest digest>:local`, not the mutable selected tag; the session fingerprint is bound to that digest. |
| Alias-to-cloud / A→B→A retarget | The fixture records no outbound cloud request and cannot redirect the digest-bound request or falsify its provenance. |
| Alias changed before the first turn | `MODEL_CHANGED` before any text-bearing Chat request; no stored turn or review pair. |
| Invalid digest or unsupported version | `MODEL_REFERENCE_UNVERIFIED` before user text; no inference fallback to a mutable tag. |
| Stop during pre-send metadata | The scripted stalled `/api/show` request is interrupted promptly with `STOPPED`; no text-bearing probe or stored pair. |
| Stop during post-generation metadata | The scripted stalled `/api/tags` verification is interrupted; the generated turn is discarded and no review pair is stored. |
| Stop during generation | Cancel the owned synthetic request; discard partial output and preserve no completed turn/review pair. Actual-model cancellation remains a separately approved check below. |

Review the existing propagation of Stop through `/api/tags`, `/api/version`, `/api/show`, `/api/ps`, probes and final generation. Do not stall or reconfigure the owner's server to simulate these failures. Retain actual timing, refusal codes and storage outcomes; a timeout, retained pair or mutable-tag request is a finding to stop on.

## 3. Ollama with an owner-approved installed model

This section remains NOT VERIFIED until the owner separately approves and performs it. Launch only the isolated copy on the approved free port; a port conflict means stop or choose another approved port, never kill the existing listener. After verifying that the new clone's data path is absent or empty:

```powershell
if (Test-Path -LiteralPath $TestData) {
    if (@(Get-ChildItem -LiteralPath $TestData -Force).Count -ne 0) {
        throw 'Review existing test data before launch; do not reuse it silently.'
    }
}
& $TestPython .\scripts\launch.py
```

First launch creates only this copy's database and local state. Keep that terminal for its own Ctrl+C shutdown. Open the isolated loopback URL (port 8870 in the example), verify `/api/v1/health` names the isolated database, then connect Ollama in this copy's Settings → Integrations. Selecting `gemma4-local:e4b` is not permission to load it.

Choose a context budget `C` and reply reserve `R` only after explicit model-load approval and review of provider limits and available hardware evidence. **8K, 16K and 32K are not assumed memory-safe.** If no initial trial has been approved, stop with capacity NOT VERIFIED. There is no automatic context-escalation step.

| # | Action | Expected | Record |
|---|---|---|---|
| 3.1 | Read device specs without approving a load | Separate model maximum, runtime setting, estimated feasibility and current measurement tiers; no new model load | Baseline model/process state; estimates labeled unverified |
| 3.2 | New conversation without the load checkbox | Refused pending approval; no new model load | Refusal and baseline comparison |
| 3.3 | After separate owner load approval, choose approved `C`/`R`, tick the checkbox and send one short synthetic message | Exact admission or a clear fail-closed refusal; a completed reply alone may be saved | Version, digest/session fingerprint, budget/reserve, token counts, refusal or completion |
| 3.4 | If separately approved, send a few short turns | Input evidence accounts for the complete history, without silent truncation | Input counts and completed-turn receipts |
| 3.5 | Observe memory at approved `C` | Keep engine-reported residency/CPU-GPU split separate from measured NVIDIA device/process VRAM | Before/after observed VRAM, peak observed sample, loaded context, offload and missing counters |
| 3.6 | Try a budget outside the documented application/model ceiling | Refused at creation; no inference needed | Requested limit and refusal |
| 3.7 | At a separately approved small budget, reach the context limit | Notice with counts; old chat saved/closed; new empty chat; draft remains unsent | Rollover and draft/consent state |
| 3.8 | Only with approval for the generation workload, press Stop during generation | Partial turn discarded; no completed pair; owner runtime remains responsive | Stop latency, stored-turn outcome and observed activity; report any continuing load |
| 3.9 | Collection OFF for one completed turn, then ON for one completed turn | Exactly one PENDING item; not dataset eligible before review | Provider, model, `model_key`, review state |

Model maximum context and loaded context are engine ceilings, not allocation safety evidence. The estimate's KV/weight formula and margin are predictions; an `ollama ps` residency value is not a measured free-VRAM guarantee. NVIDIA readings include other processes; attribute only what the available counters actually establish. One successful trial or observed sample does not prove future peak safety. CPU offload is not full-GPU acceptance.

Any higher context, larger reserve, long-generation or GPU-intensive trial needs separate owner approval and recorded measurement conditions. Do not raise 8K → 16K → 32K automatically because an estimate or idle reading appears to leave room. If output is incomplete, a repeat abort occurs, or `CONTEXT_REFUSAL_UNPROVEN` is returned, record it without increasing limits or bypassing a guard merely to obtain PASS. Stop during a cold load may leave engine loading work running; document that limitation rather than claiming it was canceled.

## 4. LM Studio with an owner-approved installed model

Real LM Studio acceptance remains NOT VERIFIED. Starting its server and loading/reloading any model require separate owner approval; NajdiLab does not do that automatically. Use only a local model and synthetic prompts, the same isolated database, and an owner-approved context. A preloaded context still does not prove safe VRAM capacity.

| # | Action | Expected | Record |
|---|---|---|---|
| 4.1 | No model loaded, try New conversation | Specific not-loaded refusal | Message |
| 4.2 | Owner approves/loads the model at chosen context; create at budget no greater than that | Created or fail-closed refusal; excessive budget refused | Model/instance identity, approved context and budget |
| 4.3 | Approved short synthetic turn | Completed reply or explicit refusal; a per-model injected system prompt/count mismatch saves no pair | Token evidence or refusal |
| 4.4 | Only after separate reload approval, reload/change model mid-conversation | Same bound instance may continue; a different identity is refused | Exact identity and result |
| 4.5 | Approved model emits reasoning | Clear refusal, a documented limit | Message |
| 4.6 | Only after workload approval, press Stop during generation | Partial turn discarded; LM Studio remains up | Stop latency and storage outcome |
| 4.7 | Approved context-limit trial | Same explicit rollover/unsent-draft behavior | Result |

Do not stop or reconfigure the owner's LM Studio service to manufacture a case. Defer cases whose prerequisites are not approved; they remain NOT VERIFIED.

## 5. Report, preserve evidence and separately approve cleanup

Report the exact approved/tested SHA, Windows/PowerShell/Python/provider versions, isolated path/port, synthetic pass/fail/skip/subtest counts, digest/refusal/Stop observations, collection/review state, and measured versus estimated memory evidence. Keep real Gemma4, LM Studio, GPU capacity and each unperformed owner check explicitly NOT VERIFIED. Hosted PR #12 historical results, PR #13 cleanup results and this owner's results are distinct records.

Preserve the isolated directory and result record by default. Shutting down the owned test app, unloading an owner model and deleting its test directory are distinct actions; do not stop unrelated services or unload models without their approval. Before any deletion, obtain separate owner approval for the exact resolved `$AcceptanceRoot`, verify it is the disposable clone (not a link to installed/private data), and preserve needed results. No automatic recursive-delete command is provided, and no model/service cleanup is implied by test completion. [Installation](installation.md) and [backup/restore](backup-and-restore.md) retain their separate operational boundaries.
