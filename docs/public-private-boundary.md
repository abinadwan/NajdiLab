# Source-only Core boundary

The separately generated Core candidate includes local authenticated ingestion, contextual review/corrections, privacy/eligibility, dataset preparation/diagnostics, selected verified JSONL retrieval and coherent private backup/separate restore. It is narrower than NajdiLab Chat. New Chat/integration/Unsloth features are not automatically included. [Core README](../public_source/README.md).

The deterministic builder uses an explicit mapping and SHA256 pins, validates import closure and classifies excluded paths. It excludes Git, private research/repair/evaluation records, databases, generated datasets/archives/backups, credentials and external models/services. Do not copy a whole working directory or infer clearance from an extension. The extension interface is removed entirely. Unknown old execution paths return ordinary404; there is no automatic plugin loader or filesystem discovery.

Candidate wrappers enforce required atomic revision checks, preserve omitted flags/notes, block private earlier context, verify exact version/manifest/hash bytes, constrain JSONL attachments and use private snapshot-coherent recovery into a new destination. Same-user direct writers, asserted reviewer identity, HMAC replay freshness and migration-loader debt remain outside these guarantees. Candidate refuses the legacy unauthenticated-ingest override before parsing/writes; Hermes receiver is also blocked.

Earlier protected-source/hash inventories are dated evidence, not a ban on the owner's explicitly authorized source cleanup or a claim that deleted paths remain. Real dataset-specific repair modules retained in the private application are not selected merely because their APIs still exist. [Rights evidence](rights-evidence.md), [verification](verification-evidence.md), [release gates](public-release-decision.md).

Rebuild and verify a pristine separately created candidate after selected sources change, run its synthetic tests/browser checks and review new pins explicitly. No candidate package, license or publication is implied. Rollback source/policy together through a reviewed revert; preserve all private state.
