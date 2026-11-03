# Najdi Lab design system

The interface of Najdi Lab | نجدي لاب: brand, tokens, type, components and the rules that keep
Arabic (RTL) and English (LTR) equal. Implementation: `static/theme.css` (tokens),
`static/najdi.css` (type, shell, components, screens), `static/brand/` (logo files).
Why it looks this way and what changed: [redesign record](development/NAJDI_LAB_REDESIGN.md).

## Brand

### The mark

![Najdi Lab mark](../static/brand/mark.svg)

The mark is the Arabic letter **ن**, the first letter of *نجدي*, drawn as one geometric bowl.
Its dot is a small equilateral triangle: the triangular wall opening of Najdi mud-brick
architecture (the vents in the walls of At-Turaif and old Riyadh houses), which is also the
oldest structural shape. Read together:

- the **bowl** holds things: a dataset, a reviewed corpus kept intact;
- the **triangle** is the one precise, human-placed point above it: the reviewed signal, the
  Gold record, the opening through which a model looks at the data;
- the **tile** is a building block, one unit of a structured whole.

The bowl's tips are cut on a slant so the letter does not read as a magnet or a smile. There is
no robot, brain, circuit or ornament. The triangle reappears in the interface as the workflow
step marker, the pipeline hand-off between stages, and the completed or empty state.

### Files

| File | Use |
| --- | --- |
| `static/brand/mark.svg` | Symbol on light grounds: ink tile, sand bowl, teal dot. |
| `static/brand/mark-dark.svg` | Symbol on dark grounds: sand tile, ink bowl, deep-teal dot. |
| `static/brand/wordmark-en.svg`, `wordmark-en-dark.svg` | **Najdi Lab** in IBM Plex Sans SemiBold, outlined. |
| `static/brand/wordmark-ar.svg`, `wordmark-ar-dark.svg` | **نجدي لاب** in IBM Plex Sans Arabic SemiBold, shaped with HarfBuzz and outlined. |
| `static/brand/logo-en.svg`, `logo-ar.svg` (+ `-dark`) | Lockups. In Arabic the mark sits on the right, at the start of the reading line. |
| `static/favicon.svg` | Favicon. Optically adjusted for 16 px: a thicker bowl and a larger dot. |
| `static/brand/app-icon.svg` | 512 px full-bleed app icon; the symbol sits inside the 80 % safe zone. |
| Inline in `static/index.html` | Compact sidebar logo. The tile, bowl and dot take their colours from tokens, so they follow the theme; the wordmark shown follows the interface language. |

All wordmarks are outlines (no font needed to render them). The text was shaped and outlined
with HarfBuzz (`harfbuzzjs`, MIT) from the bundled OFL fonts; outlining a font's glyphs into a
logo is permitted by the SIL Open Font License.

Clear space around the mark is at least a quarter of its width. Minimum size: 16 px for the
favicon geometry, 20 px for the standard mark.

## Colour

One ground (a Najd limestone frame), one sheet (white), one ink, one accent. Colour goes on data,
status and focus, not on chrome. Every role has a light and a dark value; nothing outside
`theme.css` names a colour.

| Role | Light | Dark | Used for |
| --- | --- | --- | --- |
| `--frame` / `--bg` | `#f3f1ec` | `#0e100f` | Sidebar and top bar (the L-shaped frame) |
| `--surface` | `#ffffff` | `#161918` | The working sheet, panels, inputs |
| `--surface-soft` | `#f8f7f4` | `#1c1f1e` | Wells, user messages, secondary panels |
| `--active` | `#e9e6e0` | `#272b29` | Hover, selected rows, skeletons |
| `--line` / `--rule` / `--control` | `#e4e1db` / `#eeece7` / `#b8b3aa` | `#2a2e2c` / `#222524` / `#5a605d` | Card edges / row rules / control edges |
| `--ink` | `#161a19` | `#eceeed` | Text |
| `--muted` | `#565c5a` | `#a9afac` | Secondary text (≥ 4.5:1 on every surface) |
| `--primary` | `#14201f` (brand ink) | `#eceeed` (inverted) | The one primary action per screen |
| `--accent` | `#136f78` | `#5cc0c6` | Focus, selection, the active tab line, data bars |
| `--brand-sand`, `--brand-teal` | `#efe9df`, `#3fb2b8` | — | The mark only |

### Status

Each status is a pale tint with dark text of the same hue **and a shape**, so it never depends on
colour alone.

| State | Token pair | Shape | Classes |
| --- | --- | --- | --- |
| PASS / ready / connected | `--status-ready-*` | filled circle | `.gate-badge.pass`, `.health-pill.healthy`, `.status-APPROVED`, `.status-ok` |
| WARNING | `--status-warning-*` | triangle | `.gate-badge.pass_with_warnings`, `.health-pill.warning`, `.status-demo` |
| FAIL | `--status-blocked-*` | square | `.health-pill.critical`, `.health-card-status.failed` |
| BLOCKED (a gate that cannot pass yet) | `--status-hold-*` | bar | `.gate-badge.blocked`, `.gate-badge.unavailable`, `[data-state="BLOCKED"]` |
| REVIEW / corrected / locked | `--status-info-*` | diamond | `.status-*_CORRECTION`, `.locked-chip`, `.frozen-badge` |
| PENDING / neutral | `--status-neutral-*` | ring | `.status-PENDING`, `.status-neutral` |

## Type

**IBM Plex Sans** (Latin) and **IBM Plex Sans Arabic** were drawn as one family, with shared
proportions and stroke logic. They are bundled as `woff2` subsets in `static/fonts/` (SIL OFL 1.1,
`static/fonts/OFL.txt`) and joined under one family name, `Najdi Sans`, with `unicode-range`, so
mixed lines (Arabic text with `LM Studio`, `gold-v002`, `SHA-256`) use the right face for each
character. **IBM Plex Mono** (`Najdi Mono`) has one job: identifiers, hashes, file names and code.
No font is loaded from the network (the CSP allows only `'self'`).

| Role | Size | Weight |
| --- | --- | --- |
| Page title (`h1`) | 22 px | 600 |
| Section and panel titles | 16 px | 600 |
| KPI value | 28 px | 400, tabular figures |
| Body, navigation, cells | 14 px | 400 |
| Labels, meta, pills | 12 px | 400–500 |

Arabic: the root size steps from 16 to 17 px and line height from 1.55 to 1.75 (1.9 in chat
replies), because Arabic letterforms sit smaller on the same body size. Arabic is never
letter-spaced or uppercased. Numbers use Latin digits in both languages (`nu-latn`), so counts
and timestamps compare across languages.

## Shape, space and depth

- Radius: 16 px sheet, 10 px panels, 8 px controls, pills fully round.
- One gap of 24 px between blocks; 32 px sheet padding (16 px on phones).
- Nothing at rest has a shadow. Only what floats casts one (`--shadow-float`): dialogs, menus,
  the toast, the phone navigation sheet, the chat list overlay.
- No gradients, glass, glows or emoji.

## Shell

A **framed sheet**: the sidebar and the 56 px top bar share one tinted frame with no line between
them; the work sits on a white sheet inset 8 px from the window's end and bottom edges. In
Arabic the whole frame mirrors (the sidebar moves to the right) through logical properties and
the document direction; no screen has a separate RTL layout.

- **Sidebar** (248 px; 76 px collapsed): the logo, seven workflow groups in sentence case, outline
  icons (16–18 px, 1.6 stroke, `#i-*` sprite in `index.html`), the active item as a white pill with
  a hairline and a teal icon, the review count as a neutral badge, and "Local only" with the
  loopback address at the foot.
- **Top bar**: breadcrumb (workflow group / screen), then language, theme, the local-storage
  status and Refresh.
- **Phone** (≤ 760 px): the sidebar becomes a sheet opened by the menu button (it reports
  `aria-expanded`; Escape and an outside click close it), the language and theme selects collapse
  to their icons, and the sheet becomes the full screen.

## Components

| Component | Rule |
| --- | --- |
| Buttons | 36 px; flat. Primary = brand ink (inverted in dark). Ghost = white with a hairline. Review actions use their status pair. Disabled stays legible and never relies on opacity. |
| Inputs | 36 px, 1 px control edge, teal focus edge plus a 3 px focus ring. Placeholders at 4.5:1. |
| Tabs | Underline tabs on a full-width hairline; the active tab takes a 2 px teal line. |
| KPI strip | One container split by 1 px lines. The column count follows the item count (4 → 4, 10 → 5 + 5) and the last cell fills its row. |
| Tables | 12 px grey sentence-case headers, no header band, no zebra, row rules, tabular figures. Wide tables scroll inside their own labelled, focusable region. |
| Notices | Info (blue), warning (amber), error (red), success (green): a hairline box, never a full-screen banner. |
| Dialogs | 14 px radius, float shadow, dimmed backdrop, a 160 ms fade-and-rise on open. |
| Empty states | Keep the frame and the heading, one sentence, the next action, and the brand triangle in place of an icon badge. |
| Loading | Flat grey bars at the final size; no shimmer. |

## Motion

Feedback only: 140 ms colour and border transitions on hover and focus, a 1 px press on buttons,
the dialog entrance and the phone sheet slide. `prefers-reduced-motion: reduce` removes all of
it. Nothing performs an entrance on load.

## Bidirectional content

- Chrome follows the interface language; content keeps its own direction (`dir="auto"`, `bdi`,
  `unicode-bidi: isolate` / `plaintext`).
- Identifiers, versions, hashes, paths, model names and code are `dir="ltr"` and set in Plex Mono
  inside Arabic text.
- Chevrons and the pipeline triangles point in the reading direction; logical properties
  (`inset-inline-*`, `margin-inline-*`, `border-inline-*`) are used throughout the new layer.
- Breadcrumbs and other text the interface builds are composed from English source strings, so
  the catalog can translate them both ways.
