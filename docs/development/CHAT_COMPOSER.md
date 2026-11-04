# Unified chat composer (V2.1.0)

| | |
|---|---|
| Branch | `update-project` (Draft PR #23). Product version **V2.1.0**, a development candidate, not a release. |
| Scope | Model and context chosen directly in the message box; New chat opens an empty chat at once; one server path prepares the runtime; Chat information is read only; Model library hands models to Chat with **Use in Chat**; copyright moved to the sidebar. |
| Code | `static/chat.js`, `static/index.html` (chat section), `static/najdi.css` (composer), `app/chat_preparation.py` with `GET /api/v1/chat/models` and `POST /api/v1/chat/prepare`, `NativeRuntime.running()`, `static/models.js` (Use in Chat), `app/version.py`. |

## 1. What the user sees

- **Composer.** The message box contains a compact control row below the text: the **model** button (short readable name and a status dot), the **context** button (4K, 8K, 16K, 32K), **Collect for review** (visibly on or off), and a round **Send** icon button that becomes **Stop** while a reply runs. Context usage stays a quiet meter below the box. One short hint line remains (Enter sends, Shift+Enter adds a line); the consent explanation moved to the Collect control's tooltip and screen-reader description and to Chat information.
- **Model menu.** Grouped by runtime (NajdiLab Native, LM Studio, Ollama). Each entry shows its verification (*Verified*, *Local file*, *Not verified yet*, *Connected runtime*), quantization, the model's maximum context and whether it is loaded and at which context. Unusable entries are listed but disabled with the reason (for example *llama.cpp runtime not installed*). The footer opens **Model library** and, while NajdiLab Native runs, offers **Stop NajdiLab Native (frees memory)** with confirmation. Nothing is downloaded from here.
- **Context menu.** 4K–32K as radio choices; sizes above the model's known maximum are disabled. **Advanced** (closed by default) holds a custom context, the reply reserve and GPU use for NajdiLab Native.
- **New chat.** Opens an empty chat immediately with the last valid choice as the suggestion; no dialog, no model loaded, nothing saved until the first message is sent. Collection starts off; it may be switched on before the first message and then applies to that new chat only.
- **Preparation card.** When sending needs something first, a card above the composer says what and why, with one action: *Start model* (Native stopped), *Restart with this model* (Native runs another model or context; the card names what is loaded now), *Allow* (Ollama load, or selecting the model in LM Studio). A model that cannot run here (no runtime, does not fit, above its maximum) gets a card with the reason and, if useful, *Open Model library*. *Not now* closes it. The unsent message stays in the box through every step.
- **Chat information** (was *Chat settings*). Read only: model and provider, model identity (SHA-256 for NajdiLab Native), conversation context budget, reply reserve, actual loaded context, GPU use, runtime version, devices, measured GPU memory where Windows reports it, per-turn token usage, last-reply timings, verification, and privacy and collection status. No selectors and no Start/Stop.
- **Model library.** *Use in Chat* replaces *Check fit and load…*: it opens Chat with an empty draft and that model chosen, keeps the user's context, and starts nothing. The Advisor's context and GPU settings in Discover are labelled *Simulation only* and never change a chat. Runtime install, repair, update and uninstall stay in *llama.cpp runtime*.
- **Copyright.** Shown once, in the sidebar under *Local only / 127.0.0.1:port*, smaller than navigation labels; translated (*© 2026 نجدي لاب. جميع الحقوق محفوظة.*); hidden visually but still read by screen readers when the sidebar is collapsed; no page footer.

## 2. State and invariants

One selection drives the composer: `{provider, model, context, reserve, gpu}`. An open conversation shows its own stored values; a draft shows the user's choice (the last valid choice is remembered in the browser only).

1. A conversation never changes model, context or reply reserve. Choosing differently in a conversation with saved turns asks *Start a new conversation?*; on confirmation an empty draft with the new choice opens, the old conversation stays unchanged, the unsent text moves along, and collection starts off. An empty draft simply takes the new choice.
2. The conversation record is created by the first send, after preparation, with the existing exact checks (`ChatWorkspace.create`: engine ceiling, model identity and SHA-256 binding for Native and Ollama, Ollama load approval).
3. Every send first asks the server's single preparation path (`prepare`, without approval). Only a `READY` answer sends; any other state shows the card and nothing is sent.
4. Consent is unchanged: off by default and after restart, explicit per conversation, never copied into a new conversation, never retroactive. A draft's Collect choice is applied to its new conversation right after creation and before its first message.
5. The draft text is cleared only after a reply was saved (`COMPLETED`), exactly as before.

## 3. One preparation path

`POST /api/v1/chat/prepare {provider, model, context_budget, reply_reserve, gpu_layers, approved, new_session}`:

| Runtime | Without approval | With approval |
|---|---|---|
| NajdiLab Native, same model and context running | `READY` (reuse; no restart) | — |
| NajdiLab Native stopped | `NEEDS_START` | Smart Model Advisor memory check; `BLOCKED/DOES_NOT_FIT` or start → `READY` |
| NajdiLab Native running another model or context | `NEEDS_RESTART` with what is loaded | Stop NajdiLab's own process (refused with `NATIVE_BUSY` while a reply holds it), memory check, start → `READY` |
| NajdiLab Native busy with a reply | `BUSY` | never restarted |
| LM Studio, model not selected | `NEEDS_APPROVAL` (select) | select → `READY` |
| Ollama, new chat | `NEEDS_APPROVAL` (load) | `READY` with `load_approved` for this new chat only |
| Not connected, model gone, no runtime, above maximum, unverified file | `BLOCKED` with the code | — |

Before anything is approved the Native path already runs the existing start gate (managed runtime files exact, managed model verified `READY`), so an unverified file is refused before any approval is asked. A second preparation while one runs gets `RUNTIME_PREPARING`. The server still enforces `ENGINE_CONTEXT_MISMATCH`, `MODEL_CHANGED`, `CONTEXT_SHRANK`, `STALE_SELECTION`, exact admission and incomplete-reply refusal on every turn; preparation adds no shortcut around them.

`GET /api/v1/chat/models` lists NajdiLab Native files (with Model library verification), and the models of connected LM Studio / Ollama, plus NajdiLab Native's state, loaded model and context.

## 4. Version policy

`app/version.py` is the only source (`2.1.0`; display `V2.1.0`; status `development-candidate`). The server banner, `Server` header, `/api/v1/health`, `/api/v1/config`, the Hugging Face and runtime User-Agents, the sidebar and Settings read it; `tests/test_version.py` rejects hard-coded product versions. From V2.1.0 on, each owner-approved batch of features or fixes gets one SemVer step (minor for new user-facing capability, patch for fixes only, major for incompatible data or API changes), recorded with its reason in `CHANGELOG.md`; commits inside one batch do not bump it. Dataset versions, GGUF revisions, migrations and dependency versions never follow it.

## 5. Tests and results (development checkout, 2026-11-04)

| Suite | Result |
|---|---|
| Python (`pytest tests`) | 893 passed, 38 skipped, 0 failed; new `tests/test_chat_preparation.py` 7 passed (reuse, start, restart only with approval and never during a reply, memory refusal, invalid and unverified choices, LM Studio select and Ollama load approval) |
| Node unit tests (CI list) | 61 passed (context options, switch rule; the two evidence-preset tests and two hardware-table tests were replaced with the server-side preparation tests) |
| chat-browser | PASS (5 of 5 consecutive runs after two timing fixes): no New chat dialog, model and context in the composer, conversation created by the first send, Ollama approval and *Not now*, switch confirmation, Stop replacing Send, context limit keeps the draft, read-only Chat information, 320/390 px, 400 % zoom model menu |
| chat-enhancements-browser | PASS: choosing is read-only (no `/select`, no approved preparation), an Ollama approval is never reused, wrong runtime selection never sends, drafts kept |
| models-browser | 16 passed: Use in Chat (opens an empty chat, starts nothing, explains `NATIVE_SERVER_MISSING`), copyright location in both languages, themes and collapsed sidebar, version V2.1.0 |
| i18n-browser | 10 passed (model menu, context menu, preparation card and Chat information scanned in Arabic) |
| a11y-browser | 13 passed |
| UX audit (axe WCAG 2.1 A/AA, 284 states: desktop/tablet/mobile, light/dark, Arabic/English, 200 % and 400 % zoom, model menu, context menu, Chat information, preparation card, delete dialog) | 0 violations, 0 horizontal overflow. The first run found 24 `aria-required-children` violations (headings directly inside `role="menu"`); fixed with one labelled group per runtime. |
| review-restrictions, public-source builder, docs, API inventory, compileall | 12 passed, 12 passed, PASS, PASS, ok |

Fixed during testing: the switch dialog never received `close` in the desktop app's browser (now settled by its buttons); an approved Ollama preparation re-asked instead of sending (the approved result now carries into creating the chat); a refused over-long message's bubble stayed until the lists refreshed; the model menu could extend past a 225 px-high screen; the collapsed-sidebar copyright kept its padding; in Chat information a long unbreakable value (SHA-256 identity) took the whole row and overlapped its label (value column now capped with `fit-content(65%)`; `chat-browser` checks it and fails on the old rule).

### Installed test copy (`C:\Users\Admin\NajdiLab-Update-Test`, http://127.0.0.1:8870, 2026-11-04)

Updated in place by fast-forward (no reinstall); only the NajdiLab launcher/server processes were restarted. Real models on the RTX 5070, NajdiLab Native llama.cpp `b12059-1b6935b22`:

| Check | Result |
|---|---|
| Version | `/api/v1/health` 2.1.0, sidebar V2.1.0 |
| Model library → *Use in Chat* (Qwen) | empty chat with *Qwen2.5-0.5B-Instruct · Q4_K_M · 8K*; nothing started |
| Reuse | Native already running Qwen at 32K; a 32K chat sent with no card and no restart (start time unchanged); reply in 771 ms; draft cleared after save |
| Mismatch before sending | 8K chat while Qwen ran at 32K: *Restart NajdiLab Native?* shown before anything was sent, draft kept; after approval Qwen restarted at 8K (new PID), real reply, draft cleared |
| Switch model in a conversation with turns | *Start a new conversation?*; old conversation unchanged; draft moved along |
| Gemma 4 E4B | card named the loaded Qwen · 8K and the needed Gemma · 8K; after approval Native ran Gemma at 8192 (new PID), real reply "The capital of Saudi Arabia is Riyadh.", thinking shown, draft cleared |
| Opening an older conversation | 32K Qwen conversation while Gemma ran: restart card shown on open, before typing; after approval Native ran Qwen at 32768 again (the state found before testing) |
| Chat information | read only; loaded file SHA-256 equals the conversation's model identity; actual loaded context 32768; device RTX 5070; collection Off |
| Model library and runtime | 62 files, 6,417,019,635 bytes unchanged against the pre-update snapshot; Gemma `676c3507…53fbaee` and Qwen `74a4da8c…7d9db` re-hashed and equal to their verified records |

## 6. Risks and limitations

- The memory check before a start is the Advisor's conservative estimate; it can refuse a model that would fit (see the Gemma 4 note in [REAL_MODEL_ACCEPTANCE.md](REAL_MODEL_ACCEPTANCE.md)). It never forces full GPU offload.
- A restart stops the previously loaded Native model even if the new one then does not fit (the card says *Restart*; the result says it stopped the previous one).
- LM Studio's own context limit is only known once a chat is created; its context options are not narrowed in advance.
- Some embedded browsers never fire the dialog `close` event; the switch dialog settles from its own buttons.

## 7. Rollback

`git revert` the V2.1.0 commit on `update-project` and redeploy the test installation in place (`git fetch` + fast-forward to the earlier commit, restart). No migration or stored data changed; conversations, reviews, downloaded models and the managed runtime are untouched by either direction.
