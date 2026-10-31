# Owner-operated Windows native capture acceptance

Status: **NOT TESTED on the owner's machine.** Perform personally only after reviewing/approving the relevant PRs, merging them, verifying green CI and following the [safe update/backup/migration/rollback procedure](integrations-windows-update.md). This document does not authorize Codex to update the installed checkout or modify any application.

## Current release disposition

| Application | Native capture acceptance | Current reason |
|---|---|---|
| Hermes Agent | BLOCKED | No verified zero-change live source acquisition; strong internal terminal receipts alone do not establish safe access |
| LM Studio | BLOCKED (capability UNSUPPORTED) | No validated native conversation JSON/completion format or native history API contract |
| Ollama Desktop | BLOCKED | Stored partial and completed output cannot be reliably distinguished; no shared native completion subscription |

**Do not execute the positive capture sequence below for this release, and do not mark it PASS.** No native collector is enabled. Do not send real/private conversations as tests, activate Hermes hooks, change YAML/JSON/environment/settings, install plugins, enable app debug logging, export conversations, copy/paste messages, or reroute traffic. A test through NajdiLab's runtime API is not a native-app capture test.

## Current UI/guard checks (normal operation uses Settings only)

1. Open the updated NajdiLab and navigate to **Settings → Integrations**.
2. For each app, record application name, known installation marker/API availability separately from **Native source detection**. A detected model/server does not prove a native source exists.
3. Verify **Installed version: NOT_VERIFIED** and **Source format verification: NOT_TESTED** unless a future implementation provides actual verified metadata. Research versions in documentation are not your installed version. You may record the version displayed by the original application's existing About screen; do not edit anything there.
4. Verify native capability/technical reason matches the table, **Native source connection: DISCONNECTED**, **Automatic Conversation Collection: OFF** and disabled, and **Last successful capture: Never**.
5. If automatic source detection failed, optionally expand **Select a local source path (metadata only)**. Select/enter only the existing expected `state.db`, `conversations` folder, or `db.sqlite`. Approve metadata inspection in NajdiLab. No upload/export/content reading occurs; successful detection must not change capture capability, verify a schema or turn collection on. Unsafe/network/reparse/inaccessible sources may be refused; do not change source permissions to force detection.
6. Use **Verify collection OFF** and **Verify native disconnect**, approving each within NajdiLab. Verify collection remains OFF, existing queue items remain intact and the external app is unchanged.
7. Runtime connect/model selection/tests remain separately available for LM Studio/Ollama. Do not record their successful generation as capture PASS. Hermes's unsafe HTTP receiver must stay blocked; local native disconnect never claims to remove an external hook or stop its sender.
8. Restart only NajdiLab through its normal process when safe. Verify collection still OFF and custom diagnostic path selection resets. Do not stop Hermes Gateway/Bridge, WhatsApp/Baileys, LM Studio, Ollama or unrelated workers/services.

Record **guard/UI PASS/FAIL separately** from native capture **BLOCKED**. If the UI ever claims capture is active/supported in this release, stop the acceptance process and report FAIL without changing source apps.

## Positive native capture sequence — future supported release only

This is an explicit unexecuted gate for each application whose capability eventually becomes SUPPORTED after a separate reviewed implementation. If any prerequisite is unavailable, mark that application BLOCKED; do not substitute routed chat/manual transfer.

1. Open NajdiLab; go to Settings → Integrations and verify automatic discovery plus actual installed-version/source-format compatibility.
2. Approve **Connect native source**. This must remain distinct from runtime-model permission and collection consent.
3. Separately approve **Automatic Conversation Collection**. Verify a new-only baseline and no historical import.
4. Open the **original application**, create an ordinary new native chat and send a unique synthetic message, for example `NAJDI-NATIVE-<app>-<unique-test-id>: reply with a fictional fruit name`. Do not include private information, credentials, attachments or tools.
5. Wait for its assistant to finish successfully, without exporting/copying/pasting/rerouting the conversation or running terminal commands.
6. Open NajdiLab review queue. Verify exactly one new pair, correct original-app provenance, model if available, stable conversation/turn identity and timestamp; status PENDING, training eligibility false. Inspect that no history/system/developer/reasoning/tool/config/auth data was imported.
7. Wait through additional collection cycles and refresh; verify no duplicate. Restart/recovery must not backfill history or replay the pair.
8. Disable collection inside Settings; verify OFF. Send a second unique synthetic message in the original app and wait for completion. Verify it does not enter NajdiLab.
9. Disconnect native source; repeat a third synthetic message and verify no additions. Existing captured review data must remain intact, and the original app/services/settings must remain unchanged.
10. Record per-app PASS/FAIL/BLOCKED/NOT TESTED, installed version/format, synthetic IDs, counts, timestamps and deviations. Keep test content local. Do not mark owner acceptance PASS from CI, a mock API, model generation, NajdiLab-owned chat or manual import.

## Backup and rollback

This diagnostics-only change adds no schema, cursor, persistent capture consent, imported turns or source snapshots. Use the [Windows update guide](integrations-windows-update.md) for private source/data/consistent SQLite backups and migration review before a later approved pull. Reverting these new commits to the reviewed PR #8 head removes native diagnostics without changing existing data or third-party apps. Do not restore/overwrite a live database or delete data to roll back. Returning to code older than PR #8 can reopen unsafe Hermes ingress; keep that receiver stopped pending the separately reviewed sender/receiver safety procedure. Never change source apps as a rollback shortcut.
