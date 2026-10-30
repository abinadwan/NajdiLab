# Maintainer handover

Start at [PROJECT_STATUS](../PROJECT_STATUS.md). Current authorization is private preparation, not Corpus implementation, production deployment or training. Fresh combined proof is in [unified verification](unified-readiness-verification.md); earlier [verification](verification-and-readiness-report.md) is historical.

1. Clone the original private repo using your own authorized GitHub credentials and select the default `main` branch (the former preparation branches were merged through PR #5 and deleted on 2026-10-30). Record `git rev-parse HEAD` and `git status`; preserve all local work.
2. Review setup scripts and follow [installation](installation.md). Core app needs no third-party package or Hermes/Ollama; setup is offline after clone and preserves state.
3. Select a free loopback port, launch this checkout, verify health/database identity. Ctrl+C stops only this terminal instance; never test on live data.
4. Follow [developer setup](developer-setup.md), run pytest -rs and read failures/skips/warnings. Private historical checks need authorized restoration; never publish fixtures.
5. Read [architecture](architecture.md), [code map](codebase-navigation.md), [API](api-reference.md), [database](database-and-migrations.md), [training](dataset-and-training.md) and [security](../SECURITY.md).
6. Next work is owner review/license/history-data disposition. Corpus 1A, loader guard, 005–008, adapter reconciliation, downloads, training and deployment retain separate OA/PRQ gates.
7. Reproduce checks with temporary synthetic state/free ports and documented commands. Keep protected hashes privately. Do not promote historical evidence into fresh claims.
8. Create a focused fix/ or feat/ branch; reproduce defect, modify owning layer, preserve contracts, test rollback and review subprocess/path/SQL boundaries.
9. Update WORKLOG during execution plus PROJECT_STATUS, relevant English docs and CHANGELOG. Keep dated snapshots rather than rewriting historical decisions.
10. Check staged files for secrets/private content; submit PR with actual checks/limitations/gates and rollback. No automatic deployment/merge/publication.
11. Recover using ordinary revert for source plus separate verified private state restoration. Rehearse in a fresh directory; no force push/history rewrite/restore-over-live.

Apache-2.0 is owner-approved as the **future Core target** (2026-10-28), not an active license; copyright-holder/scope/notice adoption remain unapproved. History and real curation/evaluator source need privacy/rights disposition. Exact transitive/model/data/asset rights remain incomplete. CSRF is not RBAC; loader is unguarded; adapter drift, mobile matrix and native-Linux breadth remain. After owner disposition, plan deployment/auth transition separately, then ask for a scoped Corpus baseline/loader task if desired. Rejected adapters/holdouts remain immutable evidence.
