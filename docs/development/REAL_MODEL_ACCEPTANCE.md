# Real GPU and model acceptance (V2.0.0)

**Date:** 2026-11-04. **Machine:** Windows 11, NVIDIA GeForce RTX 5070 12 GB (compute capability 12.0, driver 621.01, CUDA 13.5), 31.7 GB RAM. **Application:** disposable test installation `C:\Users\Admin\NajdiLab-Update-Test` at http://127.0.0.1:8870, `update-project` commit `4fd2091`, product version V2.0.0. **Approvals:** the owner approved this run (CUDA runtime with the NVIDIA CUDA Toolkit EULA, and the Qwen test model). Every step went through the application's own approval controls.

## 1. What was done, in order

1. **Runtime:** Model library → llama.cpp runtime → *Check this computer* → *Install…* (CUDA 13.4, recommended; CUDA 12.4 shown as not compatible) → license acknowledgement → install from the pinned archives already placed in `data/native/runtime/archives` (0 bytes downloaded). Result: *Ready — verified*: `build 12059, commit 1b6935b22`, device `CUDA0: NVIDIA GeForce RTX 5070`, probe 4 tokens with **2/2 layers on the GPU** in 0.56 s; 59 files, 735.0 MiB.
2. **Model:** Discover → `Qwen/Qwen2.5-0.5B-Instruct-GGUF` (verified official publisher, Apache-2.0) at revision `9217f5db79a29953eb74d5343926648285ec7e67` → *Check fit* for `qwen2.5-0.5b-instruct-q4_k_m.gguf` at context 8192 with the hardware read → **COMPATIBLE**, fully on the GPU, estimate 1.13 GiB against 10.22 GiB free → license acknowledgement → *Start download*. Result: *Ready — verified*; 491,400,032 bytes, SHA-256 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` (matches Hugging Face; re-hashed independently with `sha256sum`: equal).
3. **Load:** *Check fit and load…* → context 8192, *All layers on GPU* → approval checkbox → *Load in NajdiLab Native*.
4. **Chat V2:** a runner (`real_acceptance.py`, kept outside the repository) drove the running application over the same HTTP routes the browser uses (`/api/v1/chat/sessions`, `…/send-stream` NDJSON, `…/stop`, `…/collect`, `/api/v1/native/stop`), sampled `nvidia-smi` during generation and read the test database read-only. The saved chats were then opened in the Chat V2 interface.

## 2. Results

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Managed CUDA 13.4 runtime installed and verified | **PASS** | Identity, device and GPU probe as above; start gate passed for every start. |
| 2 | Official Qwen test model downloaded and SHA-256 verified | **PASS** | Library status *Ready — verified*; independent `sha256sum` equal; exact size. |
| 3 | Runtime start with CUDA backend | **PASS** | `llama-server` PID 13564 from the managed install, `--host 127.0.0.1`, random port, `--offline`, `-c 8192`, `-ngl all`; `/props` build `b12059-1b6935b22`; `--list-devices` shows CUDA0. |
| 4 | Real GPU inference, not CPU-only | **PASS** | All layers requested on CUDA0; the process is listed by `nvidia-smi` as a GPU compute process; device memory used rose from 1,324 MiB to 1,974 MiB on load (+650 MiB ≈ 469 MiB weights + 96 MiB KV + compute buffers) and to a peak of 2,273 MiB while generating; a CPU-only run allocates no device memory. The "2/2 layers on GPU" log line is recorded by the runtime probe; NajdiLab Native does not keep the model server's log, so the per-model layer line itself was not captured. |
| 5 | Response generation | **PASS** | English and Arabic replies completed and saved (see §3). Quality note: the 0.5B model's factual answers were wrong (it described GGUF as a compressed or graphics format); this is the model, not the pipeline. |
| 6 | NDJSON streaming through Chat V2 | **PASS** | Events `accepted`, 5 × `phase`, `admitted`, 12–42 `content` deltas, `done`; text identical to the saved turn. |
| 7 | Stop and cancellation | **PASS** | Stop sent 0.044 s after the first delta; stream ended with `STOPPED` at 0.086 s; 0 turns saved; the runtime kept running. |
| 8 | Context-budget enforcement | **PASS** | A 6,000-word prompt: measured 6,034 prompt tokens + 1,024 reserve ≤ 8,192, admitted; the runtime's final `usage.prompt_tokens` was 6,034 (equality checked before saving). A 9,000-word prompt: `CONTEXT_LIMIT`, the chat closed and a new one opened, **0 turns saved, nothing truncated** (`chat_turns` 7 → 7). A 4,096-token chat against the 8,192 runtime: `ENGINE_CONTEXT_MISMATCH`. |
| 9 | Model identity | **PASS** | Each session bound to `native:74a4da8c…`; `/props` model path and context re-checked before and after each reply (identity recheck 14–15 ms). The UI shows the binding and blocks sending once the runtime is stopped. |
| 10 | Incomplete responses | **PASS** | Reply reserve of 8 tokens → `INCOMPLETE_RESPONSE` ("The engine did not finish the reply normally; no pair was saved."), 0 turns saved. |
| 11 | Conversation persistence | **PASS** | Two turns (English, Arabic) read back equal to the streamed `done` events; opened in Chat V2 with the context meter (178 + 1,024 reserved of 8,192, 15 %) and *Not collected for review*. |
| 12 | Explicit consent for dataset collection | **PASS** | All real turns without consent: conversations / messages / reviews 0 / 0 / 0 → 0 / 0 / 0. A non-boolean choice: HTTP 400 `CONSENT_REQUIRED`. After an explicit opt-in, one turn created exactly 1 conversation and 1 review, `PENDING`, `training_eligible = 0`. |
| 13 | Runtime stop and GPU memory release | **PASS** | `/api/v1/native/stop` (approved): state STOPPED, process 13564 exited, device memory 2,248 → 1,576 MiB (−672 MiB, the amount the model had added; other applications share the GPU). |
| 14 | Gemma 4 E4B Q4_0 (existing NajdiLab download) | **BLOCKED** | No NajdiLab-managed Gemma 4 file exists on this computer (searched the user profile and drive F:). It would have been in the test installation's `data/models/huggingface/`, which was deleted when the test installation was replaced earlier on 2026-11-04 (deletion of that installation was owner-authorized; its downloaded models were not checked for first). Not downloaded again: that needs separate approval. LM Studio's own Gemma 4 files were not read or used. |
| 15 | Per-process VRAM figure in NajdiLab | **NOT TESTED (not available)** | On Windows (WDDM) `nvidia-smi` reports per-process memory as N/A, so NajdiLab's *measured VRAM* field stays empty; the device-level numbers above were taken with `nvidia-smi` directly. |
| 16 | Linux, Vulkan, CUDA 12.x packages; models other than Qwen 0.5B | **NOT TESTED** | — |

## 3. Measurements

| Measure | Value |
|---|---|
| Runtime | llama.cpp `0.8.0-dev (build 12059, commit 1b6935b22)`, package `windows-x64-cuda-13.4` (CUDA 13.4 runtime libraries), backend CUDA, device CUDA0 RTX 5070 |
| GPU layers | `-ngl all` (all layers + output) on CUDA0; probe 2/2 |
| Context used | 8,192 (one slot, no context shift), reply reserve 1,024 |
| Device VRAM | 1,324 MiB before load → 1,974 MiB loaded → 2,169–2,273 MiB peak while generating → 1,576 MiB after stop |
| `llama-server` RAM | 811.8 MiB working set, 1,235.0 MiB private |
| Time to first token (client, from request) | 0.135 s (first request after load), 0.048 s, 0.065 s; server-side first token 61–63 ms |
| Generation speed | 125.7 tokens/s (30 tokens, first request), 293.8 tokens/s (13 tokens), 359.1 tokens/s (43 tokens), measured from the first delta to the `done` event (includes the identity re-check and commit, so it understates raw decoding speed; replies were short) |
| Exact admission | 6,034 measured = 6,034 reported by the runtime |
| Arabic | reply with 132 Arabic letters, streamed and saved |
| Errors, crashes, warnings | none from NajdiLab or the runtime during the run |

## 4. Regression checks on the installed copy

With the real CUDA `llama-server` the normally skipped opt-in tests ran: `tests/test_native_runtime.py` lifecycle tests (start, admission, Stop with a synthetic GGUF) and `tests/test_managed_runtime.py::test_real_build_proves_identity_and_computes` — 54 passed, 1 skipped (symlinks not permitted on Windows).

| Suite (installed copy, `4fd2091`, real CUDA `llama-server` enabled) | Result |
|---|---|
| Python | **890 passed, 34 skipped, 0 failed** (the 34 skips: private historical artifacts not distributed, opt-in Ollama, Windows symlink limits) |
| Node | 62 passed |
| models-browser / i18n-browser / a11y-browser / review-restrictions | 15 / 10 / 13 / 12 passed |
| chat-browser, chat-enhancements | PASS |
| Public-source builder | 12 passed |
| Docs, API inventory, compileall | PASS |

After the MiB/GiB label fix (development checkout): models-browser 15 and i18n-browser 10 passed.

## 5. Defects and limitations found

- **Fixed:** the Model library labelled binary sizes as "MB"/"GB" (Qwen showed "468.6 MB" for 491.4 million bytes); they are now labelled MiB/GiB.
- **Limitation:** no per-process VRAM on Windows (WDDM), see #15.
- **Limitation:** only the smallest official instruct model was run; larger models, long generations and sustained-load behaviour were not measured.
- **Model quality:** Qwen2.5-0.5B is too small for reliable answers; it is a pipeline test model only.
