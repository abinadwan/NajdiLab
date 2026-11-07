# NajdiLab V2.3.0 development candidate

Current Documentation — V2.3.0

This minor version adopts the four-stage Guided Wizard as the official data workspace. Its stages are Data, Check and correct, Approve Gold, and Export. Manual editing/history, Gold management, backend guards and supported export formats retain their existing contracts.

Advanced Mode controls are removed from the official shell. A stored historical preference is ignored while workflow drafts and selections remain intact. The preserved launcher, mode controller, styles and specialist panels live in a separate bundle. Existing diagnostic URLs load those panels on demand. A tested temporary restoration procedure is available in the [developer archive](../legacy/advanced-workspace/README.md).

Gold deletion requires exact typed confirmation, current ownership/hash/dependency proof and a preview token. Interrupted deletion is recoverable. Legacy versions without managed-reference ownership proof remain readable/exportable, with permanent deletion refused. A failed handoff publication can leave a conservative dependency reservation.

The application is a review candidate on `update-project`, with PR #23 in Draft. Test results and remaining environment-specific gates are reported in [finalization](V230_FINALIZATION.md) and [the documentation audit](V230_DOCUMENTATION_AUDIT.md). Production, release publication and repository-visibility changes have separate approval scopes.

Historical version numbers and previous measurements remain in the [changelog](../../CHANGELOG.md) and archived implementation records. [Current user guide](../user-guide.md), [permanent screenshots](../screenshots.md).
