# Accessibility and keyboard use

The interface aims at keyboard-only use, screen-reader names for every control, and reflow on small screens and at high zoom, in both English and Arabic ([interface language](localization.md)).

## Keyboard

- **Tab** first reaches "Skip to main content", which moves focus past the navigation to the page.
- Navigation items, buttons, links and form controls are native elements: **Enter** or **Space** activates them. The current page is marked with `aria-current="page"`.
- Dialogs (record details, delete confirmation) are modal: focus moves into the dialog, **Tab** stays inside it, **Escape** closes it, and focus returns to the control that opened it.
- Review queue: **Ctrl + Enter** saves an open correction.
- Optional single-key review shortcuts — **1**, **2**, **3** choose a correction type and **4** approves the response — are **off by default** (Settings → Review keyboard shortcuts) because a stray key press, or a speech or switch input, must not approve a review (WCAG 2.1.4). Even when they are on, they never act while a dialog is open or while focus is in a field, button or link. The choice is saved only in this browser.

## Names, focus and structure

- Every focusable control has an accessible name in both languages; filter and sort menus are named for what they filter, not only by their first option.
- Every focusable control shows a visible focus indicator.
- Navigation is grouped (Overview, Chat, Review, Data entry, Datasets, Export, Administration) as labelled groups; icons are hidden from screen readers; collapsed navigation keeps every name.
- The sidebar and the main navigation are distinct landmarks; the main region is named by the page title.
- Errors use `role="alert"` and stay until dismissed; status messages use `role="status"`.

## Reflow and zoom

No page-level horizontal scrolling at 640 CSS px (200% zoom of a 1280 px window) or 320 CSS px (400% zoom), in either language. Wide data tables (manual data, analytics) scroll inside their own panel, which WCAG 1.4.10 allows for data tables.

## Checks

`tests/a11y-browser.cjs` (Chromium, runs in Source checks) verifies, from Chromium's accessibility tree: no unnamed focusable control in any of the 15 views in English and Arabic; a visible focus indicator on every focusable control; skip link; keyboard navigation and `aria-current`; collapsed navigation names; modal dialog focus, Escape and focus return; shortcut safety; and reflow at 640 and 320 px in both languages. `tests/test_ux10_navigation.py` checks the navigation structure. Contrast checks for dark mode are in `tests/chat-browser.cjs` (UX-25).

## Not verified

- Real screen readers (NVDA, JAWS, VoiceOver, TalkBack): the checks use Chromium's accessibility tree, which is what screen readers read, but no spoken output was tested.
- Firefox and Safari/WebKit: only Chromium is available in the test environment.
- Contrast is checked on representative elements, not as a complete audit of every screen and state.
- The Core candidate under `public_source/` has its own interface and is not covered here.
