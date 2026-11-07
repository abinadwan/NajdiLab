# Contributing

Publication and source-license selection are pending owner approval. Coordinate contributions through the repository's available review channel; do not assume a public redistribution license or contributor agreement exists.

## Local workflow

1. Work in a disposable branch/checkout. Read the [setup guide](docs/installation.md) and [architecture](docs/architecture.md).
2. Keep changes focused and preserve API/data contracts. Record behavior changes and relevant evidence.
3. Run appropriate self-contained tests; for broad changes use `python -m pytest -q tests` with the development pytest dependency installed, and report missing private fixtures separately. `unittest discover` is supplementary because it omits function-style pytest cases.
4. For interface work check keyboard focus, both themes, responsive layout, long technical identifiers and Arabic corpus rendering within the English interface.
5. Submit a reviewable diff explaining the problem, result, checks and material limitations. Use generic paths and synthetic examples.

## Data and execution invariants

Preserve original messages, review overlays, immutable Gold versions, holdouts and historical decisions. Never add real conversation data, credentials, runtime registries, model weights, backup archives or private machine paths. Arabic linguistic examples and protocol tokens should not be translated as interface text.

The application scope is Chat, review and dataset preparation/export. Do not reintroduce internal model training, acquisition, workers, benchmarking or deployment. External engines remain separately managed; migration and installed-update actions require their own explicit scope. Any retained SQL proposals stay outside startup migrations until separately approved; never edit an applied migration or move a proposal into startup migrations as incidental cleanup.

## Tests and documentation

Prefer fixture databases and temporary directories. Do not point tests at production or silently skip failures. Report command, result, platform and missing prerequisites without private logs. Update English documentation when behavior changes, and retain dated design/audit status so proposals are not presented as implemented features.

## Rights and attribution

Read the [inactive contributor/license approval package](docs/proposals/licensing-approval.md) and [source-only data/model policy](docs/dataset-model-distribution-policy.md). No inbound license, DCO or CLA is activated by those proposals.

Identify new dependency versions, upstream licenses and required notices. Confirm rights for code, examples and any dataset; a source license does not license model weights or training data. See [license options](docs/license-options.md) and [dependencies](docs/dependencies-and-attribution.md). Security reports should follow [SECURITY.md](SECURITY.md), with sensitive details withheld from public issues.

## Development standards

Use descriptive snake_case Python names, existing formatting/type patterns and standard-library components where they own the responsibility. Keep browser code framework-free unless a reviewed need changes architecture. Comments/docstrings/UI/docs are English; Arabic processing/test content remains semantically intact. Branches: fix/short-purpose, feat/short-purpose or docs/short-purpose. Commits should describe intent (for example fix: reject stale dataset authorization); never include secrets/private identifiers.

Use a PR to main; no force push, automatic merge or deployment. Reviewers check trust boundaries, data/schema/API compatibility, regressions, English clarity/Arabic direction and rollback. Release versioning, when approved, should use semantic versions with documented compatibility impact. Deprecate APIs in docs/changelog with a reviewed transition before removal; do not rename machine-readable keys for localization. No releases/tags are authorized by this preparation.

Definition of Done: implementation complete; meaningful tests; security impact reviewed; data compatibility confirmed; English docs/status/changelog updated; rollback documented; no secrets/private data; all relevant owner gates respected. Use the PR template. Contributor rights/dependency notices must be cleared before final licensing. Follow CODE_OF_CONDUCT.md.

## V2.3.0 documentation and screenshots

Current guides describe the Guided Wizard and shared APIs. Historical implementation records carry an archive notice and retain their original version numbers/counts. Run `python scripts/check_docs.py` to check repository Markdown/MDX, HTML image references, local anchors and the generated API inventory. Official screenshots must be real synthetic Chromium captures in the permanent versioned asset directory with current-version provenance. Read the [documentation audit](docs/development/V230_DOCUMENTATION_AUDIT.md) and [legacy restoration guide](docs/legacy/advanced-workspace/RESTORE_GUIDE.md) before changing those boundaries.
