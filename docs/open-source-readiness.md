# Open-source publication readiness

Decision: **NOT READY — BLOCKERS REMAIN.** English-readiness work is a reviewable preparation branch, not publication, merge, deployment, a history rewrite or a license grant. Private production and backup state remain outside this work.

## Publication gates

| Gate | State | Required closure |
|---|---|---|
| English application/documentation | Verified in development; publication gates remain | See verification-and-readiness-report.md and the Arabic exception inventory |
| Source license | BLOCKED | Owner selects license and copyright attribution; confirms authority over contributions |
| Reachable Git history | BLOCKED | Owner explicitly decides how to handle historical personal identifiers, machine paths and operational/backup disclosures; document review of all publishable refs |
| Tracked data-bearing source | BLOCKED | Determine rights/privacy disposition of historical corpus/review corrections embedded in source; preserve their content pending owner decision |
| Data/model/dependency rights | OPEN | Exact artifact/version review, data consent/provenance and distribution notices |
| Ingest migration | PREPARED ONLY | Configure a private shared secret in the target instance and collector before controlled deployment; verify compatibility without exposing it |
| Public test strategy | VERIFIED with explicit historical limits | 278 source-only tests pass; 23 historical checks explicitly skip missing private artifacts; full authorized-fixture run passes 301 tests. Never count skips as historical proof |
| Operational readiness | OPEN | New development evidence does not authorize production deployment; configure/verify the intended runtime separately |

Current-file sanitization cannot erase values in prior commits, tags, branches, logs or archives. `.gitignore` cannot remove tracked material. Do not make the repository public or upload a full archive based on a clean working-tree text scan. Preserve private evidence and obtain the owner's explicit disposition; this branch performs no history rewrite or data deletion.

## Intentional Arabic

Keep actual Arabic corpus/review content, provisional Riyadh Najdi word lists and linguistic examples, tokenizer/template markers and protocol data unchanged. English explanatory prose describes those examples. Corpus linguistic lists remain provisional until native validation (PRQ-LANG-01); translation work cannot validate their correctness or rights.

## Historical versus current state

Dated audits, ADRs, approval packages and the [historical project record](historical-project-status.md) preserve engineering decisions and measured counts. Their statuses apply to those dates. The Corpus v1.1 design was approved without implementation authorization; the historical rejected adapter and blocked model release remain evidence. Current request-hardening behavior is documented in [SECURITY.md](../SECURITY.md); old security threat tables are historical baseline evidence.

Review [license choices](license-options.md), [dependencies](dependencies-and-attribution.md), [contributing](../CONTRIBUTING.md) and the branch worklog before any owner publication decision. Sensitive audit details belong in private evidence, not public documentation.

Current branch evidence: [verification report](verification-and-readiness-report.md) and [Arabic exceptions](arabic-localization-exceptions.md).

Current multi-track state: [PROJECT_STATUS](../PROJECT_STATUS.md). Full installation/handover package: [documentation index](documentation-index.md). Conduct/security reporting contacts and exact distribution notices require owner designation before public launch.
