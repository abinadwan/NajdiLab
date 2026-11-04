# NajdiLab Native — local GGUF models through llama.cpp's llama-server

**Status: in development on `feature/chat-experience-v2`, not merged, not owner-accepted.** Tested only on Linux, CPU only, with a tiny random-weight synthetic GGUF. No real model, no GPU and no Windows run has been tested. RTX 5070 support and compatibility with arbitrary GGUF files are **not claimed**.

> **V2.0.0 (Phase 3):** NajdiLab can now install and verify its own pinned llama.cpp build: **Model library → llama.cpp runtime**, or `python scripts/install.py --runtime`. See [Managed llama.cpp runtime](development/MANAGED_RUNTIME.md). The managed build was verified on Windows with an RTX 5070 (CUDA 13.4 package); the owner-supplied path below still works and takes precedence.

NajdiLab Native lets Chat use a local GGUF model without Ollama or LM Studio. NajdiLab starts and stops **one** llama.cpp `llama-server` process — the managed runtime or one the owner supplies — and talks to it over its HTTP API. Code: `app/native_runtime.py` (lifecycle and engine), `app/gguf.py` (header reader). License review: [THIRD_PARTY_ATTRIBUTION.md](THIRD_PARTY_ATTRIBUTION.md).

## What NajdiLab will never do

- Download a program, a model, weights or a tokenizer by itself. The managed llama.cpp runtime is downloaded only when you approve that package, and only the pinned official build with matching SHA-256 values. `llama-server` is started with `--offline`, and proxy and Hugging Face token variables are removed from its environment. Model files may be downloaded separately, only on explicit approval, through the Model library ([Hugging Face Direct](development/HUGGING_FACE_DIRECT.md)); NajdiLab Native starts such a file only after its size and SHA-256 were verified (`MODEL_NOT_VERIFIED` otherwise).
- Listen beyond this computer. The server always binds `127.0.0.1` on a free port, with a random API key per start (`LLAMA_API_KEY`), no web UI, no `/slots`, no `/props` writes.
- Stop anything it did not start. Stop, restart and NajdiLab shutdown act only on the child process handle NajdiLab created.
- Change Ollama, LM Studio or their models.

## Setup

1. Either install the managed runtime (Model library → llama.cpp runtime: NajdiLab chooses the package for your GPU and driver, verifies it and proves it computes on the device), or get a `llama-server` binary yourself and set `NAJDILAB_NATIVE_SERVER` (step 3). An owner-supplied binary is used as is; NajdiLab does not choose or verify it.
2. Put GGUF files in a folder, by default `data/models` inside the NajdiLab folder (sub-folders up to 4 levels).
3. Only for your own binary or another models folder, set the paths before launching NajdiLab:

```powershell
$env:NAJDILAB_NATIVE_SERVER = 'C:\tools\llama.cpp\llama-server.exe'
$env:NAJDILAB_NATIVE_MODELS = 'D:\models\gguf'
.\run.ps1
```

```bash
NAJDILAB_NATIVE_SERVER=/opt/llama.cpp/llama-server NAJDILAB_NATIVE_MODELS=~/models sh ./run.sh
```

4. In Chat, open **⚙ Chat settings → NajdiLab Native**, choose a model, a context size and GPU use, then **Start**. When it shows *Running*, **New chat** offers *NajdiLab Native* as a runtime.

## How a model is checked

| Step | What happens |
|---|---|
| Discovery | Lists `*.gguf` files in the models folder only; paths outside it (including `..` and symlink escapes) are refused. |
| Format check | Reads only the header: `GGUF` magic, version 2 or 3, bounded tensor and metadata counts, typed metadata. Truncated, oversized or hostile headers are rejected with a fixed code (`NOT_GGUF`, `TRUNCATED`, `HEADER_LIMITS`, …). Vision projectors (`clip`) and files without a declared context are not offered. |
| Split files | `-00001-of-0000N.gguf` sets are listed as `SPLIT_UNSUPPORTED` (not yet handled). |
| Integrity | SHA-256 of the whole file at start (cached by size and modification time). Chats are bound to `native:<sha256>`; a changed file blocks the next turn (`MODEL_CHANGED`). Compare the hash with the publisher's if they provide one. |
| License | `general.license` is shown when the file declares it. That field is self-reported; check the model's real terms yourself. |

## Context, GPU and memory

- The context is fixed when the server starts (`-c`, one slot, `--no-context-shift`). A chat's context budget must equal the running context; otherwise sending is refused with `ENGINE_CONTEXT_MISMATCH` (restart Native at that context or start a new chat).
- GPU use maps to `-ngl`: *Automatic* (`auto`), *All layers* (`all`), *CPU only* (`0`). The device list comes from `llama-server --list-devices` of your build.
- **Measured** VRAM: when `nvidia-smi` exists, NajdiLab reads the memory used by its own server process ID only. **Estimates** for 4096–65536 come from the GGUF layer sizes and file size (*Estimate memory*), and are labelled as estimates. Neither is a guarantee.
- Start failures are classified without showing raw server output: `NATIVE_OUT_OF_MEMORY`, `NATIVE_MODEL_UNSUPPORTED`, `NATIVE_PORT_UNAVAILABLE`, `NATIVE_START_FAILED`.

## How a turn is proven

1. Same running instance, same file size/mtime, `/props` shows the same model path and context.
2. The server's own `/apply-template` renders the full history and `/tokenize` counts it exactly. Prompt + reserved reply must fit the budget; otherwise the chat closes and a new one opens (no truncation).
3. The reply streams from `/v1/chat/completions` (`stream: true`, usage included). `reasoning_content` is shown as **thinking** and never saved; `content` is the answer.
4. After the stream: identity is checked again and the server's final `usage.prompt_tokens` must equal the measured count, `finish_reason` must be `stop`, and the answer must be non-empty. Only then is the turn saved.

Verified against the real `llama-server` (b12059): the measured count equalled `usage.prompt_tokens` (57 = 57 on the synthetic prompt), an oversized prompt is refused by the server with HTTP 400, and Stop cancels generation without stopping the server.

## Privacy and data collection

Same rules as other runtimes: collection is off by default and after restart, only complete verified replies can be collected, thinking is never collected, nothing is training-approved automatically.

## Tests

`tests/test_native_runtime.py`: parser, path-safety and start-validation tests always run. Three lifecycle tests run only with `NAJDILAB_NATIVE_TEST_SERVER=/path/to/llama-server` and use the synthetic GGUF from `tests/ollama_disposable.py`; without it they are reported as **skipped**, which is not a pass. Results: [Chat V2 test log](development/CHAT_EXPERIENCE_V2.md#test-results).

## Known limits

- Tested on Windows with an RTX 5070 and the managed CUDA 13.4 build using one real model, Qwen2.5-0.5B-Instruct Q4_K_M ([record](development/REAL_MODEL_ACCEPTANCE.md)). Not tested: larger real models, chat templates with thinking, Linux GPUs.
- On Windows, per-process VRAM is not reported by `nvidia-smi` (WDDM), so *measured VRAM* stays empty there.
- One model at a time; one request at a time.
- Split GGUF sets are not supported yet.
- The API key protects against other local programs using the port by accident; it is not a defense against malware running as the same user.
