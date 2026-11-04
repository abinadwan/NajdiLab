# Managed llama.cpp runtime (V2.0.0, Phase 3)

**Status: development on `update-project` (PR #23, Draft). Not a release.** Application version stays **V2.0.0**.

NajdiLab can now provision, verify, run and remove its own llama.cpp `llama-server` for NajdiLab Native, instead of requiring the owner to find one. Nothing is downloaded, installed, started or removed without an explicit approval for that action.

Code: `app/runtime_catalog.py` (pinned build, host detection, package selection), `app/managed_runtime.py` (download, verification, install, switch, rollback, uninstall), `app/synthetic_gguf.py` (the tiny random-weight model used for the GPU probe), UI in `static/models.js` (**Model library → Runtime**), CLI in `scripts/install.py`.

## 1. What was reused

| Existing piece | Reuse |
|---|---|
| `app/native_runtime.py` | Unchanged lifecycle: 127.0.0.1 only, random port and API key, `--offline`, stripped environment, exact admission, stop only its own child. The managed runtime only supplies `server_path` and a start gate. |
| `app/model_store.py` storage rules | Same reserve rules (`NAJDILAB_DOWNLOAD_RESERVE_GIB`, `NAJDILAB_SYSTEM_RESERVE_GIB`), the same volume detection, free space re-measured during the transfer. |
| `app/hf_hub.py` transport | Same pattern: one HTTPS request per hop, certificate verification on, no automatic redirects, host allowlist on every hop. |
| `app/integrations.py` connector | Health check and the probe completion against the child server. |
| `tests/ollama_disposable.py` synthetic GGUF | Moved to `app/synthetic_gguf.py` so the GPU probe can use it; the tests import it from there. |
| Model library UI | A third tab, **Runtime**, with the same dialogs, status pills and approval pattern. |

## 2. Decisions

1. **Pinned official build.** Source: `ggml-org/llama.cpp` GitHub releases, tag **`b12059`** (commit `1b6935b227b9f9aa89deea8016c0e208f547446f`, published 2026-11-02). This is the build NajdiLab Native was already verified against. llama.cpp publishes every build as an automated GitHub release marked *pre-release*; there is no separate "stable" binary channel (the `v0.8.0` release has no binaries). Trust comes from the pinned tag, commit and the **SHA-256 of every archive**, copied from GitHub's published asset digests into `app/runtime_catalog.py`. A changed upstream file fails verification.
2. **No binaries in git.** The catalog holds names, sizes and hashes only. Archives are fetched at install time (or supplied offline, §6).
3. **Packages** (x86-64 only):

   | Package | Assets | Selected when |
   |---|---|---|
   | `windows-x64-cuda-13.4` | `llama-b12059-bin-win-cuda-13.4-x64.zip` + `cudart-llama-bin-win-cuda-13.4-x64.zip` | NVIDIA GPU, compute capability ≥ 7.5, driver supports CUDA ≥ 13.4 |
   | `windows-x64-cuda-12.4` | `…win-cuda-12.4-x64.zip` + `cudart-…-12.4-x64.zip` | NVIDIA GPU, compute capability 5.0–9.0 (CUDA 12.4 predates Blackwell), driver ≥ 12.4 |
   | `windows-x64-vulkan` | `…win-vulkan-x64.zip` | A Vulkan loader is present and no CUDA package fits |
   | `windows-x64-cpu` | `…win-cpu-x64.zip` | Always eligible (fallback) |
   | `linux-x64-cuda-13.4`, `linux-x64-cuda-12.8`, `linux-x64-vulkan`, `linux-x64-cpu` | Ubuntu archives of the same build | Same rules (CUDA 12.8 covers 5.0–12.0) |

   Other systems and architectures (macOS, ARM) are **BLOCKED** with an explanation; the owner can still point `NAJDILAB_NATIVE_SERVER` at their own build.
4. **CUDA compatibility is verified, not assumed.** Selection rules only narrow the choice (compute capability range of the CUDA toolkit, the driver's maximum CUDA version from `nvidia-smi`). After extraction the build must pass all three checks before it can become active:
   - `llama-server --version` reports build `12059` and commit `1b6935b…` (executable identity).
   - `--list-devices` lists a device of the package's backend (CUDA or Vulkan).
   - **GPU probe:** a tiny random-weight GGUF generated locally is loaded with every layer on that device (`--device <dev> -ngl all`, log verbosity 4 so the server prints its offload line), and a 4-token completion must succeed. Missing kernels for the GPU's architecture ("no kernel image is available") fail here. The startup log line `offloaded N/N layers to GPU` is recorded as evidence. The CPU package runs the same probe with `-ngl 0`.
   Nothing about a specific GPU is hard-coded.
5. **Layout** under `data/native/runtime/`: `installs/<package>-<tag>-<id>/` (files, `NOTICES/`, `najdilab-runtime.json` manifest with every file's size and SHA-256 and the verification evidence), `archives/` (downloads in progress and owner-supplied offline archives), `active.json` (current and previous install). Activation is an atomic `os.replace` of `active.json`. At most two installs are kept: active and previous.
6. **Precedence:** `NAJDILAB_NATIVE_SERVER` (owner-supplied) > active managed install > legacy `data/native/bin/llama-server`. Owner-supplied builds are never changed.
7. **Start gate:** before every Native start from a managed install, every file's size and modification time and the server executable's SHA-256 must match the manifest; otherwise `RUNTIME_NOT_VERIFIED`. **Verify** re-hashes every file.
8. **Fallback:** a GPU package that fails its probe is never activated; the panel offers the next eligible package (Vulkan, then CPU). A model can always be started with *CPU only* (`-ngl 0`).

## 3. Safety rules

- Every action is explicit: Install / Repair / Update (download), Roll back, Uninstall need `approved: true`; Uninstall also needs the typed confirmation. Nothing installs or loads automatically after a download.
- Network: HTTPS only, `github.com` for the release URL, then only `release-assets.githubusercontent.com` / `objects.githubusercontent.com`, at most 3 redirects, exact size enforced, SHA-256 compared before anything is extracted. No token or cookie is sent.
- Archives are untrusted until verified, and their contents are checked on extraction: no absolute paths, `..`, drive letters, `:` streams, device files or hard links; symlinks only as relative sibling links whose target is in the same archive (the Linux `.so` chains); per-file and total size caps; extraction goes into a fresh staging folder and only a fully verified folder is moved into place.
- Disk: the preflight counts the archives plus a 4× extraction bound plus the safety reserve; the exact unpacked size is checked again before extraction; free space is re-measured every 32 MiB during the download.
- Process: the probe and the Native server bind `127.0.0.1` only, with a random API key; NajdiLab stops only processes it started (it holds the handle). Install, update, rollback and uninstall are refused while Native is running.
- No model-repository code is ever run. The probe model is generated by NajdiLab.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Upstream replaces or deletes an asset | Pinned SHA-256 fails closed; offline archives keep working; a NajdiLab update pins a new build. |
| GPU build installs but cannot compute on this GPU | GPU probe must pass before activation; fallback package offered. |
| Driver too old for the CUDA build | Driver CUDA version compared before download; probe catches the rest. |
| Large downloads (CUDA ≈ 0.6 GB) fill the disk | Preflight + reserve + re-measure; cancel deletes partial files. |
| Interrupted install | Staging and `.part` files removed; previous install stays active. |
| Linux, Vulkan, CUDA 12.x packages | Implemented, **not tested on real hardware here**; only the Windows CUDA 13.4 and CPU packages were tested (see §8). |
| Same-user malware replacing files | Out of scope (as for the API key); the stat + hash gate detects accidental changes, and **Verify** re-hashes everything. |

## 5. Rollback

- **In the app:** Model library → Runtime → **Roll back** switches `active.json` to the previous verified install (refused while a model runs).
- **Remove the managed runtime:** **Uninstall** deletes `data/native/runtime/installs/*` and `active.json` only (owner-supplied archives in `archives/` are kept and listed). NajdiLab Native then reports no server, as before this phase.
- **Code rollback:** revert the Phase 3 commits on `update-project`. No migration was added, so the database needs no change; `data/native/runtime/` can be deleted by hand.

## 6. Distribution

- **Source checkout:** contains no platform binaries. `scripts/install.py` (and `install.ps1` / `install.sh`) explains the selected package (source, files, sizes, SHA-256, licenses, destination) and asks `Download and install? [y/N]`. Non-interactive runs skip it and say how to do it later (`--runtime`, or the app). `--no-runtime` skips the question.
- **Offline / packaged distribution:** put the pinned archives into `data/native/runtime/archives/` (same file names). Install then verifies the same SHA-256 and does not download. A packaged distribution ships these archives plus `NOTICES/` and the manifest; it must include the license texts listed in §7. Cloning the source alone does not include any binary.

## 7. Licenses

- llama.cpp: MIT (`LICENSE` of the pinned commit) and `licenses/LICENSE-jsonhpp` (nlohmann/json, MIT) — written into each install's `NOTICES/` because the Windows archives do not contain them.
- LLVM OpenMP (`LICENSE-LLVM-OpenMP`, inside the Windows archives) — kept as shipped.
- NVIDIA CUDA runtime libraries (`cudart-llama-bin-…` archives, published by the llama.cpp project): governed by the NVIDIA CUDA Toolkit EULA (redistributable runtime components). NajdiLab downloads them on the owner's machine from the llama.cpp release; it does not redistribute them. A packaged distribution that ships them must include the NVIDIA EULA terms.
- Model weights remain separate; see [THIRD_PARTY_ATTRIBUTION.md](../THIRD_PARTY_ATTRIBUTION.md).

## 8. Results (2026-11-04, Windows 11, RTX 5070 12 GB, driver 621.01 / CUDA 13.5, compute capability 12.0)

| Check | Result |
|---|---|
| Detection | RTX 5070, compute capability 12.0, driver CUDA 13.5, Vulkan loader present. Recommended `windows-x64-cuda-13.4`; `windows-x64-cuda-12.4` rejected with `GPU_ARCHITECTURE_UNSUPPORTED`; Vulkan and CPU eligible. |
| CUDA 13.4 package, real online download | Both archives (161.1 + 403.9 MiB) fetched through `github.com` → `release-assets.githubusercontent.com`, SHA-256 matched the pins. The first attempt was **refused** by the probe (`RUNTIME_GPU_NOT_USED`): at the default log level this build does not print its offload line, so the GPU evidence was missing. Fixed by running the probe at verbosity 4; nothing had been activated. |
| CUDA 13.4 package, install from offline archives | Identity `build 12059, commit 1b6935b22`; device `CUDA0: NVIDIA GeForce RTX 5070`; probe: 4 tokens, **2/2 layers on the GPU**, 0.58 s; 59 files, 770.7 MB unpacked; 5.6 s including hashing. Offline archives kept, nothing downloaded. |
| CPU package, real online download (update) | 23.5 MiB archive, identity confirmed, probe on CPU (0/2 layers on GPU, 4 tokens); CUDA install kept as previous. |
| CUDA 12.4 package on Blackwell (negative check) | Run directly through the verification (not offered by selection). It **passed** the probe on the RTX 5070 (2/2 layers on the GPU) but needed 11.3 s against 0.58 s for CUDA 13.4, consistent with just-in-time compilation of code that is not native to compute capability 12.0. The selection rule (CUDA 12.4 only up to 9.0) is therefore conservative, not a proven incompatibility; CUDA 13.4 stays the choice for Blackwell. |
| Rollback | Switched back to the CUDA install; start gate passed; full re-hash of every file passed. |
| Opt-in real-build test | `NAJDILAB_RUNTIME_TEST_SERVER=<CUDA install>/llama-server.exe pytest -k real` → 1 passed (CPU and CUDA probes). |
| Automated tests | `tests/test_managed_runtime.py` 33 passed + 1 opt-in; full Python suite 851 passed, 38 skipped, 0 failed; Node 61; models-browser 13; i18n-browser 10; a11y-browser 13; review-restrictions 12; chat-browser PASS; chat-enhancements PASS; public-source builder 12; docs and API-inventory checks PASS. |
| Real model through the app (owner-approved) | Runtime installed in the test installation from offline archives via the UI; official Qwen2.5-0.5B-Instruct Q4_K_M loaded with all layers on CUDA0 and chatted through Chat V2: [REAL_MODEL_ACCEPTANCE.md](REAL_MODEL_ACCEPTANCE.md). The opt-in Native lifecycle tests and the real-build test passed against the installed CUDA `llama-server`. |
| Not tested | Linux packages, Vulkan package, CUDA 12.x packages through the app; models larger than Qwen2.5-0.5B. |

Unpacked size was 1.3× the CUDA archives, well inside the 4× bound used before a download.
