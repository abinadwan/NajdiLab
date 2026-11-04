# Hugging Face Direct, Smart Model Advisor and context safety

| | |
|---|---|
| Branch | `update-project` (Draft PR #23). Started from `fcaac6f`. |
| Scope | Discover → evaluate → download → verify → approve load → chat, for **single-file GGUF** models only, plus a context-usage indicator in Chat V2. |
| Status | Implemented and tested with a synthetic hub and synthetic GGUF. Real-model loading, real GPU and GitHub CI acceptance are **not** done (see [Acceptance](#12-acceptance)). |
| Discovery modes | *Recommended for your device* and *Trending*: [MODEL_DISCOVERY.md](MODEL_DISCOVERY.md). |
| Code | `app/hf_hub.py`, `app/model_store.py`, `app/model_advisor.py`, `app/model_service.py`, `migrations/009_managed_models.sql`, `static/models.js`, the context indicator in `static/chat.js`; small hooks in `app/server.py`, `app/native_runtime.py`, `app/gguf.py`. |

## 1. Audit of the starting point (2026-11-03)

| Component | Actually operational? | Notes |
|---|---|---|
| Chat V2 (`app/chat_workspace.py`, `static/chat.js`) | Yes | Exact admission: the engine's own template and tokenizer count every prompt; `input + reply reserve > budget` closes the session as read-only `CONTEXT_LIMIT` and creates an empty successor with collection off; the draft is kept; a prompt that does not grow is refused (`CONTEXT_SHRANK`); only complete, verified replies are committed. |
| NajdiLab Native (`app/native_runtime.py`) | Yes (CPU + synthetic GGUF in tests) | Starts the owner's own `llama-server` on 127.0.0.1 with a random key, `--offline`, no web UI; lists GGUF files under `data/models` (or `NAJDILAB_NATIVE_MODELS`), rejects split files, symlink escapes and non-text models; identity = SHA-256 + size/mtime/file id. |
| GGUF reader (`app/gguf.py`) | Yes | Bounded header reader; metadata only. |
| Hardware snapshot (`app/hardware.py`) | Yes | Approval-gated, read-only: RAM via the OS, NVIDIA VRAM via `nvidia-smi`; memory estimates labelled as unverified estimates. |
| Ollama / LM Studio integrations | Yes | Unchanged by this work. |
| Hugging Face Direct | **No** | A static "Planned — not available" card in Settings. No code. |
| Training, deployment, model registry | **No** | Removed earlier; training stays external (Unsloth handoff). Not restored. |

## 2. Hugging Face API contracts (verified against live responses, metadata only)

| Need | Documented endpoint | Verified fields |
|---|---|---|
| Search | `GET /api/models?search=&author=&filter=gguf&limit=&sort=downloads&direction=-1` | list of `{id, author?, downloads, likes, tags[], pipeline_tag, createdAt}`; license appears as a `license:*` tag |
| Details, pinned | `GET /api/models/{repo}?blobs=true` and `GET /api/models/{repo}/revision/{sha}?blobs=true` | `sha` (40-hex commit), `gated` (`false`/`"auto"`/`"manual"`), `private`, `disabled`, `cardData.license`, `gguf.{total, architecture, context_length}`, `siblings[].{rfilename, size, lfs.{sha256,size}}` |
| Download | `GET /{repo}/resolve/{sha}/{file}` | `302` to an `*.hf.co` CDN; `X-Repo-Commit`, `X-Linked-Size`, `X-Linked-ETag` (= LFS SHA-256); the CDN honours `Range` (`206`) |
| Errors | — | private, gated (unauthenticated) and missing repositories answer `401`; rate limit headers `RateLimit: "api";r=…;t=…` and `RateLimit-Policy: q=500;w=300` |

Nothing else (no `huggingface_hub` package, no tokens, no undocumented endpoints) is used.

## 3. Plan

1. `app/hf_hub.py` — HTTPS-only client with a host allowlist checked on every redirect hop, response-size caps, no credentials, no cookies; search, pinned details, bounded remote GGUF header read (`Range`), pinned download stream.
2. `app/model_store.py` — managed folder `<Native models>/huggingface/`, storage preflight per volume, a reservation ledger shared by concurrent downloads, live free-space monitoring, `.part` + sidecar + atomic rename, SHA-256 verification, pause/resume/cancel, recheck, confirmed deletion; registry table (migration 009).
3. `app/model_advisor.py` — COMPATIBLE / LIMITED / UNVERIFIED / BLOCKED with reasons and evidence, separating download eligibility, load eligibility and performance expectation.
4. Native gate — a managed file must be `READY` (verified) before NajdiLab Native will start it; loading stays an explicit, approved action in the existing Native panel.
5. Chat V2 — context usage indicator from the authoritative admission numbers, 70/85/95 % configurable notices, a clearer context-limit panel. Backend admission unchanged.
6. UI — one new destination, **Model library**, in the Chat group; Settings links to it; Arabic and English.
7. Tests with a fake hub transport, fake disk, synthetic GGUF; browser and accessibility runs on the synthetic fixture.

## 4. Risks and how they are handled

| Risk | Handling |
|---|---|
| Disk exhaustion | Preflight on the destination's own volume with a safety reserve (larger on the system volume); reservations for all active downloads; free space re-measured during the transfer; automatic safe pause; never deletes anything to make room. |
| Hostile or changed repository | Revision pinned to a 40-hex commit; size and SHA-256 from LFS metadata re-checked against the CDN headers and the bytes; no repository code, configs or Python files are ever downloaded; GGUF only. |
| SSRF / redirects | HTTPS only; hosts limited to `huggingface.co`, `*.huggingface.co`, `*.hf.co`; every hop re-validated; at most 3 redirects; no user-supplied URLs. |
| Path traversal / symlinks | Repo ids and file names validated by strict patterns; destination resolved and required to stay inside the managed root; symlinked or junctioned parents refused. |
| False confidence | Every number is labelled measured, reported or estimate; missing evidence yields UNVERIFIED, never COMPATIBLE. |
| Privacy | Chat text, datasets and hardware never leave the computer; requests carry only the search terms or repository id. |
| Gated or licensed models | Gated repositories are BLOCKED (no token support in this phase); license acknowledgement is a separate explicit action from the download approval. |
| Runtime damage | No automatic loading; Native start stays explicit, checks integrity, binds 127.0.0.1; Ollama and LM Studio untouched. |
| Context integrity | Existing exact admission and `CONTEXT_LIMIT` transition kept; the indicator only reads authoritative numbers; no summarisation or truncation. |

## 5. Storage safety

**Where files go.** `<NajdiLab Native models folder>/huggingface/<owner>--<name>/<first 12 of commit>/<file>.gguf`. The Native models folder is `data/models` unless `NAJDILAB_NATIVE_MODELS` is set. Nothing outside `huggingface/` is listed, changed or deleted by the model library; Ollama and LM Studio folders are never read.

**Preflight (before any byte is written)**, on the volume that holds the destination (the nearest existing parent is measured with `shutil.disk_usage`):

```
to_write   = file size − bytes already in a matching .part (resume)
temporary  = to_write + 64 KiB sidecar          # the .part file next to the final file
reserve    = NAJDILAB_DOWNLOAD_RESERVE_GIB (default 2 GiB)
             or, on the operating-system volume, max(that, NAJDILAB_SYSTEM_RESERVE_GIB, default 10 GiB)
others     = bytes still to write by other active downloads on the same volume
required   = to_write + 64 KiB + reserve + others
ALLOWED only if free_now ≥ required
```

There is no "twice the file size" rule: the `.part` file is written beside the final path on the same volume, and finalising is an atomic `os.replace`, so at no moment do two copies exist. The interface shows every term of this sum, the free space after the download, and whether the drive is the system drive.

**During the download.** Free space is measured again at the start and every 32 MiB; if `free − remaining − others < reserve` the download pauses (`STORAGE_RESERVE`) before the reserve is touched. A disk-full error from the OS (`ENOSPC`, Windows error 112) also pauses (`DISK_FULL`). At most two downloads run at once and share the same reservation ledger. Network interruptions pause with the verified prefix kept (`HUB_UNREACHABLE`). NajdiLab never deletes anything to make room.

**Integrity before READY.** Revision pinned to a 40-hex commit; the first response hop must report the same commit, size (`X-Linked-Size`) and SHA-256 (`X-Linked-ETag`) as the reviewed metadata; ranges are checked against `Content-Range`; the SHA-256 is computed over every byte (a resumed prefix is re-hashed); size and digest must equal the published values, otherwise the partial file is removed and the entry shows `ERROR`. A matching file whose GGUF header is unreadable, not a text model or without a context length is `UNVERIFIED` and cannot be started. Recheck recomputes the digest on demand.

**Resume.** A `.part` is resumed only if its sidecar names exactly the same repository, revision, file, size and digest; otherwise it is discarded and the download starts over. A restart of NajdiLab turns a running download into `PAUSED` (`INTERRUPTED`).

## 6. Smart Model Advisor

Three answers are kept apart:

1. **Download** — `ALLOWED` unless the repository is gated/private/disabled, the file is unsupported (split, vision projector, sub-folder, unsafe name, size or SHA-256 not published), or the storage preflight fails.
2. **Load** — for one context size and GPU setting:
   - **BLOCKED**: not downloadable for a non-space reason; not a text model; context above the model maximum; no `llama-server` configured; the estimate exceeds all RAM and VRAM together; or it does not fit the memory free now (or "all layers on GPU" cannot fit).
   - **UNVERIFIED**: hardware not read, header unreadable, architecture or KV layer sizes unknown, file size unknown, RAM unmeasurable.
   - **LIMITED**: fits only with partial GPU offload, only on the CPU, or the `llama-server` build reports no GPU.
   - **COMPATIBLE**: the estimate fits the free VRAM of a GPU the runtime can use, with every layer on the GPU.
3. **Performance** — GPU / split GPU+CPU / CPU, as a plain expectation.

Estimate (shared with Chat presets, `app/hardware.py`): `(weights + KV-per-token × context) × 1.15 + 512 MiB`, with KV per token an upper bound from the GGUF header (`layers × KV heads × (key + value length) × 2 bytes`). The header is read **before** download from the file's first bytes (bounded `Range` reads of 1, 8 and at most 32 MiB). Every figure is tagged measured (this computer now), reported (Hugging Face or the header), estimate or unknown. The advisor also reports the largest context that fits fully on the GPU and the largest that fits at all. Hardware is read only when the user ticks the box, through the existing approved snapshot, and never leaves the computer.

## 7. Running a downloaded model

Downloaded files appear in NajdiLab Native's existing model list (`huggingface/...`). NajdiLab Native refuses to start a file inside the managed folder unless its library entry is `READY` (`MODEL_NOT_VERIFIED`); files placed there by hand are refused too. Loading is a separate, explicit step: "Check fit and load…" runs the advisor on the local header, offers the load only for COMPATIBLE or LIMITED, and needs a ticked approval before calling the existing `/api/v1/native/start`. Nothing starts after a download. Native's own controls are unchanged: its own `llama-server` only, 127.0.0.1 with a random key, `--offline`, exact admission, SHA-256 identity, stop only what it started. Ollama and LM Studio are untouched. A model in use cannot be deleted (`MODEL_IN_USE`).

## 8. Chat V2 context window

Unchanged and preserved: exact admission with the engine's own template and tokenizer; no truncation, dropping or summarisation; `CONTEXT_SHRANK` refusal; the audited `CONTEXT_LIMIT` transition (old session read-only and saved, a new empty session with collection off, the draft kept); no partial reply is ever saved or collected.

Added:

- **Indicator** under the composer: a `<meter>` and "Context used: *history* + *reserve* reserved of *budget* tokens (*n* %)". History is the last saved prompt plus its reply, both counted by the engine (measured). "Left for the next message" excludes the new message's few template tokens, so it is labelled an estimate; during a turn the admitted prompt is shown as measured.
- **Notices** at 70 / 85 / 95 % (Settings → Chat context warnings; whole numbers 1–99, strictly increasing; saved in this browser). Each level is announced once per conversation through a polite live region, never on every token. They never permit exceeding the budget: the server still decides admission exactly.
- **Limit panel**: after a `CONTEXT_LIMIT` rollover the new chat shows the exact counts that did not fit and a button to open the previous conversation read-only. The user is told, not silently moved.
- **Failure categories** in front of the engine's message: Reply reserve reached / The runtime did not finish the reply / Context capacity / Runtime error / Cancelled.
- **Deferred**: the user-reviewed "continue in a new chat with a summary" handoff (§8.4 of the request). Carrying context between chats needs its own consent and data-classification design so a summary can never be mistaken for verbatim history or become training-eligible; it is not implemented in this phase.

## 9. Interface

One new navigation destination, **Model library** (Chat group), with two tabs: *Discover on Hugging Face* (search → repository details pinned to a revision → GGUF file table with support reasons → advisor result with the storage preflight → download dialog with a separate license acknowledgement and start button) and *Downloads and library* (managed folder and drive, progress with speed and time left, pause/resume/cancel, recheck, delete with the exact file name typed, check-and-load). Settings → Integrations' former "Planned" card now opens the library. All new text exists in Arabic and English (catalog tests enforce it), layouts mirror for RTL, numbers and identifiers stay left-to-right, status uses the design system's colour-plus-shape vocabulary (COMPATIBLE = circle, LIMITED = triangle, UNVERIFIED = ring, BLOCKED = bar).

## 10. Security boundaries

| Threat | Control | Test |
|---|---|---|
| SSRF, hostile redirects | HTTPS only; host allowlist `huggingface.co`, `*.huggingface.co`, `*.hf.co`; port 443; no userinfo; each hop re-checked; ≤ 3 redirects; no user-supplied URLs | `test_only_https_huggingface_hosts_are_fetched`, `test_redirect_to_a_foreign_host_is_refused` |
| Oversized / hostile metadata | JSON ≤ 4 MiB; ids, revisions and names matched by strict patterns; strings length-capped; malformed entries dropped; UI inserts text only (no HTML) | `test_search_filters_gguf_…`, `test_invalid_metadata_is_never_offered` |
| Path traversal, symlinks | names validated; destination must resolve inside the managed root; linked parents refused; deletion only of library entries inside the root | `test_invalid_paths_…`, `test_symlinked_managed_folder_is_refused`*, `test_delete_needs_exact_confirmation_…` |
| Disk exhaustion | §5 | `test_preflight_…`, `test_insufficient_space_…`, `test_space_shrinking_…`, `test_disk_full_…`, `test_concurrent_downloads_…` |
| Corrupt / changed files | pinned revision, size and SHA-256 checks, header check; recheck | `test_corrupted_or_wrong_digest_…`, `test_recheck_detects_tampering`, `test_changed_or_invalid_revision_is_refused` |
| Code execution | only `.gguf` files are fetched; no repository code, configs or packages; no `trust_remote_code` | by construction |
| Credentials | none sent or stored; gated repositories are blocked, not bypassed | `assert 'authorization' not in headers` in the fake hub; `test_gated_repository_…` |
| CSRF / cross-site triggering | every model operation is a POST behind the existing session token and Origin/Host checks | `test_routes_need_the_csrf_token_…` |
| Unapproved resource use | license acknowledgement and download approval are separate; resume needs approval; nothing loads after download; Native refuses unverified managed files | `test_download_requires_…`, `test_native_refuses_unverified_managed_files_…`, browser test |
| Privacy | only search words or repository ids go to Hugging Face; hardware stays local | by construction; fake hub records every request |

\* skipped on Windows accounts without symlink permission.

## 11. Tests

New: `tests/test_hf_direct.py` (42 + 1 skipped on Windows), `tests/fake_hub.py` (synthetic Hugging Face), `tests/chat-context.test.cjs` (8), `tests/i18n-models.test.cjs` (3), `tests/models-browser.cjs` (10 browser checks). Updated: `tests/chat_browser_fixture.py` (fake hub, isolated models folder, synthetic hardware), `tests/test_ux10_navigation.py` (16 destinations), `tests/ux-audit.cjs`, `tests/a11y-browser.cjs`, `tests/i18n-browser.cjs` (Model library added). Final run on the committed source (Windows 11, Python 3.12.10 in a virtual environment with the optional `lmstudio` SDK, Node 26.10.0, Chrome):

| Suite | Result |
|---|---|
| `pytest tests` | **818 passed, 37 skipped, 0 failed** — skips: 22 private historical artifacts not distributed, 9 opt-in real-Ollama tests, 3 need a real `llama-server` (`NAJDILAB_NATIVE_TEST_SERVER`), 3 need symlink permission on this Windows account |
| `public_source/tests/test_builder.py` | 12 passed |
| `node --test tests/*.test.cjs` | 60 passed |
| `a11y-browser.cjs` / `i18n-browser.cjs` / `review-restrictions-browser.cjs` | 13 / 10 / 12 passed |
| `chat-browser.cjs`, `chat-enhancements-browser.cjs` | PASS |
| `models-browser.cjs` (Model library, context indicator, V2.0.0 label) | 11 passed |
| `ux-audit.cjs` (axe WCAG 2 A/AA, 236 states incl. 200 % / 400 % zoom, light/dark, Arabic/English) | 0 violations, 0 overflowing states |

### Issues found during acceptance and fixed

| Issue | Root cause | Fix | Regression test |
|---|---|---|---|
| `test_every_node_unit_test_runs_in_source_checks` | New Node tests were not listed in `.github/workflows/checks.yml` | Listed `chat-context.test.cjs`, `i18n-models.test.cjs` | the same test |
| Two migration inventory tests | Migration 009 was not in the reviewed inventory / latest-migration pin | Added 009 to `docs/cleanup-inventory.json`; latest migration now `009_managed_models.sql` | the same tests |
| `chat-browser.cjs` timeout (`ENGINE_BUSY`) | The preset check held the runtime's chat lease while taking the host snapshot (`nvidia-smi`, about a second on Windows), so Start right after a check was refused | Lease covers only `engine.limits()`; the snapshot runs after release (reviewed pin of `chat_workspace.py` updated) | `test_host_snapshot_runs_after_the_runtime_lease_is_released` (fails without the fix) |
| `i18n-browser.cjs` untranslated text | A generic Arabic pattern `{a} of {b}` captured the context sentence first; example placeholders and format names counted as English | Specific patterns first; GGUF, `huggingface.co` and the product name "Native" declared as Latin names; example placeholders marked `translate="no"` | `i18n-models.test.cjs` now asserts the exact Arabic |
| `a11y-browser.cjs` destination count | The Model library adds a 16th destination | Expected count 16 | the same test |
| `models-browser.cjs` delete step (under load) | A finished row was reported `active` in the instant between writing READY and removing the job, hiding Delete and keeping the page polling | `active` only while the row is `DOWNLOADING` | `test_finished_row_is_never_reported_active` (fails without the fix) |
| Hard-coded `NajdiLab/1.1` in the Hugging Face User-Agent | Missed by the version change | Reads `app/version.py` | `test_no_other_product_version_is_hard_coded` |

## 12. Acceptance

| Gate | Status |
|---|---|
| Synthetic hub, synthetic GGUF, isolated folders (Windows 11) | PASS (see §11) |
| Live Hugging Face metadata contracts | Verified on 2026-11-03 (search, pinned details, header range read, redirect headers, gated and missing repositories) |
| Downloading a real model | NOT TESTED by design (no large downloads in verification) |
| Loading a downloaded model in NajdiLab Native with a real `llama-server` and the RTX 5070 | NOT TESTED: no `llama-server` is configured on the test installation; the advisor correctly reports BLOCKED |
| GitHub Actions (Windows, Ubuntu, Core) | NOT RUN (Actions not triggered, as instructed) |

## 13. Limitations

- GGUF only; split GGUF, vision projectors, files in sub-folders and other formats are refused with a reason.
- Gated and private repositories are blocked; no Hugging Face token support.
- Memory estimates are estimates (upper-bound KV, fixed headroom); free memory changes while other programs run.
- AMD/Intel GPU memory is not measured (only NVIDIA through `nvidia-smi`), so those machines get LIMITED (CPU) or UNVERIFIED rather than COMPATIBLE.
- The context-handoff summary flow is deferred (§8).

## 14. Rollback

All changes are in commits on `update-project`; `git revert <sha>` restores the previous behaviour. Migration 009 only adds the `managed_models` table; after a revert the table is ignored (it is additive). Downloaded files stay in `data/models/huggingface/` until deleted from the library or by hand; NajdiLab Native would then list them like any owner-supplied GGUF file.
