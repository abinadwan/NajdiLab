# Public GitHub readiness review (V2.2.0)

> Historical / Archived Documentation. This record describes its dated implementation and verification. Follow the [current V2.3.0 user guide](../user-guide.md) for present operation.

| | |
|---|---|
| Scope | `update-project` at the V2.2.0 commit, all 183+ commits of history, the installed Windows test copy. |
| Verdict | **Not ready for publication.** No security vulnerability was found in the code reviewed, but owner decisions below remain open. The repository stays private; nothing was published, no visibility or history was changed. |

## 1. Findings

| Area | Result | Evidence / action |
|---|---|---|
| Secrets in the working tree and **all history** | None found | `git grep` over every commit for Hugging Face, GitHub, OpenAI-style, Slack, Google and AWS key formats and PEM private keys: no match. `.env.example` holds names only (the ingest token is empty). |
| Private data tracked | None | Databases, `data/`, `exports/`, `backups/`, `datasets/`, logs, archives, `*.gguf`, `*.safetensors`, checkpoints and compiled Unsloth caches are ignored; `git ls-files` lists none of them. Test fixtures are synthetic. |
| Personal paths and names in documentation | **Fixed at HEAD** | 12 mentions of the owner's Windows profile path in 6 development records were replaced with `%USERPROFILE%`. Earlier commits still contain them (no secret: a Windows user name and local folder names). Rewriting history is an owner decision; this review did not do it. |
| Owner identity | Informational | Commit author name and e-mail are in history, as in any Git repository. README/CONTRIBUTING name the owner's GitHub account. |
| Network binding | Safe default | The server refuses any bind address other than `127.0.0.1`; Host/Origin/Fetch-Metadata checks and CSRF on writes; ingest needs a bearer or HMAC secret. |
| Outbound network | Explicit only | HTTPS with certificate verification to `huggingface.co` (+ its download hosts) and `github.com` (+ release asset hosts), each request started by the user; LM Studio / Ollama only on `127.0.0.1`. No telemetry; nothing is uploaded. |
| Downloads | Verified | GGUF and Safetensors files are checked against the SHA-256 (or git blob id) Hugging Face publishes; the llama.cpp runtime against pinned SHA-256s; resumed downloads are hashed in full; pickle weights and repository code are never downloaded. |
| Archive extraction | Hardened | Runtime archives refuse absolute paths, `..`, drive letters, streams, devices, hard links and escaping symlinks; staging folders; size limits. |
| Subprocesses | No shell | Every call uses an argument list; only NajdiLab's own children are stopped, by handle. |
| Logs | No content | Request logs keep method, path and status (no query strings or bodies); secrets are redacted from metadata. |
| Database changes | Recoverable | Hash-registered migrations; an automatic integrity-checked copy before any schema change. |
| Third-party code | Not vendored | Unsloth Studio (AGPL-3.0) is only imported by the optional verifier from the user's own installation. llama.cpp is MIT; model licenses are shown before each download and must be acknowledged. |

## 2. Remaining blockers and owner actions

1. **License.** No `LICENSE` file is approved ([options](../license-options.md)). Without one the code is not open source. Owner decision.
2. **History.** Decide whether the personal paths in old commits are acceptable or whether to publish a fresh history (for example the curated NajdiLab Core candidate built by `public_source/build.py`). Rewriting this repository's history needs explicit approval.
3. **What is published.** The full repository and the Core candidate differ (the candidate is a dataset-only subset). Choose one.
4. **Clean installation.** Verified only on the owner's Windows 11 machine with an RTX 5070. A run on a fresh account or second machine, and on Linux/macOS if they are to be claimed, is still needed (see [installation](../installation.md)).
5. **CI.** GitHub Actions were not triggered for V2.2.0 by instruction; run them before any release.
6. **Known test flake.** Some HTTP-security rejection tests intermittently see a Windows connection reset instead of the expected 4xx (documented in [chat composer §6](CHAT_COMPOSER.md#6-risks-and-limitations)); the requests are still refused.

Only `127.0.0.1` use is supported. Do not expose the port through tunnels or shared hosting ([security policy](../../SECURITY.md)).
