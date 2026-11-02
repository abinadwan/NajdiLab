# Chat controls, keyboard sending and reply presentation

## What caused the reported UI behavior

The composer had a form submit handler but no textarea keyboard handler. A textarea therefore inserted a newline on Enter. Sending also needed a common guard for blank drafts, pending/busy requests, closed sessions and the saved conversation's original model.

Replies were assigned to a paragraph's `textContent`. That safely displayed the original model text, including Markdown syntax; it was not a Markdown renderer. A literal backslash followed by `n` in a model reply is also literal model output, not a newline for the UI to decode.

New conversations previously exposed only manual context/reply inputs. Hardware evidence reported model maximum, current runtime context and memory estimates separately, but did not expose the authoritative admission ceiling to the UI. Reading hardware also unnecessarily called the model-selection helper before reading evidence.

## Budget controls

The new-conversation selector offers Light (4096 context / 1024 reply), Balanced (8192 / 2048) and Long (16384 / 3072). Context includes prompt, complete history and reserved reply. Reply reserve is part of that total, including thinking tokens when the runtime counts them.

A preset is enabled only when an explicit device snapshot reports an integer `recommendation.budget_ceiling` large enough for that preset and an exact matching candidate with a positive memory estimate and `ESTIMATE_FITS_FREE_VRAM`. The model's advertised maximum is never substituted for the loaded runtime ceiling. Missing evidence disables the preset with a reason. The report keeps model maximum, current runtime context, proven engine ceiling, measured allocation and unverified estimates on separate lines. A fitting estimate is not an allocation test or a guarantee against out-of-memory errors.

Before a snapshot, Advanced/manual remains available with initial values 4096/1024. The existing backend constraints remain authoritative: integer context 128–1048576; integer reply 1–8192 and strictly smaller than context. The UI checks these same bounds without rounding. No preference is persisted. Changing controls or reading specs does not modify any saved conversation's budgets.

Snapshots are keyed to provider, model and selection revision. A different binding cannot reuse their evidence. Reading specs sends the existing selection revision directly, without selecting or loading a model. LM Studio still requires an already loaded model; Ollama still needs the existing explicit loading approval when creating a conversation. If a runtime cannot provide the KV-cache data needed for a memory estimate, presets stay disabled even when its loaded context is known; manual admission remains available subject to server validation.

## Keyboard and draft behavior

Enter submits; Shift+Enter inserts a newline. IME composition events, `isComposing`, key code 229 and repeated keydown events cannot submit. The button and keyboard use the same blank/busy/closed/model-readiness checks, and the controller rejects guarded requests before an API call. The backend continues to enforce runtime binding and admission.

Only a completed request with an unchanged draft clears the composer. Failed/stopped requests, context overflow and newer text typed during inference keep the draft. No inference request is automatically retried or replayed into a new conversation.

## Restricted Markdown and exact text

Model replies support a small dependency-free presentation subset: ATX headings, simple ordered/unordered lists, quotes, fenced code, inline code, `**bold**` and `*emphasis*`. Rendering uses only fixed element names, `createElement`, text nodes and `textContent`; it never parses model content as HTML. Links, images, HTML and entities remain inert text. Literal escape sequences are never decoded. Tables, nested formatting, syntax highlighting, embedded media and general CommonMark compatibility are outside this subset.

Each model reply has a Show raw text / Show Markdown control. The raw paragraph contains the exact reply, including whitespace, Markdown delimiters, entities and literal escapes. Presentation does not change stored text or future prompts. User messages remain plain text. Model/user content is excluded from localization; all added interface text is available in English and Arabic.

## Collection and review visibility

Collection remains off by default and after a server restart. New copy explains that opting in covers only future roles and requires human review; it does not grant training approval. To collect a complete SFT conversation, enable collection before the first turn of a fresh conversation.

When review data reports `context_complete: false`, the review pane displays its `context_warning` above the actions using `textContent`. Training and evaluation checkboxes are unchecked and disabled. Ordinary review remains available. These controls reset for complete or unrelated sources; server restrictions remain authoritative. The backend warning and export refusal also have Arabic translations.

## Verification (2026-11-02)

- Before implementation, four new helper tests failed because the requested behavior did not exist. The added review-warning test separately failed before its renderer was added. A further regression reproduced formatting of backslash-escaped delimiters; opening/closing delimiters preceded by an odd number of backslashes now stay exact literal text.
- `node --test tests/chat-ui.test.cjs tests/i18n-catalog.test.cjs`: 21 passed, zero failed. These cover exact preset values, unknown/actual engine ceilings, missing/insufficient memory estimates, integer boundaries, controller/API guards, IME/repeat decisions, Markdown parsing, literal escapes and escaped delimiters, raw request text, draft retention, review-warning safety/reset and English/Arabic catalog coverage.
- `node tests/chat-enhancements-browser.cjs`: passed with synthetic hardware evidence and disposable conversations. It checks actual keyboard Enter and Shift+Enter; synthetic IME/229/repeat key events; blank/no-session/wrong-model/busy guards; preset gating and snapshot isolation; no selection mutation during specs; safe Markdown DOM, inert HTML/URLs and exact persisted raw text; failure/newer draft retention; Arabic and 390px chat layout.
- `node tests/chat-browser.cjs`: passed with disposable synthetic model engines. The existing privacy, collection, rollover, Stop, Ollama approval and unrelated regression checks remain, with added visible incomplete-context warning and disabled training/evaluation checks. Chat controls are scrolled below the sticky header before real pointer clicks; programmatic draft assignment emits the same input event as typing.
- `node --test tests/review-restrictions-browser.cjs tests/i18n-browser.cjs tests/chat-enhancements-browser.cjs`: 23 passed, zero failed. The review accessibility test checks both existing description IDs by token; the localization test recognizes the intentional keyboard/format names Enter, Shift+Enter, HTML and Markdown. Desktop and 390px screenshots were visually inspected after navigation transitions settled; wrapping and Markdown code remain within their panels.

Chromium checks reuse the already present `puppeteer-core` package under the sibling workspace's `.test-tmp/browser-tools/node_modules` and the installed Chrome executable. No dependencies were installed. The fixture needed permission to open its disposable loopback sockets in this environment; the restricted attempt failed before connecting the fixture. No test reads user chat data or contacts an installed model service. Synthetic keyboard composition events verify guards, but do not replace acceptance with every operating-system IME. Memory estimates and actual GPU capacity were not validated by these frontend tests.
