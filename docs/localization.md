# Interface language: Arabic and English

The application interface is available in English (left to right) and Arabic (right to left). Choose the language from the selector in the top bar or under Settings → Interface language. The choice is saved only in this browser (`localStorage` key `najdilab.language`) and is restored on reload. If the browser blocks storage, the interface still works and can be switched; the choice just isn't remembered. English is the default.

The separate Core candidate under `public_source/` has its own interface and is English only.

## How it works

English is the source language of the markup and scripts. `static/localization.js` translates rendered interface text from the catalog in `static/i18n-ar.js`:

- A `MutationObserver` translates text and the `placeholder`, `aria-label`, `title` and `alt` attributes as they are rendered, so dynamic messages, errors, toasts and late-loaded views are covered.
- Each node keeps its English source. Switching language applies at once without reloading, so unsaved drafts are never lost; switching back restores the exact English.
- `exact` entries map a whole English string; `patterns` map text built from values (for example `Showing {a}–{b} of {total}`). Placeholder values are translated when they are themselves catalog entries (such as status words); free text inside them is kept as is.
- Native dialogs (`confirm`) are not part of the page, so their text goes through `NajdiI18n.t()` in code.
- Dates are rendered as `<time datetime>` and re-formatted on a language change. Arabic uses the Gregorian calendar with Latin digits (`ar-SA-u-ca-gregory-nu-latn`) so timestamps and counts read the same in both languages.
- `static/i18n.css` flips the shell, sidebar, mobile menu and the active-item marker for right-to-left. Most layout already uses logical CSS properties.

## What is never translated

User and dataset content is shown exactly as stored. The localizer skips anything inside `dir="auto"`, `bdi`, `code`, `pre`, `textarea`, `kbd`, `samp`, `time`, `[translate="no"]` and `[data-i18n-skip]`. Use these for:

- conversation messages, originals, corrections, notes and other user text — `dir="auto"`;
- identifiers such as dataset version names, file names, model and provider names, session and record ids — `<bdi dir="ltr">` (or `<code>`), so they stay left to right inside Arabic sentences;
- menu options that hold identifiers — `translate="no"`.

Product and format names (NajdiLab, NajdiLab Native, Ollama, LM Studio, Unsloth, Hugging Face, GGUF, SFT, DPO, JSONL, SHA-256, API, GPU) stay in Latin script in both languages.

A server message that is not in the catalog is shown in Arabic as "رسالة الخادم:" followed by the original text isolated left to right, never mixed silently into the Arabic interface.

## Adding or changing interface text

1. Write the English text in the markup or script as usual.
2. Add its Arabic translation to `static/i18n-ar.js`: an `exact` entry, or a `patterns` entry if the text contains values.
3. Put user content and identifiers in one of the skipped containers above.
4. Run the checks below. They fail on missing translations.

Keep Arabic out of the other source files: `tests/test_english_localization.py` allows Arabic only in the catalog (and the language's own name in the selector).

## Checks

- `tests/i18n-catalog.test.cjs` (Node, runs in Source checks): every text in `index.html`, every fixed toast/confirm/status message, every view title, status and error tag has an Arabic translation through the real translation function; patterns keep their placeholders.
- `tests/i18n-browser.cjs` (Chromium, runs in Source checks): the default is English and left to right; choosing Arabic switches language and direction immediately and survives a reload; every view, data state (review workspace and correction editor, conversation detail, data dialog, health, balance, version details, evaluation, export), chat session, toast and error message is free of untranslated English; user messages stay verbatim; the sidebar sits on the right; no view overflows at 390px; the mobile menu opens from the right; switching back restores English; blocked storage keeps the interface usable.

## Known limits

- Server messages are translated where they are listed in the catalog; internal pipeline errors (tokenizer, migration, dataset build) are shown as labelled original text.
- The browser checks prove what Chromium renders. Screen-reader announcements and other browsers have not been tested manually.
- Translations were written for this release and have not been reviewed by a second Arabic speaker.
