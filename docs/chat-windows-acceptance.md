# Chat Windows acceptance — owner-operated

Nothing here has been performed on an installed model. Run it yourself, on a copy of the branch, before any merge or update decision. Use short synthetic prompts, never personal conversations. Each step lists what to record. Stop at the first result that differs and record it instead of working around it.

## 0. Prepare an isolated copy

No installed NajdiLab, database or backup is touched. Use a separate clone and a new empty data folder.

```powershell
git clone https://github.com/abinadwan/NajdiLab.git $env:TEMP\najdilab-acceptance
```

```powershell
git -C $env:TEMP\najdilab-acceptance checkout feat/chat-workspace-claude
```

```powershell
cd $env:TEMP\najdilab-acceptance; python -m venv .venv; .venv\Scripts\python -m pip install -r requirements-chat.txt -r requirements-dev.txt
```

Record `git rev-parse HEAD`, `ollama --version`, the LM Studio version and the output of `nvidia-smi`.

## 1. Automated checks on your machine

```powershell
.venv\Scripts\python -m pytest -q tests
```

Then the real-engine checks. They start your installed `ollama.exe` on a private port with an empty model folder, hidden GPUs and a tiny generated model. Your running Ollama and your models are not used.

```powershell
$env:NAJDILAB_DISPOSABLE_OLLAMA='1'; .venv\Scripts\python -m pytest -q tests/test_chat_ollama_real.py
```

**Pass:** all pass. Repeat this step after every Ollama update: a failure here is what tells you an update changed the behavior Chat depends on.

## 2. Ollama with your installed model

Start the copy on a port of your choice from step 0, with its own data folder as documented in [installation](installation.md). Connect Ollama in Settings → Integrations and select `gemma4-local:e4b`.

| # | Action | Expected | Record |
|---|---|---|---|
| 2.1 | Read device specs before any chat | Four separate evidence lines; suggestion labeled unverified; model not loaded (`ollama ps` empty) | Suggested context |
| 2.2 | New conversation without the load checkbox | Refused, asks for approval; nothing loaded | Message |
| 2.3 | Budget 8192, reserve 2048, tick the load checkbox, send one short message | Reply appears. `ollama ps` shows the model at context 8192 | Token numbers; GPU/CPU split in `ollama ps` |
| 2.4 | Send three more messages | Input tokens grow every turn | The four input counts |
| 2.5 | Read device specs again | "Measured now" line shows real size at 8192 | Size and GPU share |
| 2.6 | Budget above 131072 | Refused at creation | Message |
| 2.7 | Small budget (for example 1024, reserve 512), keep chatting until the limit | Clear notice with numbers; old chat saved and closed; new empty chat opens; draft stays unsent | Whether the draft was retained |
| 2.8 | Long request, press Stop | Turn discarded. `ollama ps` shows no runaway; GPU use falls | Time to stop |
| 2.9 | Collection OFF, one turn; then ON, one turn | Review Queue gains exactly one PENDING item, not training eligible | Item's provider, model, `model_key` |
| 2.10 | Raise the budget stepwise (16384, 32768) only if 2.5 left room | Your own measured capacity; a chat may fall back partly to CPU, shown in `ollama ps` | Largest context fully on GPU |

Step 2.10 allocates real GPU memory and is your choice to run. If a Thinking model uses the whole reserve the turn is refused as incomplete; raise the reserve up to 8192. If Ollama reports a token repeat abort, the turn fails and saves nothing: that is the engine stopping a looping reply.

## 3. LM Studio with your installed model

LM Studio's server must already be running with the model loaded by you. NajdiLab will not start it or load anything.

| # | Action | Expected | Record |
|---|---|---|---|
| 3.1 | Model not loaded, try New conversation | Refused with a "not loaded" message, not a generic failure | Message |
| 3.2 | Load it at a chosen context, new conversation at a budget ≤ that | Created; budget above it refused | Loaded context |
| 3.3 | Send a turn | Reply saved. If LM Studio adds a system prompt from its per-model settings, the count differs and the turn is refused with no pair saved | Token numbers or refusal |
| 3.4 | Reload the model mid-conversation, send | Continues if the same model; `MODEL_CHANGED` if a different one | Result |
| 3.5 | Model that emits reasoning | Refused with a clear message (a documented limit) | Message |
| 3.6 | Long request, press Stop | Discarded; LM Studio stays up | Time to stop |
| 3.7 | Context limit, as in 2.7 | Same rollover behavior | Result |

## 4. Report

Send the recorded values with the commit hash. Any refusal in 2.3 or 3.3 is a finding, not a failure to work around: `CONTEXT_REFUSAL_UNPROVEN` means your installed model's path did not refuse overflow, so Chat correctly stays blocked for it.

Remove the copy afterward with `Remove-Item -Recurse $env:TEMP\najdilab-acceptance`. Models you loaded stay loaded until their keep-alive expires or you unload them.
