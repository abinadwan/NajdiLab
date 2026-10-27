# Visual asset provenance register

Date: 2026-10-27. Baseline media at `15c7517`: existing favicon SVG and Arabic-interface JPEG. New assets are introduced by the visual documentation continuation on the same branch; exact introducing commit is available with `git log --diff-filter=A -- <path>`. Hashes below identify the reviewed bytes. No file is licensed by this register. Source ownership/license approval, underlying UI/owner artwork rights and the public-distribution gate remain unresolved.

| Asset/path | Description and source | Creation method / AI-assisted? | Synthetic data | Rights evidence / redistribution status | Editable source / date and revision |
|---|---|---|---|---|---|
| `docs/images/architecture/owner-conceptual-architecture.jpg` | Original owner task attachment; conceptual English/Arabic architecture | Owner-provided JPEG; creation process and AI assistance unknown | No conversation data shown | Attachment receipt and byte-match verified; only orientation/resolution/color-space/dimension EXIF observed, no GPS pointer; underlying icons/trademarks/artwork permissions OWNER_CONFIRMATION_REQUIRED | Original JPEG preserved unchanged; source design unavailable; supplied 2026-10-27 |
| `docs/images/architecture/najdilab-system-architecture.svg` | New source-grounded layers A–G, original simple vector shapes/text | Codex AI-assisted SVG/code design; no icon pack/external artwork | No research data | Creation method VERIFIED; owner must approve distribution/license; no active grant | SVG and sibling `generate_architecture.py`; 2026-10-27 continuation |
| `docs/images/architecture/najdilab-system-architecture-preview.png` | Render of the new SVG | Chromium lossless screenshot; AI-assisted orchestration | No research data | Derived from SVG; same pending distribution status | Primary SVG/generator; 2026-10-27 |
| `docs/images/screenshots/dashboard.png` | Actual dashboard | Chromium/Puppeteer; AI-assisted capture, not generated UI | Three fictional turns | Capture VERIFIED; underlying UI copyright authority pending | Live unmodified baseline app; [reproduction](visual-documentation-verification.md); 2026-10-27 |
| `docs/images/screenshots/conversation-review.png` | Actual review queue | Same real-browser capture | Fictional Arabic prompt/weak answer | Same UI/source rights uncertainty | Baseline app + [user-guide example](user-guide.md); 2026-10-27 |
| `docs/images/screenshots/correction-overlay.png` | Actual correction editor | Same; text entered through real form | Fictional independent correction | Same; not historical reviewer evidence | Baseline app + user guide; 2026-10-27 |
| `docs/images/screenshots/training-data.png` | Actual corrected-record list | Same | One corrected demo; Include demo selected | Same; no built Gold version claimed | Baseline app + user guide; 2026-10-27 |
| `docs/images/screenshots/dataset-health.png` | Actual empty version/quality state | Same | Synthetic-only instance, no versions | Same; no fabricated metrics | Baseline app; 2026-10-27 |
| `docs/images/screenshots/training-setup.png` | Actual unconfigured training form | Same | No weights/runtime | Same; defaults not training recommendations | Baseline app; 2026-10-27 |
| `docs/images/screenshots/human-review.png` | Actual missing-historical-artifacts state | Same | No real evaluation data | Same; no fabricated results | Baseline app; 2026-10-27 |
| `docs/images/english-ui-arabic-record.jpg` | Prior synthetic UI crop | Prior capture record; exact author/tool origin not established | Reported synthetic; visually reviewed | Existing asset unchanged; provenance/ownership confirmation remains | Earlier report in `installation-verification.md`; baseline `15c7517` |
| `static/favicon.svg` | Existing NajdiLab favicon | Repository vector; original authorship/AI assistance unknown | N/A | OWNER_CONFIRMATION_REQUIRED; no copied icon-pack origin established | Existing editable SVG, unchanged baseline `15c7517` |
| README architecture/workflow and architecture.md Mermaid | Existing technical diagram sources | Earlier AI-assisted documentation session | No research records | Source preserved; owner/source license pending | Inline Mermaid blocks unchanged from `15c7517` |
| New gallery Mermaid views | Data flow, verified ER subset, optional training, security | Codex AI-assisted text diagrams | No private records | Creation method known; owner/source license pending | Inline `docs/architecture-diagrams.md`; 2026-10-27 |

No fonts, external logos or icon packs were added to the new SVG. System font names reference locally available fonts; no font file is distributed. Application screenshots necessarily include existing UI symbols and text, whose original authorship must be cleared separately. The owner illustration includes recognizable third-party-style symbols; preserve the supplied artwork but do not infer permission from possession. A public snapshot must either clear these assets or exclude them with owner approval.

## Reviewed image hashes

SHA256 values allow no-loss comparison; they are not ownership evidence. PNGs are lossless browser captures, kept at consistent dimensions without resampling or photo metadata. Regenerating screenshots can change timestamps, antialiasing and pixels; do not silently replace old evidence to force a matching hash.

| Image | SHA256 |
|---|---|
| `docs/images/architecture/najdilab-system-architecture-preview.png` | `338da30c7781e6f165e6f90ba9b9a23512d6b119bbbc0c6341c683504728f530` |
| `docs/images/architecture/najdilab-system-architecture.svg` | `5e7d2706f1b10953eae292653d40e595d471bbdd0792071e7df6d1ee6c90c16f` |
| `docs/images/architecture/owner-conceptual-architecture.jpg` | `dabcb5c9f2041f2827a16d8cd6e8b663d32b80b9054c08931a8a6ce4070820ae` |
| `docs/images/english-ui-arabic-record.jpg` | `d7fabc3a2999ce6e037a354dc241844e6e3935c4dfeca4367afd6e300bbdfedc` |
| `docs/images/screenshots/conversation-review.png` | `f1110492a7396a7deff04c141df7dd4ae44708e7ab7c2b8c8ecb62b9456a9a53` |
| `docs/images/screenshots/correction-overlay.png` | `267977a4c6cfeaffc95378f28729673bf06cbaa1a71bc270fdd978fa204b8b73` |
| `docs/images/screenshots/dashboard.png` | `37cfd0b370852bc62b7963aa6cc3b5d47b3543c157691a7a9f6e01a8f605fbcb` |
| `docs/images/screenshots/dataset-health.png` | `8f927cc2172538dc881dabf506a5130c11ceacdaed13a5ba556f0ac1e2b37763` |
| `docs/images/screenshots/human-review.png` | `0960530d659e3420c8db5398ed050201a5b4f14e3f94e39b4ba5995f4ff47b9f` |
| `docs/images/screenshots/training-data.png` | `d811129e46f9338f72b64ecb89011f5706762f0230eb19e537f94fa3af142c72` |
| `docs/images/screenshots/training-setup.png` | `134fbbff93fce29c54136b5654d2fc40779014ff4700d07a6fcd20097dc92e8d` |
| `static/favicon.svg` | `d4335ecf689ed3d87b88b1e6bd1fe6d66287c346f27bffafc43878c42929bf22` |
