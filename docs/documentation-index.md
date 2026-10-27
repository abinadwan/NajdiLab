# Documentation inventory

Current combined work: [unified verification](unified-readiness-verification.md), [release decision](public-release-decision.md), [history review](privacy-history-review.md), [rights matrix](dependency-licensing-matrix.md) and [source-only asset policy](dataset-model-distribution-policy.md).

| Audience | Current English entry points |
|---|---|
| New user | [README](../README.md), [installation](installation.md), [requirements](system-requirements.md), [shell commands](shell-commands.md), [configuration](configuration.md), [troubleshooting](troubleshooting.md) |
| Operator | [security](../SECURITY.md), [Hermes transition](hermes-integration.md), [backup/restore](backup-and-restore.md), [installation proof](installation-verification.md) |
| Developer | [setup](developer-setup.md), [architecture](architecture.md), [code map](codebase-navigation.md), [API](api-reference.md), [route inventory](api-routes.md), [schema](database-schema.md), [migration guide](database-and-migrations.md) |
| Researcher | [dataset/training](dataset-and-training.md), [export](training-export.md), [model selection](model-selection-guide.md), [preflight](training-preflight-runbook.md), [tool protocol](tool-runtime-contract.md) |
| Contributor | [CONTRIBUTING](../CONTRIBUTING.md), [conduct](../CODE_OF_CONDUCT.md), [CHANGELOG](../CHANGELOG.md), issue and PR templates under .github |
| Maintainer | [PROJECT_STATUS](../PROJECT_STATUS.md), [handover](maintainer-handover.md), [worklog](worklogs/english-open-source-readiness.md), [verification](verification-and-readiness-report.md), [publication gates](open-source-readiness.md) |
| Rights/release reviewer | [licenses](license-options.md), [dependencies](dependencies-and-attribution.md), [inactive NOTICE proposal](proposals/NOTICE.txt), [GitHub presentation](github-presentation.md), [Arabic exceptions](arabic-localization-exceptions.md) |
| Historical/design evidence | [engineering record](historical-project-status.md), [board](master-execution-board.md), [Corpus v1.1 approved design](corpus-v1.1/README.md) |

Historical documents are preserved dated snapshots. PROJECT_STATUS reconciles them; an old approval/status is not a new action grant. Arabic linguistic examples remain intentional and provisional where specified. No private artifact/evidence location is part of public documentation.

## Visual and practical navigation by audience

| Audience | Additional entry points |
|---|---|
| New users | [Practical user guide](user-guide.md), [screenshots](screenshots.md) |
| Reviewers | [Correction walkthrough](user-guide.md), [review screens](screenshots.md) |
| Researchers | [Diagram gallery](architecture-diagrams.md), [source provenance](source-provenance.md), existing historical/design evidence above |
| Dataset curators | [Data/storage architecture](architecture-diagrams.md), [dataset guide](dataset-and-training.md) |
| Model-training operators | [Training boundary](architecture-diagrams.md), [existing preflight](training-preflight-runbook.md) |
| Developers | [Editable diagram and maintenance](architecture-diagrams.md), [architecture](architecture.md) |
| Maintainers | [Visual verification/no-loss evidence](visual-documentation-verification.md), [asset register](asset-provenance.md) |
| Contributors | [Source provenance](source-provenance.md), [contribution standards](../CONTRIBUTING.md) |
| License and security reviewers | [Third-party attribution](third-party-attributions.md), [assets](asset-provenance.md), [release decision](public-release-decision.md), [SECURITY](../SECURITY.md) |

These pages extend navigation; they do not replace existing status, technical references, historical reports or ADRs.

## Source-only candidate engineering

Developers/maintainers: [public/private boundary and blocked compatibility patch](public-private-boundary.md), [exact-candidate build/test/release report](public-source-isolation-report.md). These extend, rather than replace, the original architecture/status and PR #2 documentation.

## Public core scope review

Owner/product reviewers: [original-versus-candidate feature, UI, module and API matrices](public-core-feature-parity.md), [recommended first-release scope, approval gates and prioritized backlog](public-core-release-scope.md). Developers should use the proposed B02–B06 next phase only after scope approval. This analysis does not migrate features or change the two existing Draft PRs. Original-interface guides/screenshots/architecture above describe the private full application; the mapped candidate has a smaller interface.

## Public core Phase 5 engineering

Current implementation reviewers/developers: [milestone execution and rollback](public-core-phase5-execution.md), [finding register](public-core-phase5-issue-register.md), [actual verification evidence](public-core-phase5-verification.md). This candidate-only work continues the approved scope without modifying original code or earlier Draft PRs.
