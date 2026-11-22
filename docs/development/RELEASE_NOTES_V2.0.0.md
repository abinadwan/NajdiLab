# Najdi Lab V2.0.0 — development candidate

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

> Superseded by [V2.1.0](RELEASE_NOTES_V2.1.0.md) (unified chat composer). Kept as the record of V2.0.0.

**Status:** development candidate on `update-project`, Draft PR #23. V2.0.0 is the owner-approved product version identifier; it is **not** a public release, a production approval or a merge to `main`. Acceptance gates that remain open are listed below.

The version has one source, `app/version.py`. The server banner, the `Server` header, the Hugging Face client's User-Agent and `/api/v1/config` (`app_version`, `app_version_display`, `release_status`) read it; the interface shows it under the Najdi Lab / نجدي لاب name in the sidebar and in Settings → About Najdi Lab. Dataset versions, model files, migration numbers and dependency versions are unrelated and unchanged. `tests/test_version.py` and `tests/models-browser.cjs` check that the source, the API and the interface agree, in Arabic and English, light and dark, expanded and collapsed sidebar and on a phone.

## What V2.0.0 contains

| Area | Summary | Record |
|---|---|---|
| Interface and brand | Najdi Lab identity, design system, framed-sheet shell, Arabic and English, light and dark | [Redesign](NAJDI_LAB_REDESIGN.md), [design system](../design-system.md) |
| Hugging Face Direct | GGUF discovery, Smart Model Advisor, storage-safe verified downloads, model library, approved loading through NajdiLab Native | [Hugging Face Direct](HUGGING_FACE_DIRECT.md) |
| Trending and recommended models | Recommended for your device (Smart Model Advisor ranking) and Hugging Face trending with provenance labels and a 12B total-parameter limit | [Model discovery](MODEL_DISCOVERY.md) |
| Managed llama.cpp runtime | Pinned official llama.cpp build installed only on approval, verified by SHA-256, identity and a GPU probe; rollback and uninstall | [Managed runtime](MANAGED_RUNTIME.md) |
| Chat V2 | Context usage indicator and configurable notices; exact admission unchanged | [Hugging Face Direct §8](HUGGING_FACE_DIRECT.md#8-chat-v2-context-window) |
| Database | Migration 009 (`managed_models`, additive) | [Hugging Face Direct §5](HUGGING_FACE_DIRECT.md#5-storage-safety) |

## Open acceptance gates

- GitHub Actions on the exact final commit (not triggered, as instructed).
- Real-model acceptance is done for two official models on the RTX 5070 (Qwen2.5-0.5B-Instruct Q4_K_M and Gemma 4 E4B QAT Q4_0, all checks PASS: [record](REAL_MODEL_ACCEPTANCE.md)); larger models are not accepted.
- Linux, Vulkan and CUDA 12.x runtime packages: implemented, not tested on real hardware.
- Owner review and approval of PR #23.

## Rollback

`git revert` the V2.0.0 commits on `update-project`; migration 009 is additive and harmless if left in place. See each record's rollback section.
