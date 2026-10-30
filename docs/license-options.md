# Source license decision: Apache-2.0, MIT or BSD-3-Clause

Final inactive drafts and owner fields: [licensing approval package](proposals/licensing-approval.md), [Apache-2.0 text proposal](proposals/LICENSE-Apache-2.0.txt) and [NOTICE proposal](proposals/NOTICE.txt). No root LICENSE or active NOTICE is introduced.

Status: **OWNER DECISION REQUIRED — no LICENSE has been added.** This is a preparation recommendation, not a license grant or a conclusion that all contributions are cleared. Confirm copyright ownership/contributor authority and the intended public attribution before applying any license. Do not substitute an actual developer identity without consent.

| Option | Main effect | Distribution obligations | Tradeoff |
|---|---|---|---|
| MIT | Broad permission to use, modify, distribute and sell the covered software | Preserve the copyright and permission notice in copies or substantial portions; retain the warranty disclaimer | Short and simple; lacks an express patent grant |
| BSD-3-Clause | Broad free/commercial use, modification and redistribution | Retain copyright, conditions and disclaimer in source; reproduce them in binary documentation/materials; no endorsement using contributor names without permission | No express patent grant; explicit non-endorsement clause |
| Apache-2.0 | Broad copyright permissions plus an express contributor patent grant with patent-litigation termination | Supply the license; mark modified files; preserve relevant notices; reproduce applicable upstream NOTICE attribution if provided | More explicit patent terms and contribution rules, with more notice administration; no general trademark permission |

The [OSI MIT text](https://opensource.org/license/mit) and [Apache 2.0 text, especially sections 3–6](https://www.apache.org/licenses/LICENSE-2.0) are the primary references checked on 2026-10-26. Both disclaim warranties; neither requires every downstream modification to be published.

**Recommendation:** Apache-2.0 for NajdiLab source and documentation if the owner wants an explicit patent framework for external contributors and integrations. MIT is reasonable if minimal obligations are the main priority. This recommendation does not select a license on the owner's behalf. If Apache-2.0 is chosen, retain third-party notices and add a project NOTICE only where attribution requirements warrant it; do not invent provenance. If MIT is chosen, use the owner-approved copyright holder and year.

## Separate rights layers

A NajdiLab source license covers only material the licensor has authority to license. It does not relicense Python, SQLite, ML packages, vendor runtimes, model weights, tokenizers, chat templates, downloaded repositories, datasets, prompts, generated outputs or conversation/review content.

- Review exact dependency artifacts and transitive components, not just top-level project names.
- Review each selected model repository at its pinned revision, including model license, use policy, access conditions and redistribution terms. Model families and quantized derivatives can differ; no shared license is assumed for Gemma, Ministral, Unsloth-hosted variants or Ollama models.
- Review consent, privacy, copyright, provenance and training/publication rights for every dataset. Model availability and an ingest event do not establish those rights.
- Adapters and merged/quantized exports may carry source-model or data obligations. Review their intended distribution separately.
- Private backups and existing Git history remain private-risk material until the owner approves their public disposition; adding a license does not sanitize them.

See the [dependency inventory](dependencies-and-attribution.md) and [publication blockers](open-source-readiness.md). No final license, release or history rewrite is authorized by this document.

## Attribution and derivatives

All three permit free/commercial use, modification and redistribution when their terms are met; none generally requires publishing private changes. MIT preserves its copyright/permission notice in copies/substantial portions. BSD-3-Clause distinguishes source and binary notice retention and prohibits implied endorsement. Apache-2.0 requires the license, modification notices and relevant retained notices; if an upstream NOTICE is supplied, section 4(d) requires a readable copy of applicable attribution in one of the allowed locations. Its express patent grant/termination differs from MIT/BSD silence. It grants no general trademark permission.

Legally required notices are distinct from recommended visible credit. None requires a homepage backlink in every derivative application. Recommend downstream README/About credit linking the original repository and making modifications clear, without implying owner endorsement. If mandatory public homepage attribution is desired, that exceeds these standard terms and needs a separate legal/owner decision; no custom restriction is added here.

[Proposed NOTICE](proposals/NOTICE.txt) is inactive until license/copyright/rights approval. Only after compatible licensing is selected may distribution text state: "NajdiLab is free and open-source software. When redistributing NajdiLab or works derived from it, preserve all copyright, license, and attribution notices required by the applicable license. Original project: NajdiLab. Source repository: https://github.com/abinadwan/NajdiLab". This conditional text is not a current license grant.

BSD reference: https://opensource.org/license/bsd-3-clause . Compatibility is distribution-specific: preserve each dependency's terms; unverified/strong-copyleft auxiliary components, weights/data or third-party code are not automatically relicensed by choosing Apache/MIT/BSD. Exact-artifact review remains open.
