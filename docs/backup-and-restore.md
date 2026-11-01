# Private backup and separate restore

Source history and operational state are separate recovery requirements. A clone contains no local database, Chat history, dataset versions, previous job/log evidence or external engine state. Keep archives/manifests private; they can include excluded or archived text. Archive is not erasure.

From the intended checkout, `python scripts/backup.py` (or `scripts/backup.ps1` / `.sh`) creates a timestamped ZIP under local backups/. It uses SQLite's online backup API and copies exports/. It does not include all datasets/, reports/, historical training/ state, external models/interpreters or credentials. Export copying is not globally atomic with concurrent mutation: freeze immutable files and verify their hashes. Preserve separately inventoried private evidence without loading it into the application.

For recovery, record authorized source revision, archive/member SHA256, database table counts/schema/ledger and export manifests in a private record. Keep secrets separately in approved private storage. A valid ZIP, push or old successful rehearsal is not complete recovery proof.

1. Verify ZIP/member integrity and reject absolute/traversal/link paths before extraction. Restore into a new empty private checkout, never over live state.
2. Restore a consistent database snapshot without another instance's WAL/SHM. Require integrity_check=ok, no foreign_key_check rows, and matching schema/counts/ledger. Verify every dataset/holdout/manifest hash separately. Retain mismatched/failed evidence privately and stop.
3. Restore other inventoried private artifacts only from verified sources. Keep historical external-runtime copies distinct; this backup does not certify or authorize their restoration/reconciliation. Copied environments can depend on permissions, symlinks, interpreter and original paths; no complete OS image is supplied.
4. Recreate only authorized secrets; never reuse transient session/CSRF/connector consent. Set NAJDILAB_NO_DEMO=1 and inspect source migrations before launch: startup applies unrecorded SQL, with [known loader debt](database-and-migrations.md).
5. Test the restored local review/version/Chat state in isolation, record actual missing fixtures and ensure no unrelated process is operated. The separate [Core profile](../public_source/README.md) has its own coherent registered-version backup/restore contract and limits.

This source-only cleanup changes no database/schema/private export, so its rollback is a reviewed source revert, not a data restore. Earlier source may reopen removed interfaces or unsafe Hermes ingress: inspect before launch. Any later installed update or operational recovery is a separate deliberate action. Do not decommission existing state until recovery is proved.
