# Trending models and Recommended for Your Device

| | |
|---|---|
| Branch | `update-project` (Draft PR #23), on top of [Hugging Face Direct](HUGGING_FACE_DIRECT.md) and the [managed llama.cpp runtime](MANAGED_RUNTIME.md). Product version stays **V2.0.0**. |
| Scope | Two discovery modes in **Model library**: *Recommended for your device* (the default tab) and *Trending*. Search, details, downloads, the library and loading are unchanged and stay approval-gated. |
| Code | `app/model_discovery.py` (rules, cache, ranking), `HubClient.list_models` / `relations` / `listing` in `app/hf_hub.py`, routes `hub/trending` and `hub/recommended` in `app/model_service.py`, the two tabs in `static/models.js` and `static/index.html`. |

## 1. Hugging Face data used (checked against live responses, 2026-11-04)

`GET /api/models?filter=gguf&pipeline_tag=text-generation&sort=<trendingScore|downloads|likes|lastModified>&direction=-1&limit=50&expand[]=…` returns, per repository, `trendingScore`, `downloads`, `likes`, `lastModified`, `gguf.total` (total parameters from Hugging Face's own GGUF parser), `gguf.architecture`, `cardData.license`, `tags` with `base_model:<relation>:<repo>` (relations `quantized`, `finetune`, `merge`, `adapter`), `siblings` (file names) and `gated`. Pages continue through the `Link: <…cursor=…>; rel="next"` header; the cursor is validated and only ever sent back to `huggingface.co/api/models`. Rate limits come as HTTP 429 with a `RateLimit` header (`t=` seconds), reported as `RATE_LIMITED` with a retry hint. `GET /api/models/<repo>?expand[]=tags` gives a base model's own declared origin. Organisation "verified" flags are **not** used: they are not set even for large original publishers (for example `Qwen` reports `isVerified: false`).

## 2. Rules

| Topic | Rule |
|---|---|
| Ranking | Hugging Face's order for the chosen sort, with its numbers as reported and the time they were fetched. NajdiLab removes entries; it never re-orders or scores them. Ranks shown are positions on Hugging Face (`#3` = third entry it returned). |
| Size | Total parameters from `gguf.total`. Filters: up to 12B (default), up to 3B, above 3B through 7B, above 7B through 12B; 12.0 B is the limit (a 12.2 B model is excluded). A mixture of experts counts all experts (`30B-A3B` is 30 B, never 3 B). |
| Unknown or contradicted size | No count, or a count the repository name contradicts by more than 1.6× (active `A3B` and effective `E4B` sizes in names are ignored), is **UNVERIFIED**: hidden by default, shown only with *Include models whose parameter count is unknown*, labelled *UNVERIFIED size*, never placed in a size bucket and never recommended. |
| Purpose | Instruct / chat (default) = Hugging Face's `conversational` tag or *instruct / chat / it* in the name; *Any purpose* includes base models. |
| Format | GGUF repositories with at least one single, top-level GGUF file (split sets and vision projectors do not count). |
| Provenance | **Verified official publisher**: the GGUF is published by the same Hugging Face account as the base model it declares as `quantized` (Hugging Face only lets an account's members publish under its name), and that base model's own declared origin, followed up to three steps, never leads to another account. It is still labelled a GGUF conversion, not the original weights. **Community conversion**: a declared `quantized` copy by another account whose name contains the original's name. **Fine-tuned / modified**: a declared `finetune`, `merge` or `adapter`; a base that is itself derived from another account's model; or a name that says it was changed: *uncensored, abliterated, heretic, decensored, roleplay* always; *merge, fine-tune, DPO, SFT, LoRA, distill* when the original's name does not. **Unverified source**: no declared origin, no stated relation, a name that does not match the claimed original, or an origin that could not be checked. |
| Duplicates | Copies of the same original are grouped (before the source filter); the best-sourced one is shown at its own Hugging Face position with *Also converted by …*. Modified and unverified copies are never merged with the original. |
| License | *Open license* (Apache-2.0, MIT, BSD, CC-BY…), *Custom terms: read them before use* (for example Llama, Gemma, `other`), *Non-commercial use only*, *No license stated*. Shown, used as a ranking factor, never a reason to hide. |

## 3. Recommended for Your Device

Needs the hardware-read approval (memory, GPU and runtime are read locally and never sent). Steps:

1. **Pool (popularity only chooses what is checked):** Hugging Face's three most-downloaded pages and first trending page, filtered and de-duplicated as above; the first 10 matches.
2. For each: pinned details (file sizes and SHA-256), one bounded header read of one file (layer sizes are the same for every quantization), then the **Smart Model Advisor** for every supported file at the chosen context and GPU setting, with the storage preflight for that file.
3. **Suggested file:** best verdict, then download allowed, then GPU placement, then quality (higher bits up to 8-bit; full precision is not preferred).
4. **Order:** compatibility (COMPATIBLE, LIMITED, UNVERIFIED, BLOCKED) → download allowed → provenance → license → where it would run → larger total size. Popularity is not a factor.

Each card shows **Compatibility (estimate)** (the Advisor's verdict and reasons) separately from **Expected performance** (where it would run: fully on the GPU, split, CPU). Neither is a load test or a benchmark. Without a llama.cpp runtime every model is BLOCKED with `NATIVE_SERVER_MISSING`, which the card explains.

## 4. Caching, failures, privacy

List pages are cached for 10 minutes (*Refresh from Hugging Face* bypasses it); if a refresh fails (network or rate limit) a ranking up to an hour old is shown, marked *Hugging Face could not be reached; this is the last ranking fetched*. Base-model origins are cached for 6 hours; a failed check leaves the copy UNVERIFIED rather than official. Repository details are cached for 10 minutes. Opening a tab sends nothing: every request follows a button press. Only list, details and header requests go to Hugging Face; hardware facts never leave the computer. Downloads and loading keep their existing approvals.

## 5. Tests

`tests/test_model_discovery.py` (synthetic catalogue in `tests/fake_hub.py`: official, community, modified, misleading name, finetune lineage, mixture of experts above 12B, over 12B, unknown size, base model, custom license): name sizes and MoE, unknown/contradicted counts, size buckets and the 12B edge, official vs. look-alike accounts, lineage, modified detection, order kept, duplicates, trending sorts, default filters, pagination with cursor and continuing ranks, cache and stale fallback on rate limit, hostile list entries, recommendations needing approval, ranking by fit (GPU memory, disk, runtime), route validation. `tests/i18n-models.test.cjs` covers every new text and evidence sentence in Arabic with names and numbers kept; `tests/models-browser.cjs` covers the default tab, the approval, both modes, labels, phone width and Arabic RTL.

## 6. Results (2026-11-04)

| Check | Result |
|---|---|
| Live Trending (official, chat, ≤12B) | 2 pages (100 entries) read: 63 above 12B, 4 unknown size, 3 not chat, 3 duplicates merged. LiquidAI's and XHToken's own GGUF repositories were confirmed official through their base models' lineage; NVIDIA's Nemotron Bolt (a fine-tune of `google/gemma-4-E4B-it`), *Uncensored* / *Abliterated* copies and a *Distill* fine-tune were labelled **Fine-tuned / modified**; two *composer* repositories whose names do not match the model they claim to convert were labelled **Unverified source**. 4.5 s including lineage checks. |
| Live Recommended (RTX 5070, 10.8 GB GPU free, managed CUDA runtime, context 8192) | 10 official models checked, all COMPATIBLE fully on the GPU; order Qwen3-8B (Q6_K, 9.7 GB estimated), Qwen2.5-7B-Instruct (Q3_K_M: its larger quantizations are split files), Qwen2.5-Coder-7B-Instruct (Q8_0, 10.4 GB), …, Qwen2.5-0.5B-Instruct; models with custom license terms after open-licensed ones. 26 s for up to 12B, 10 s for up to 3B (details and header reads run four at a time). Nothing was downloaded. |
| Automated (development checkout) | `tests/test_model_discovery.py` 35 passed; full Python suite 886 passed, 38 skipped, 0 failed; Node 62; models-browser 15; i18n-browser 10; a11y-browser 13; UX audit 236 states, 0 axe violations, 0 overflow; review-restrictions 12; chat-browser and chat-enhancements PASS; public-source builder 12; docs and API inventory PASS. |
| Fixed during the work | Duplicates are grouped before the source filter (an official entry still names the community copies it hides); official claims now need the base model's lineage (live data showed same-account GGUFs of fine-tunes of other publishers' models); a community copy must carry the original's name; names that say safety training was removed (*uncensored, abliterated, heretic…*) now always mean **modified**, because the installed-copy check showed two such repositories passing as official when their same-account base declared no origin; the *Refresh* and *Load more* buttons ignored `hidden` because of the button display rule; `api()` now passes the error code and retry hint to the interface. |

## 7. Limitations

- Provenance relies on what repositories declare plus account ownership; a repository that declares a false `quantized` relation and keeps the original's name cannot be told apart from an honest conversion without downloading and comparing weights (not done).
- Hugging Face's `gguf.total` can be incomplete for split-only repositories; those have no single-file GGUF and are left out anyway.
- Purpose detection uses Hugging Face's tag and the name; some chat models without either are listed only under *Any purpose*.
- Recommendations check at most 10 models per request; widen the filters or use Trending and Search for more.

## 8. Rollback

`git revert` the commit that adds this feature; no migration or stored data is involved. Search, downloads, the library and the runtime keep working without it.
