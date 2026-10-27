# Dependencies and attribution review

Status: preliminary source inventory, checked 2026-10-26. The repository has no complete pinned dependency lockfile or final third-party notice bundle. This document identifies evidence and remaining review work; it is not a redistribution clearance or a claim that all dependencies use one license.

## Local application

Top-level application imports use Python's standard library (`http.server`, `sqlite3`, JSON, hashing, filesystem, subprocess and related modules). The frontend uses repository HTML/CSS/JavaScript with no package-manager build step. Python and bundled SQLite retain their own upstream terms. Inventory the exact interpreter/distribution, SQLite build and any bundled static artwork/fonts before packaging a binary or installer.

`app/training_control.py` contains remote-runtime script strings importing `huggingface_hub`; this does not make it a startup import for the local web app. Acquisition and ML execution are separate features.

## Optional ML/integration inventory

| Component | Evidence in this source | Review before redistribution |
|---|---|---|
| `torch` | Training adapter, collator, benchmark and controlled scripts; runtime probe | Exact PyTorch build, license files and bundled components/CUDA terms |
| `transformers` | Tokenizer/model loaders and Trainer | Exact release artifacts, notices and tokenizer/model dependencies |
| `unsloth` | FastModel training/benchmark/export; runtime probe | Exact release, auxiliary packages/kernels and model-specific terms |
| `peft` | Controlled training and benchmark; runtime probe | Exact package license/notice and transitive dependencies |
| `numpy` | Smoke, benchmark and controlled training scripts | Exact wheel and bundled numeric-library notices |
| `safetensors` | `export_v007_e1_ollama.py` | Exact package and binary-component notices |
| `huggingface_hub` | Explicit WSL model acquisition snippets | Exact client release plus remote model/repository terms |
| `accelerate`, `bitsandbytes` | `REQUIRED_PACKAGES` / runtime checks; optimizer/runtime stack | Exact releases, binary/kernel/CUDA terms |
| `trl` | Historical preflight evidence/check vocabulary | Verify whether selected runtime actually installs/uses it; review artifact terms if included |
| External Hermes `agent.outbound_webhooks` | `scripts/acceptance_v11.py` | External integration fixture; not bundled as a web-app dependency |
| WSL, NVIDIA/CUDA, Ollama/GGUF tools | Explicit runtime and export workflows | External platform/tool licenses and selected model terms; not automatically bundled |

Primary upstream license references include [Transformers](https://github.com/huggingface/transformers/blob/main/LICENSE) and [Unsloth](https://github.com/unslothai/unsloth/blob/main/LICENSE), whose upstream main-branch license files were consulted during preparation. The consulted Transformers file identifies Apache-2.0. The consulted Unsloth file distinguishes Apache-2.0 core/test/script paths from optional Studio/CLI paths identified as AGPLv3; package name alone is therefore insufficient for clearance. Main-branch references are discovery evidence only: they do not establish the terms of historical installed versions or every included file. Other artifact licenses remain unverified here. No actual models, ML wheels or operational datasets were redistributed by this documentation task.

## Required release evidence

Pin the exact versions/hashes of anything packaged. Collect the matching LICENSE/NOTICE/copyright files, transitive native-library notices, source and binary distribution conditions and any required modification notices. Record static asset provenance and rights; record the source/revision and terms for model weights, tokenizer/template and adapters independently. Produce an attribution bundle scoped to the actual distribution, preserving upstream notices rather than substituting a generic project license.

Historical runtime measurements in the [preflight runbook](training-preflight-runbook.md) are not a lockfile. The model catalog supplies identity/revision evidence but no automatic legal approval. See [license options](license-options.md) for the distinct source-license decision.
