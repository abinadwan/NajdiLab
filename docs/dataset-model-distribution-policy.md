# Dataset and model distribution policy

Status: proposed public-source distribution boundary, 2026-10-27. No asset is licensed or approved for publication by this policy. The default candidate is **source-only**, with explicitly synthetic examples; it excludes private datasets, research records, weights, adapters and operational artifacts.

| Asset class | Default disposition | Evidence required to change disposition |
|---|---|---|
| NajdiLab application logic and documentation | Candidate only; source ownership/license approval pending | Copyright authority, third-party provenance and privacy review of the exact file manifest |
| Clearly synthetic Arabic examples and tests | Candidate; preserve Arabic bytes and processing behavior | Review that examples were independently authored and contain no real identities or copied private records |
| Original conversations, Gold datasets, frozen v008/v009 | Private; must not be distributed | Per-source consent, lawful processing/publication basis, provenance, copyright permission and privacy assessment; preserve originals regardless |
| Reviewer decisions, corrections, model responses and historical evaluations | Private; must not be distributed by default | Reviewer/source permissions, confidentiality review and separate publication authorization |
| Base model weights, tokenizers and chat templates | Excluded; NOT_VERIFIED | Exact upstream repository/revision, all license/use/access terms and required notices; separate component provenance |
| Adapters and checkpoints | Excluded; NOT_VERIFIED | Base-model obligations, training-data rights, contributor ownership and leakage evaluation; rejected evidence remains preserved |
| Merged models, GGUF and other quantized derivatives | Excluded; NOT_VERIFIED | Base and adapter rights plus converter/kernel/tool notices; quantization does not erase upstream obligations |
| Training outputs, runtime logs, reports, SQLite databases and backups | Private; must not be distributed | Individual privacy/secret/provenance review and explicit scope approval |

Possession, a successful training run, Hugging Face access, a model-card license string or an internal model approval does not establish redistribution permission. Research use, model training, commercial deployment and public dataset publication are distinct permissions. Do not treat one as consent to all four.

For each private data source, retain a private provenance ledger: origin and acquisition terms; author and subject permissions; intended purpose and retention; reviewer authorization; third-party text/code rights; sensitive-personal-data checks; withdrawal/deletion handling and applicable jurisdiction. Include conversations about other people and quoted material. Redaction or pseudonymization alone does not establish publication rights. Do not commit that ledger if it contains personal evidence.

## Protected-source separation plan

The following are research-bearing source, not generic examples: `scripts/complete_review_queue.py`, `scripts/build_v007_eval_report.py`, `scripts/build_v007_epoch2_report.py`, `app/phase38_dataset.py` and the historical repair material in `app/phase39_edits.py`. The historical assertion in `tests/test_phase39_mt06_repair.py` also repeats protected correction text. Corpus-specific identifier matching exists in the analytical utilities listed in [Arabic exceptions](arabic-localization-exceptions.md). These files remain unchanged and are **not cleared for public distribution**.

The server imports Phase 3.8/3.9 modules directly; freeze/resolution modules and tests import them too. Removing files from an archive would break imports. A working public replacement must therefore be developed separately, with the protected implementation retained privately:

1. Inventory importers and historical endpoints; separate reusable validation/review storage interfaces from fixed historical manifests and builders.
2. Make historical builders, correction manifests and evaluator annotations private optional tools. Public handlers must return a structured unavailable response when private assets are absent, without importing private data-bearing modules.
3. Define private fixture schemas for messages (`role`, `content`), record IDs, review decisions, provenance and fingerprints from the existing contracts; loading must be explicit, read-only by default and restricted to an owner-selected private directory. No automatic execution of dataset code or discovery of live datasets.
4. Test public interfaces with newly authored, labeled synthetic Arabic fixtures and temporary directories. Keep historical tests in the private validation track; absence is SKIP, never fabricated historical success.
5. Compare protected hashes; obtain review of a complete public manifest, including tests, docs and generated reports. Run the public package independently before considering release.

This is an exclusion/replacement plan, not an implemented separation or permission to edit frozen evidence. No genuine research evidence was replaced with synthetic content. Current tracked modules still block a public snapshot.

`.gitignore` reduces accidental additions; it cannot remove tracked records, sanitize Git history or enforce a distribution boundary. Review source text as well as file extensions. Do not use `git archive HEAD` as a public package until every included path is cleared.

## Isolated engineering implementation

The [new boundary specification](public-private-boundary.md) and [candidate report](public-source-isolation-report.md) implement a narrower separate core profile without editing the protected files above. Original full-application separation remains gated; the candidate does not establish rights or sanitize repository history.
