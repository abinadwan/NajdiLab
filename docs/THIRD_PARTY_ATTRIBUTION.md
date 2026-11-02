# Third-party attribution — Chat Experience V2 and NajdiLab Native

Scope: every external project consulted or used for branch `feature/chat-experience-v2`. The broader, older register is [third-party-attributions.md](third-party-attributions.md); the detailed dependency evidence remains [dependency-licensing-matrix.md](dependency-licensing-matrix.md). This file is a review record, **not** a NOTICE file or a license grant.

**Summary.** No third-party source code, images, icons, fonts or other assets were copied into NajdiLab in this branch. No new Python or JavaScript dependency was added. The Markdown renderer, the GGUF header reader, the streaming parsers and the chat UI are original NajdiLab code. llama.cpp is used as a **separately installed external program** that the owner supplies; NajdiLab does not bundle, build or download it.

License texts below were read on 2026-11-02 from a shallow clone of each repository at the listed commit (file `LICENSE`), not from memory or a third-party summary.

## 1. llama.cpp (`llama-server`)

| Field | Record |
|---|---|
| Repository | https://github.com/ggml-org/llama.cpp |
| Version used for testing | tag `b12059`, commit `1b6935b227b9f9aa89deea8016c0e208f547446f` (server reports `b1-1b6935b`) |
| Type of use | **External tool.** NajdiLab starts the owner's own `llama-server` binary as a child process and talks to its documented HTTP API (`/health`, `/props`, `/apply-template`, `/tokenize`, `/v1/chat/completions`). Command-line flags are taken from `llama-server --help` of that build. |
| Local files affected | `app/native_runtime.py` (process management and API client), `app/gguf.py` (independent GGUF header reader, written from the public format description; no llama.cpp/ggml code copied) |
| License | MIT License — https://github.com/ggml-org/llama.cpp/blob/master/LICENSE |
| Copyright holder | "Copyright (c) 2023-2026 The ggml authors" |
| Modifications to their code | None. No llama.cpp code is in this repository. |
| Obligations and how they are met | MIT obligations apply when copies or substantial portions are **distributed**. NajdiLab distributes none, so there is no current obligation. The test binary was built from source in a temporary scratch directory on the build machine, used only for tests, and not committed. |
| Files required if distributed later | If a future release bundles `llama-server`, ship llama.cpp's `LICENSE` and every license in its `licenses/` folder for the exact build (this revision contains `licenses/LICENSE-jsonhpp`, the nlohmann/json MIT license), plus the licenses of any GPU runtime bundled with that build (for example NVIDIA CUDA redistributables, whose EULA must be checked separately). |
| Open questions | A CUDA build for RTX 5070 has its own NVIDIA component terms, not reviewed here. |

## 2. Model weights (any GGUF file)

Model weights are **not** covered by llama.cpp's MIT license or by NajdiLab's license. Each model file has its own terms (for example Gemma terms of use, Llama community licenses, Apache-2.0, etc.). NajdiLab shows the `general.license` metadata when a file declares it, but that field is self-reported by the file and is **not** verification. NajdiLab never downloads weights. Owner action: confirm each model's license before use or redistribution, and before using its outputs for training data. Tests use only a random-weight synthetic GGUF that NajdiLab generates (`tests/ollama_disposable.py`), so no third-party weights were used.

## 3. UX references that were studied, not copied

The task listed these as study references. For each, **no code, markup, styles, icons, images or text was copied**. The chat layout (collapsible sidebar, date-grouped history, pinned items, a collapsible "thinking" panel, Enter-to-send) uses common chat-application conventions and was implemented independently.

| Project | Commit read | License (as read) | Copyright | Use | Notes / risk |
|---|---|---|---|---|---|
| [Open WebUI](https://github.com/open-webui/open-webui) | `f7ac7ee10962ddec0017f5c29b6740d9b9c5faca` | **"Open WebUI License"**: BSD-3-Clause-style terms plus clause 4, which prohibits altering or removing "Open WebUI" branding in most deployments, and a CLA for contributors. Not an OSI-standard license. | "Copyright (c) 2023- Open WebUI Inc." | None (license read only) | Because of the branding clause, **do not copy any Open WebUI code or assets into NajdiLab**. Materials under earlier licenses are governed by its `LICENSE_HISTORY` (not reviewed). |
| [LibreChat](https://github.com/danny-avila/LibreChat) | `f4154b649efa37e1345ccc517a4d8d1ed2178c82` | MIT | "Copyright (c) 2026 LibreChat" | None (license read only) | Copying would require keeping the MIT notice; nothing was copied. |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) | `a4dcbb5b9155cd7220e383c67a0613197d4d963d` | MIT | "Copyright (c) 2026 AgentbaseAI Inc." | None (license read only) | Same as above. |

## 4. Engines NajdiLab talks to (unchanged relationship)

| Project | Use in this branch | Notes |
|---|---|---|
| [Ollama](https://github.com/ollama/ollama) | Streaming now uses Ollama's documented NDJSON `/api/chat` stream (`stream: true`). Still an optional, separately installed external service. | Same version gate (0.40.13) as before. License evidence unchanged from the existing register. |
| LM Studio SDK `lmstudio==1.5.0` | Same pinned optional dependency; streaming uses the SDK's existing fragment stream. | No version change; existing open review of exact-artifact/transitive notices still applies. |

## 5. Dependency review for this branch

- **Python:** no new runtime packages. Test tools unchanged (`pytest==9.1.1`).
- **JavaScript:** no new packages. Browser tests use the Chromium/Playwright already installed on the test machine, or `puppeteer-core` as in the existing CI workflow; neither is shipped.
- **Transitive dependencies:** none added, so nothing new to review. Existing open items in the dependency matrix are unchanged.

## 6. Remaining items needing a license decision

1. Before ever **bundling** `llama-server`: collect the exact build's license files (llama.cpp MIT, `licenses/*`, and any CUDA/Vulkan/Metal runtime terms) and add them to a NOTICE bundle.
2. Each model file used with NajdiLab Native: the owner must verify its license independently.
3. Open WebUI: keep it as a "no copying" reference because of its branding clause.
