# Windows 11 + RTX 5070 acceptance — checklist for an authorized run

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

**Status on 2026-11-03: BLOCKED.** No computer was connected to the development session, so nothing below has been run on Windows or on a GPU. Every item is **NOT TESTED** until the owner (or an authorized session connected to the owner's computer) runs it and records the report.

Tool: `scripts/acceptance_chat_v2.py` (validated on Linux for its non-GPU steps: migration-on-a-copy PASS, Native CPU start/stop/unload PASS with a synthetic model).

## Ground rules

1. Use a **separate development checkout** (for example `%USERPROFILE%\NajdiLab-acceptance`), never `%USERPROFILE%\NajdiLab-PR19-20-Local`. The tool refuses to run inside the folder that holds `--database`.
2. The permanent database is only **read** (SQLite online backup into a temporary folder). Migrations run on the copy. Nothing in the permanent installation is written, migrated or deleted.
3. Do not stop the permanent NajdiLab, Ollama or LM Studio for this. Do not run memory stress tests on production processes. Each context is tried once; an out-of-memory start is reported as FAIL, not retried.
4. Permanent deletion is tested only on synthetic data (the test suite); never on real conversations.
5. Updating the permanent installation is a separate step that needs the owner's explicit approval **after** this report passes, and a fresh verified backup.

## Setup (isolated checkout)

```powershell
git clone https://github.com/abinadwan/NajdiLab.git %USERPROFILE%\NajdiLab-acceptance
cd %USERPROFILE%\NajdiLab-acceptance
git checkout feature/chat-experience-v2
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-chat.txt
npm install --prefix ..\chat-browser-tools --ignore-scripts --no-audit --no-fund puppeteer-core@25.16.0
$env:NODE_PATH = "$PWD\..\chat-browser-tools\node_modules"
```

## Run

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_chat_v2.py `
  --browser "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --database "%USERPROFILE%\NajdiLab-PR19-20-Local\source\data\najdilab.db" `
  --llama-server "C:\tools\llama.cpp\llama-server.exe" --gguf "D:\models\gguf\<model>.gguf" --gpu-layers all `
  --ollama-model "gemma4-local:e4b" --approve-model-load `
  --contexts 4096,8192,16384 --report acceptance-report
```

Adjust the paths. Drop `--ollama-model/--approve-model-load` if Ollama must not load anything now (the step is then NOT TESTED). `--approve-model-load` means Ollama may load or reload the model at each context; that is the same consent the Chat dialog asks for.

## What it covers

| # | Requirement | Step in the report |
|---|---|---|
| 1 | Python and Node regression tests on Windows | `pytest tests`, `pytest public_source builder`, `node unit tests` |
| 2 | Browser acceptance in Arabic and English (incl. 320/390px, keyboard, zoom) | `chromium *.cjs` (5 suites) |
| 3–7 | Gemma 4 on installed Ollama: real streaming, thinking separation, completion integrity, real token counts | `ollama: <model> at <context>` (tokens, content/thinking deltas, timings; a refusal shows `code · check · hint`) |
| 7 | Stop/cancellation (Native) | `native: … stop` (stops at the first token; must save nothing) |
| 8 | Contexts 4096 / 8192 / 16384 | one row per context, each tried once |
| 9–11 | Native llama.cpp CUDA on RTX 5070, GGUF load/stream/stop/unload, GPU/CPU | `native: devices`, `native: … at <context>`, `… unload`; rerun with `--gpu-layers 0` for CPU |
| 12 | VRAM reporting and out-of-memory recovery | `measured VRAM` in the Native rows; an OOM start must FAIL with `NATIVE_OUT_OF_MEMORY` and leave the runtime STOPPED |
| 13 | Migration 008 on an isolated copy of the real database | `migration 008 on a copy`, `existing conversations open after migration (copy)` |
| 14 | Backup and restore | Manual, below |

## Manual steps the tool does not automate

- **LM Studio** (real model): load a model in LM Studio yourself; in the isolated instance (`$env:NAJDILAB_PORT='8871'; .\run.ps1`, separate data folder) create a chat, send two messages, press Stop once, try a reasoning model and confirm thinking appears separately and is not saved.
- **Backup and restore:** in the isolated checkout run `python scripts\backup.py`, restore it into a new folder as in `docs/backup-and-restore.md`, and open it read-only.
- **IME:** type Arabic with the Windows IME; Enter while a candidate window is open must not send.
- **Screen reader** (Narrator/NVDA): the chat list, menu, dialogs and streaming status announce correctly.

## Recording the result

Attach `acceptance-report\acceptance.md` and `acceptance.json` to PR #22 (they contain no conversation text; model names and paths only). Any FAIL blocks acceptance until explained. NOT TESTED rows stay NOT TESTED; they are not PASS.
