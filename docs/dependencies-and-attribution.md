# Dependencies and attribution

Core review/dataset work uses Python's standard library with SQLite and framework-free HTML/CSS/JavaScript. Test tools are separate: requirements-dev.txt pins pytest; browser harnesses use externally installed Node/browser tooling. LM Studio Chat optionally uses pinned SDK1.5.0 in NajdiLab's environment; Ollama and LM Studio remain external applications.

Optional offline mask validation uses Transformers AutoTokenizer only; no package is required for core review/export. Shared local tokenizer validation accepts an explicit local path and disables remote code; it does not fetch models or start optimization. No PyTorch/Unsloth/trainer/GPU stack is installed by application setup. Unsloth export is a file-format handoff to an independently managed external environment.

[Dependency licensing evidence](dependency-licensing-matrix.md) and [third-party register](third-party-attributions.md) retain dated upstream source-text checks and NOT_VERIFIED exact-artifact/transitive/native limitations. Deleted internal-training imports are not present dependencies. Retain applicable source/notice obligations for any actual copied code; absence of a runtime does not prove source ownership.

Before distributing anything, inventory exact origin/version/hash, LICENSE/NOTICE, modifications, native/transitive components and data/model/asset permissions. Framework terms do not license weights, content or adapters. Optional Unsloth Studio/CLI AGPL scope is not blanket Apache clearance; keep external pending exact review. [License options](license-options.md), [rights evidence](rights-evidence.md), [publication decision](public-release-decision.md).
