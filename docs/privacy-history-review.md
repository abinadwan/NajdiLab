# Privacy and Git history review

Review date: 2026-10-27. Baseline source: `ae0ebb634459a8cadb742143a49f65c755f2b290`. Verdict: **NOT READY — BLOCKERS REMAIN**.

## Scope and evidence handling

A real clone was inspected with `git status --short --branch`, `git rev-parse HEAD`, `git fsck --full`, `git for-each-ref`, `git rev-list --objects --all`, `git cat-file` and a tracked-file inventory. The initial development checkout was clean. Remote PR #1 had already been merged and the development branch deleted before this task; local branch restoration at the supplied SHA does not change main. Production and other developers' working trees are inaccessible here; the historical live uncommitted-work reconciliation remains unresolved.

The fetched refs contain main and PR #1's retained head. Their reachable graph contains **7 commits and 328 distinct blobs**. All blobs were inspected as UTF-8 text where possible; the one JPEG was visually reviewed. A SHA256 baseline covers **224 tracked files**, including the JPEG. Private evidence is outside the checkout in an owner-only directory (directory mode 0700; evidence files 0600). It contains exact findings and commit identities; never attach it, test logs or a full repository archive to public issues. This report contains only redacted references and classifications.

Pattern scans cover absolute Windows/home paths, backup references, emails and common token/private-key formats, supplemented by source/data review. No credential candidate matched those particular patterns; this is not a complete secret audit or proof that arbitrary free text contains no secret. Numeric IDs, names and Arabic text require contextual review. GitHub settings, deleted/unreachable objects, caches, old clones, Actions logs/artifacts and external backups are outside the complete-enumeration claim.

## Findings and classification

| Evidence | Classification | Finding and disposition |
|---|---|---|
| PRIV-01 | Contains real personal information; requires owner review | **26** personal Windows-directory matches in historical blob versions. Affected historical scripts include audit/overlap/influence utilities, launch/backup helpers and a training-plan test. Do not reproduce directory identities. Not found as personal Windows paths in current source. |
| PRIV-02 | Contains private operational details | Historical backup guidance discloses a local backup location. One location-bearing regex match is independently confirmed. The earlier report's two backup-location matches are **not independently reproduced as two distinct disclosures**; the broader regex also matched a harmless loopback URL. No backup was accessed. |
| PRIV-03 | Requires owner review | Author/committer identity metadata remains in reachable commits. Approval to publish a GitHub handle is not blanket consent to publish every historical identity/address. Preserve attribution privately and obtain a specific public attribution decision. |
| PRIV-04 | Requires owner review | Three historical non-generalized home-path scan matches need owner disposition. Current `/home` examples use the generalized project account, not verified production paths. |
| PRIV-05 | Public-safe | Current generalized Windows/home examples, a deliberately missing test path, loopback URLs and synthetic credentials/phone sentinels. A broad path match alone is not personal information. |
| PRIV-06 | Must not be distributed by default | Real correction manifests, reviewer annotations and historical repair/evaluation source; see [distribution policy](dataset-model-distribution-policy.md). Rights/consent and separation remain blocked. |
| PRIV-07 | Needs generalization or exclusion; requires owner review | Corpus-specific identity/search terms in analytical scripts may reveal research subjects or link records. Do not replace them inside protected evidence; exclude or author independent public analytics. |
| PRIV-08 | Public-safe within reviewed scope | Linguistic dictionaries, compatibility enums, independently synthetic Arabic tests/demo content, and the synthetic UI screenshot. JPEG visibly contains a generic Arabic text-storage example; no EXIF APP1 block was found. This does not establish copyright provenance of all frontend work. |
| PRIV-09 | Requires owner review | Operational architecture/resource observations in dated engineering documents. Generalized text is not evidence that all operational context is approved for public release. Include all documentation in the final manifest review. |

Across the distinct-blob scan there were 31 Windows-path candidates: 26 personal historical matches and five generalized/test matches across versions. There were 90 home-path candidates, of which three need owner review; remaining matches use generalized examples. Counts are matches across unique blob versions, not distinct people, commits or current files. Current files have three Windows-path and 36 home-path matches, all generalized/test examples. Pattern counts will change when documentation adds new examples; they are not a durable privacy allowlist.

No tracked database, JSONL corpus, model weight/checkpoint, archive, environment secret file or generated ML cache was found by the baseline filename scan. Embedded real data in Python defeats any conclusion based only on extensions. `.gitignore` is a preventive control, not erasure.

## Publication strategy comparison

| Strategy | Remaining exposure | Attribution/provenance | Contributors/clones | Rollback and approval |
|---|---|---|---|---|
| A. Keep existing history after authorized remediation | Latest-file cleanup retains old values. Safe only if every retained disclosure is specifically cleared, or sensitive reachable history is separately removed (then this becomes C). | Best direct commit lineage; metadata privacy still needs consent | Least disruption if history unchanged; existing clones retain everything | Simple code revert, but public disclosures cannot reliably be recalled. Owner must approve every retained disclosure and all publishable refs. **Not recommended with current blockers.** |
| B. New clean source snapshot | Can omit old history and protected files; current source/docs still need full review. Does not erase copies or make the existing repository safe to publicize. | Keep original-repository credit, owner-approved copyright and a private snapshot-to-source hash manifest; no fabricated author lineage | New public lineage; private contributors retain original repository; explain the split | Preserve private repo unchanged; rebuild a candidate snapshot. Exposure after publication remains hard to recall. Owner approval required for exact source manifest, attribution, rights and new public destination. **Recommended.** |
| C. Reviewed history rewrite | Can remove targeted reachable objects; missed refs, PR refs, caches and clones can retain disclosures | Rewrites commit IDs; preserve approved credits and a private mapping; signed commits may lose validity | Coordinated contributor re-clone and branch cleanup; stale clones can reintroduce data | High complexity; private mirror/backup and rehearsal required. Explicit owner approval for rewrite, force-push and hosting-provider cleanup; none authorized here. |

Recommendation B is a proposal only. No history rewrite, force-push, commit deletion or public repository creation was performed. **Sanitizing the latest files does not remove information accessible through earlier commits.** Making this existing repository public would expose its reachable historical data. A clean snapshot must be published separately only after data/rights/license gates close; it must not carry `.git` or private audit evidence.
