# System requirements and verification scope

## Core local web platform

| Item | Requirement / evidence |
|---|---|
| Python | Code/launcher minimum 3.11; preparation tested Python 3.12.10 on Windows; Ubuntu/WSL version in installation-verification. Other versions need checks |
| SQLite | Python sqlite3 with WAL/FKs; SQLite 3.24+ for registry UPSERT; tested builds recorded in verification |
| Dependencies | Standard library only; no pip, GPU/CUDA, Hermes, Ollama, Node or model required to open app |
| Tests | Optional requirements-dev.txt; never implicitly installed on launch |
| Browser | Modern JS/CSS browser; recorded real-browser English/Arabic and themes proof; legacy browsers unverified |
| RAM/disk | No measured universal minimum. Provide writable space for SQLite WAL, exports, full private backup and restore copy. Dataset/model sizes dominate |
| Network | Loopback IPv4 only; default 127.0.0.1:8770 or NAJDILAB_PORT. Git/package acquisition needs separate access. No public-network server support |
| Permissions | Read source, write installation-local state; no Administrator/sudo needed for normal setup/run |
| OS | Windows 11 tested. Ubuntu 24.04 under WSL2 only to scope recorded in installation-verification; hosted native Ubuntu source tests passed separately; native deployment, macOS and other distributions/versions not certified |

Each checkout owns its data/registry paths. Keep SQLite and writers on the same OS filesystem; do not share a live DB between Windows/WSL. Setup checks runtime/source only; first launch applies existing migrations and initializes state.

## Optional model training

Production integration uses a separately registered WSL runtime and selected NVIDIA/CUDA stack. Core setup does not install it. Native Windows training, CPU-only, non-NVIDIA GPUs and arbitrary GPUs are not certified.

PyTorch/CUDA, Unsloth, Transformers, PEFT, Accelerate and bitsandbytes versions depend on pinned model/runtime. Check exact wheels/driver, tokenizer tool template, precision/quantization, and live preflight. Do not install an arbitrary latest bundle into the web environment. numpy/safetensors/huggingface_hub depend on selected operation. VRAM estimates are advisory; no exact minimum/fit guarantee is established.

A [historical configuration](training-preflight-runbook.md) recorded RTX 5070 with about 12 GiB VRAM and specific package versions. This is one observation, not a current minimum or recreated lockfile. WSL GPU access, model paths, rights and downloads need separate verification/approval. Setup never installs CUDA, WSL, Hermes, Ollama or models.

Budget storage for base weights, tokenizer/template, frozen dataset/holdout, staging, checkpoints, adapters, logs, recovery snapshots and evaluation. Keep source and outputs separate. Prove live checks, masks, preflight and zero-step Dry Run before distinct Smoke/Full approvals. Recovery does not revive an old authorization. See [dataset/training guide](dataset-and-training.md).
