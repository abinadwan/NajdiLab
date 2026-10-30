# User guide — a fictional card workshop

This guide is for the **generated Core candidate**, not the original full application. Use its [README](../README.md) to build, install and explicitly create the 32-row workshop in fresh disposable storage. All examples are independently fictional Arabic/Najdi card-workshop conversations. Automated test decisions are demonstrations, not genuine research review evidence.

| Step | Action | Expected result / evidence |
|---|---|---|
| Open | Launch and open loopback URL; read Overview | Real local counts, no model/runtime dependency; [overview](images/overview.png) |
| Inspect | Open Conversations, search and choose a conversation | User question, context and immutable original; [review](images/conversation-review.png) |
| Correct | Open its review, enter a separate complete correction, inspect loaded flags and notes | Original stays read only; retained correction is prefilled; [editor](images/correction-editor.png) |
| Choose flags | Explicitly mark privacy/evaluation/exclusion or training eligibility after review | Editing text alone never clears restrictions. A restricted row stays out of training; [saved decision](images/saved-decision.png) |
| Resolve conflict | Have another client save the same revision, then attempt your stale save |409/no writes, draft retained, explicit reload and comparison; never silently retry with a new token |
| Exclude/restore | Enter a reason and select Exclude or Restore | Correction preserved; restore is pending/ineligible with restrictions retained. Resolve a retained pending correction explicitly before re-exclusion |
| Finish review | Resolve each intended synthetic record; approve only after inspection and select eligibility deliberately | Pending, excluded and evaluation filters remain inspectable. The workshop never approves itself |
| Check readiness | Open Dataset readiness; explicitly Include synthetic demo | At least20 final records, three holdout conversations and10–15% split; blocker and duplicate/holdout evidence; [readiness](images/dataset-readiness.png) |
| Prepare | Select Prepare a new local version and confirm | A new local version, not training/publication; [version](images/dataset-version.png) |
| Inspect quality | Open file/hash, health, quality, balance and holdout evidence | Actual findings, no fabricated model metrics; [quality](images/quality-findings.png) |
| Retrieve | Select a listed JSONL file and acknowledge privacy warning | Attachment matches its manifest SHA256; full archive/DB/secret/model access denied; [artifact access](images/artifact-access.png) |
| Recover | Run coherent backup and validate separate restore | Original messages, correction overlays, flags, manifests and hashes preserved; see [README recovery](../README.md#backup-and-separate-restore) |

The screenshot scenario adds a few fictional card examples to the workshop. One intentionally contains HTML-like text to demonstrate inert rendering; it is not a script running in the page. A personal-information flag is deliberately toggled on a fictional record to demonstrate preservation; it is not a real person's information. The valid version is prepared from the remaining eligible fictional records. No private research data, actual model evaluation, training, adapter or production system is used.

A new version does not retroactively change older artifacts. The private full archive contains the dataset's original local recovery snapshot, including excluded records; never upload it. Review/quality PASS and file hashes do not establish rights or consent. This guide demonstrates implemented core behavior only; generic model configuration, training and historical research remain unavailable.
