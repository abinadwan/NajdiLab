# Phase5 exact-candidate rights and publication decision package

Date: 2026-10-27. **NOT READY — BLOCKERS REMAIN**. This is an inactive decision package, not a license grant. The engineering candidate can work while ownership, attribution, privacy and publication approvals remain open. No model/data rights are inferred from framework terms or successful tests.

## Exact scope and evidence

Reviewed implementation: `ea2347ffb6fd0cf2ed0549a87e854a4609450104`. The source-only profile selects **74 files** (plus generated MANIFEST.json): 28 preserved generic project paths and 46 candidate-specific code/test/document/asset paths. Canonical UTF-8/LF text and exact PNG bytes are pinned; the private original raw hashes are separate. Manifest SHA256: `eabd5ba88e8a516c11b5e1d1fe384f7fd56f4b01d6413ed85af74aeb970c637e`. The inventory below records exact source/destination/hash coverage. A changed selected byte requires rebuilding and reviewing this evidence; a root report-only update does not change selected bytes.

A disposable clean snapshot was built and verified outside the checkout, with only selected files and manifest, no Git history, private evidence, DB, generated dataset, model, adapter, checkpoint, archive or active LICENSE. Two-build byte determinism and tamper/import/path checks pass. No package was uploaded. This demonstrates a technically inspectable snapshot; it is not permission to distribute it.

## Independent gates

| Gate | Current result | Smallest safe next action |
|---|---|---|
| Deterministic technical package | PASS within exact tested profile | Rebuild/verify exact final approved manifest after any change |
| Bounded path/credential scan | PASS: zero candidates for the documented patterns | Owner contextual review; scans cannot prove arbitrary text safe |
| Embedded real records/private imports | No protected records/modules selected; synthetic fixtures independently fictional | Owner review selected generic source and residual legacy labels |
| Ownership and contributor authority | AWAITING_OWNER_APPROVAL | Confirm original/employer/contributor/borrowed-code rights for each selected path |
| Source license / holder / year | AWAITING_OWNER_APPROVAL | Complete inactive fields and approve exact scope/standard license |
| Third-party redistribution | NOT_VERIFIED for any future bundled runtime/binary | Keep runtimes external; inventory exact artifacts and notices if scope expands |
| Asset redistribution | AWAITING_OWNER_APPROVAL | Approve underlying UI/source and original SVG/capture distribution rights |
| Existing historical Git privacy | BLOCKED | Keep original repository Private; separately authorize clean-snapshot publication strategy |
| Public destination / publication | AWAITING_OWNER_APPROVAL | Approve exact manifest, notice bundle and destination only after all gates close |

## Source ownership/provenance assessment

Preserved generic application modules, migrations, wrappers and two original tests are traced to the private NajdiLab tree by policy and baseline hashes. This establishes repository origin, **not independent authorship or authority to license**. No copied/adapted third-party source or bundled external UI asset was confirmed in the selected bytes; notice/header/origin searches found no claim establishing one. Absence of a header and source similarity are not proof of originality. Existing [source provenance](source-provenance.md) and [dependency research](dependency-licensing-matrix.md) remain historical evidence, not universal clearance.

New wrappers, UI, tests, synthetic fixture generation, guides and original geometric SVG/generator are AI-assisted engineering additions. Owner must assess contribution/employer/tool-input authority; generated code does not establish a third-party license or solve underlying project ownership. Existing upstream/source comments are preserved. Browser screenshots are actual fictional-data UI captures, not generated dashboard artwork; underlying UI rights remain pending. No external icon pack, font binary, library JS bundle, model template or tokenizer is included. [Asset register](asset-provenance.md) identifies each SVG/PNG and its creation source.

Residual historical naming is explicit: the unchanged generic `scripts/select_v007_windows.py` is imported for pure window-selection helpers by dataset_platform. It retains a v007 label, numerical defaults and candidate-relative optional CLI paths. It contains no original conversations/evaluation annotations, performs no import-time reads and is not executed during install/startup. Those labels/configuration are **OWNER_REVIEW_REQUIRED**, not certified anonymous research metadata. If unwanted in a future public snapshot, prepare a tested candidate-only generic helper replacement; never edit the protected original silently. The source-only manifest itself contains no commit-author metadata or original Git objects.

## Runtime/development dependency and notice matrix

Matching tagged source license text was freshly retrieved through GitHub on 2026-10-27. These are source-text checks, not provenance certification of a wheel, OS package or compiled runtime. Nothing below is vendored into the candidate merely because code imports a standard module or test script requires a tool.

| Component / origin | Exact evidence / usage | Matching license evidence | Redistribution/notice conditions and uncertainty |
|---|---|---|---|
| [CPython](https://github.com/python/cpython) | Local3.12.14; HTTP/JSON/sqlite3/path/venv standard library, installed externally | [v3.12.14 LICENSE](https://github.com/python/cpython/blob/v3.12.14/LICENSE), Git blob `f26bcf4d2de6eb136e31006ca3ab447d5e488adf`: PSF terms and historical notices | Preserve applicable license/copyright and modification summary if distributing Python; no interpreter binary is shipped. Exact hosted runtime/native notices NOT_VERIFIED |
| [SQLite](https://github.com/sqlite/sqlite) | Local linked3.53.1 via sqlite3; enforced minimum3.24 | [version-3.53.1 LICENSE.md](https://github.com/sqlite/sqlite/blob/version-3.53.1/LICENSE.md), blob `5f59bb8fefd54767e2eb08a17d0dc19007958d90`: public-domain statement | No SQLite binary/extension bundled; exact runtime build provenance/extensions/jurisdictional assurance NOT_VERIFIED. Matching source statement is not a binary bill of materials |
| [pytest](https://github.com/pytest-dev/pytest) | requirements-dev9.1.1, separately installed test runner; prohibited as runtime import | [9.1.1 LICENSE](https://github.com/pytest-dev/pytest/blob/9.1.1/LICENSE), blob `c3f1657fce94589bd1ec7cead810639047f3d359`: MIT | Retain copyright/permission if redistributed; native/transitive environment not bundled/cleared |
| [puppeteer-core](https://github.com/puppeteer/puppeteer) |25.16.0 actual browser automation, separately installed; source CJS harness only shipped | [puppeteer-core-v25.16.0 LICENSE](https://github.com/puppeteer/puppeteer/blob/puppeteer-core-v25.16.0/LICENSE), blob `d2c171df74e931892e20f9395041bf8529e45330`: Apache-2.0; installed package metadata matches version/license | License/notices/modification terms apply if redistributing tool; package/transitive audit remains NOT_VERIFIED. No node_modules or Chromium bundled |
| Node / Chromium / hosted browser | External test execution only; version/runtime observations belong to verification | Full selected binary/transitive notice inventory NOT_VERIFIED | Do not redistribute browsers, fonts or Node binaries based on this report. Browser raster captures are distinct from shipping font/browser code |
| GitHub Actions checkout/setup-python/setup-node | External CI service actions at v4/v5/v4 major refs, not source bundled | Exact immutable action/transitive verification NOT_VERIFIED | Consider independently reviewed immutable action pins; no change to repository security settings implied |
| ML/GPU/model/integration stack | PyTorch, Transformers, Unsloth/core/zoo/Studio/CLI, PEFT, Accelerate, bitsandbytes, NumPy, safetensors, HF Hub, CUDA/NVIDIA, Hermes/Ollama/llama.cpp | **Excluded**, existing [matrix](dependency-licensing-matrix.md) / [attributions](third-party-attributions.md) retain earlier exact/discovery evidence and uncertainties | No blanket legal clearance; optional AGPL scope cannot be called Apache. No import/runtime/model artifact selected; adding one requires new exact-artifact review |

Current stdlib-only application source does not inherit an ML framework's distribution terms because that framework is absent. Conversely, excluding a runtime does not clear any copied application source. Commercial use under a proposed permissive source license remains contingent on actual ownership/licensing, and never licenses private data/models.

## Owner decision fields — inactive

- Public copyright holder/entity: **[OWNER MUST CONFIRM]**. A repository account is not a legal ownership declaration.
- Copyright year/range: **[OWNER MUST CONFIRM]**, not inferred from commit or report date.
- Authorized source scope: **[APPROVE EXACT MANIFEST SHA256 AND ALL SELECTED PATHS]**.
- Original/employer/contributor/borrowed-source authority: **[EVIDENCE REQUIRED]**.
- Standard source license: **[APPROVE APACHE-2.0 OR SELECT ALTERNATIVE]**.
- Third-party/source/asset notice bundle: **[CONFIRM APPLICABLE CONTENT]**.
- Public attribution identity/repository wording: **[APPROVE]**.
- History strategy/destination/publication: **[SEPARATE EXPLICIT APPROVAL]**.

The existing [Apache proposal](proposals/LICENSE-Apache-2.0.txt), [NOTICE proposal](proposals/NOTICE.txt), [approval guidance](proposals/licensing-approval.md) and [MIT/BSD comparison](license-options.md) remain inactive and outside the candidate; no root LICENSE/NOTICE has been activated.

Apache-2.0 is recommended: free/commercial use, modification and redistribution subject to its conditions; express limited contributor patent grant with specified litigation termination; no warranty/liability provisions. Derivative distributions include the license (§4(a)), identify changed files (§4(b)), retain relevant source notices (§4(c)), and reproduce applicable NOTICE attribution in one of §4(d)'s allowed locations. A NOTICE cannot add restrictions or grant trademark endorsement. MIT preserves copyright/permission notices; BSD-3-Clause adds source/binary notice and non-endorsement terms; neither has Apache's express contributor patent grant. Compatibility must be checked for the actual combined work, especially GPLv2-only/AGPL and vendor/model terms.

Proposed attribution, **only after approval**:

> Original project: NajdiLab. Original source: https://github.com/abinadwan/NajdiLab. Copyright [OWNER-CONFIRMED YEARS] [OWNER-CONFIRMED HOLDER]. Preserve applicable license, copyright and NOTICE attribution; identify modifications. Third-party materials and separately supplied data/models retain their own terms. No endorsement is implied.

Recommended voluntary README/About credit: “Based on NajdiLab — https://github.com/abinadwan/NajdiLab.” Apache-2.0 does not universally mandate a homepage backlink or particular About screen. Stronger mandatory advertising credit would require separately assessed custom terms and may reduce open-source compatibility; none is activated. Contributor guidance requires authority/origins; optional DCO/CLA/inbound rules are owner decisions, not retroactive rights evidence.

## Dataset/model rights and exclusions

Synthetic examples are independently fictional, clearly labeled and opt-in; permission to redistribute the actual fixtures/UI still belongs to the source/asset decision. Original conversations, human corrections/annotations/evaluations, frozen Gold v008/v009, research evidence, checkpoints/adapters, base/merged/quantized models, tokenizers/templates and training outputs remain excluded/private. Rights for those are **NOT_VERIFIED**. Possession, ability to train, permission to use/train, copyright ownership and permission to publish/redistribute are different. Consent, provenance, privacy/copyright, access/model license and derivative restrictions require separate evidence. Generated local dataset/backup files may contain private information and never become distributable merely because SHA/integrity checks pass.

## Clean-snapshot strategy and rollback

Recommend strategy B: retain the original restricted repository/history unchanged and, only after all independent approvals, publish a separately reviewed clean source snapshot from the approved allowlist. The local disposable snapshot proves omission of Git; it does not execute public publication, erase old disclosures or make the existing repository safe to change visibility. Keeping uncleared history retains exposures; rewriting history disrupts clones/IDs and cannot erase external copies. Neither was performed. [Historical comparison](privacy-history-review.md#publication-strategy-comparison) remains applicable; new source cleanup cannot remove earlier commits.

Rollback: forward-revert candidate commits/pins/docs as a reviewed unit, retain all private originals/data/backups and earlier Draft PRs; rebuild into another new directory. Never reset/force-push, rewrite history, overwrite a live DB or silently activate license terms. Reopening a technical gate after changed bytes does not close ownership/publication decisions.

## Exact selected-file inventory

Origin categories: **O** = preserved original-project source, authorship/rights NOT_VERIFIED; **C** = candidate-specific AI-assisted addition, owner authority/redistribution AWAITING_OWNER_APPROVAL. Source hashes are canonical text or exact PNG; source path mapping preserves the protected original rather than overwriting it.

| Engineering source | Candidate destination | Origin | SHA256 |
|---|---|---|---|
| .env.example | .env.example | O | `5644f61c1ba5f91b9e245352b0a0ec2bd1a1afbd58547d52b38d86907055b6b4` |
| .gitignore | .gitignore | O | `578ac7650c23f3584956a5129fb88402e2032d757a5c790439774e34d08084eb` |
| app/__init__.py | app/__init__.py | O | `8900ed8a83d6e23ce60b5fa26854c3ebf74c2bf90eb23bf628d10b306888ede7` |
| app/clean_export.py | app/clean_export.py | O | `db6adb31f9970f58c186407fda8d360e6bb9175afef0f5c765ad8410fe0d1f77` |
| app/dataset_balancer.py | app/dataset_balancer.py | O | `27448d307a8706ac5c4ac30723d5b1a497da0a2289cc562793ec40dc24fd84e3` |
| app/dataset_platform.py | app/dataset_platform.py | O | `58712351a96b56a0ec631600a6646bf026b1027d7e32474ff234681e72ecf2a2` |
| app/dataset_quality.py | app/dataset_quality.py | O | `047cf004dac322fedc039b15e8601fc622e509437b20b0049c4b8652ce4fc187` |
| app/db.py | app/db.py | O | `0124721c461f3bf65c68651e15e5a13336cd35ef4bfc013fa43de711ec942bae` |
| app/evaluation_guard.py | app/evaluation_guard.py | O | `2f6c3bb6a0e55582f850278fc4e45313afb41a6e150d18e4c4ddf76ccc8629ef` |
| app/http_security.py | app/http_security.py | O | `75b729b35c4127ad97996a05b99234338315e9b6a30ac0d7a6c2864eefb0343e` |
| app/review_integrity.py | app/review_integrity.py | O | `1a94367c9a9f87b3dc9472f69a1182834199b69fb936078bb3a095700231cd8f` |
| app/review_lifecycle.py | app/review_lifecycle.py | O | `eff2930396074b17280c250107a2eaa8e7e53203d1d3ad78ecf328274eb37cad` |
| app/service.py | app/service.py | O | `07dabe17178eac419a5c2d6eaeb969fa7c34ccbd5d00dd5db17358be3cac0ec8` |
| migrations/001_initial.sql | migrations/001_initial.sql | O | `b42c3dd9059ab2556fb0560d593c9cc0d51f84ebaff361b275e24e37a5d1db7d` |
| migrations/002_hermes_idempotency.sql | migrations/002_hermes_idempotency.sql | O | `46197b8ad158ea5df989c0d80cca810285de4186415e6f2b551ec622d4ff1020` |
| migrations/003_manual_data_manager.sql | migrations/003_manual_data_manager.sql | O | `8001ab0ac2b76d5bceca50161796fd14dc1d298fd655a1f6984751aa6e9a10b0` |
| migrations/004_review_lifecycle.sql | migrations/004_review_lifecycle.sql | O | `92290af7684d75f181a0a489567a75ffb236f3944db03fe2b317cd0d22d6079e` |
| public_source/CONTRIBUTING.md | CONTRIBUTING.md | C | `e6eb14fd2655c05657c96560a01fa435be784c261c01a790d729e2d366797f99` |
| public_source/README.md | README.md | C | `49b95b31149348fb07113b63569a5e353eae8ed32147f48c988917fe32303ea4` |
| public_source/artifacts.py | app/core_artifacts.py | C | `8e1530921bdf6324bff167f13a09bdc7fbb9d7dc31b69be95c208d42c3e12276` |
| public_source/backup.py | scripts/backup.py | C | `e325c1ea377f8651c734f7c8244abbda20d578e4a25324b3ffa8a39f81799589` |
| public_source/datasets.py | app/core_datasets.py | C | `244d054d0bb5ea1cec3612cb5460fc193874102c47d1951ec7926b70a0bb844f` |
| public_source/docs/api.md | docs/api.md | C | `6a2e84fbf59efd0884bd184a4ccb30d9c4f978965240dda78aa83b0327717aab` |
| public_source/docs/architecture.md | docs/architecture.md | C | `6eb1ff769ba9de664224f288551dc35c3d1457d361997653d3e0ec728767d4ef` |
| public_source/docs/generate_architecture.py | docs/generate_architecture.py | C | `c8154c5aaf5b5b1e2bf2e14ea3536bbe54c70cb62b46673d17adb9fb2e0b1883` |
| public_source/docs/images/artifact-access.png | docs/images/artifact-access.png | C | `4da591031168a6776a2c3b29e8e869ca8067d71b92c04ea460f97b28140e6c54` |
| public_source/docs/images/conversation-review.png | docs/images/conversation-review.png | C | `4982f2ecb60ea94d4f12beefc4ace7678480a74eec1ef179de6b7735def25e89` |
| public_source/docs/images/core-architecture.svg | docs/images/core-architecture.svg | C | `dc5ed76f2d11a1d8385cde2693da4e73859933a6f738a5128b3486be0aeba256` |
| public_source/docs/images/correction-editor.png | docs/images/correction-editor.png | C | `8de5ca5c112f5980b17bc658a6f306cbdc959e3c2ad879c02c4453f9eb81d0b2` |
| public_source/docs/images/dataset-readiness.png | docs/images/dataset-readiness.png | C | `d2dbba57008b34611f03b16faae22f808cdcc48a17e32905d255efc619dd77e7` |
| public_source/docs/images/dataset-version.png | docs/images/dataset-version.png | C | `4d59082390c00675ade069d2799d6d78d5d017a1cbf4b9af3f0ab1ca482fa9e3` |
| public_source/docs/images/overview.png | docs/images/overview.png | C | `f868af7cc294fe17ba284ceefa9d263ba28460257e8e235a7322c65083f5ff93` |
| public_source/docs/images/quality-findings.png | docs/images/quality-findings.png | C | `6e7de373455ab38eee1239ef768ef2adec9e0451b9caa3da35b5796b5e48ea6a` |
| public_source/docs/images/saved-decision.png | docs/images/saved-decision.png | C | `adb1a9f4125bd81a775e10fd1fe2469a6081eaed6d2c6274c3945db5f905ff3c` |
| public_source/docs/initial-profile.md | docs/initial-profile.md | C | `805ae99aed467c62f820fa8361b80ec2e139d62f9b019e5a9a945075010e2230` |
| public_source/docs/screenshots.md | docs/screenshots.md | C | `71c4c1df33fbc69df9ae1fe4ebe9e4636e1527afb45471023d7c741633b31361` |
| public_source/docs/user-guide.md | docs/user-guide.md | C | `91275427e647af8392f7d2f8a54e0baa8724411268d79419cf73ca36354d8a94` |
| public_source/extensions.py | app/extensions.py | C | `2539f07efe87a6763ce928ea4271603cc7aa6961766eb4a4d4e36e494fc81467` |
| public_source/read_views.py | app/core_views.py | C | `8bcd67410b4e3fdd45d41100ae6297e0cd2847c99cf136f0905d084d565d9d55` |
| public_source/restore_backup.py | scripts/restore_backup.py | C | `88f457d712b89521f4b03e56bd556833b456ead8b8c061bd8185956c2fd90a37` |
| public_source/reviews.py | app/core_reviews.py | C | `6a0852b54ef3eee6253520dcc83380a2de045aa825f72133f5af0a7778a2bc4d` |
| public_source/server.py | app/server.py | C | `84f496a38c43e5104a4f585a3afbaaf24d1e4c985fb56dca300e67c2d34ac84d` |
| public_source/snapshot.py | app/core_snapshot.py | C | `eb0a8bd53df885bba87621375f6e806398cbc14c8b9504ba0a82eda2f4878fbb` |
| public_source/static/app.js | static/app.js | C | `2fe00c8f2428be7c86a608030214a88fe7293ece74458212fc3628f8986c92a0` |
| public_source/static/index.html | static/index.html | C | `a7cae133021c412352f1de3f77554ed0d4e0b1e60fb51f8f7f48e6cfa24385ba` |
| public_source/static/style.css | static/style.css | C | `1bd0e885c9e30f1abdeb596a79d236b67005ff614d64986c2646de08ee52c5ae` |
| public_source/storage.py | app/core_storage.py | C | `0d00ef72d0bb7ca11062311d582cf90f0c254a7e1381e77729251ad652b6dc5b` |
| public_source/synthetic.json | synthetic.json | C | `21b7807ac2e8762b12ead29d83028c0b258a9f0e360fedc1c9def0e0df60f748` |
| public_source/synthetic_demo.py | scripts/synthetic_demo.py | C | `48148460b1acd28eba8dc41b48b88aed8dc3c72097a0c214c001d4d667aef442` |
| public_source/synthetic_workshop.json | synthetic-workshop.json | C | `dba18fecc6dd731b889e8be3190523ea1e84a59ff6988e974b9deb5da3863305` |
| public_source/tests/__init__.py | tests/__init__.py | C | `7e22133fb1639284bd74d15745e49ed1a282136eed011467a6ed013b8c12b7cb` |
| public_source/tests/artifacts.py | tests/test_candidate_artifacts.py | C | `0081fd4b1eb5b9946187a05b33fcd95f431f14b2573375cc69b5803b4fdce26a` |
| public_source/tests/browser.cjs | tests/browser.cjs | C | `1fc85f7f293e215d4c171651ae09c4118e14e5d7e462eb1f5072dd791929c099` |
| public_source/tests/candidate-copy.cjs | tests/candidate-copy.cjs | C | `84907962385f4e9a6d9384721740a0b13e1b0b3ab4f45402f11567f62ecec58d` |
| public_source/tests/context.py | tests/test_candidate_context.py | C | `2f17a14acdaf8caffa19aa9e6f2c907793cd46482172d3d33f38a33ab017fa0b` |
| public_source/tests/contract.py | tests/test_candidate_contract.py | C | `45b9cfc8c8c01a36ba9279267ae3be170a18a9096d9e5f7cc8e50765c8d9d2eb` |
| public_source/tests/datasets.py | tests/test_candidate_datasets.py | C | `98141ff24f6a310bc059fac5f248d154b6952e4b6ff97d414f0e8bd402edff24` |
| public_source/tests/harness.cjs | tests/harness.cjs | C | `4416c675a6c4005f36929372b09f193ec9fed226319eb6aae8fc3c3db8c900a0` |
| public_source/tests/install.py | tests/test_candidate_installation.py | C | `1e9020922a3e5e5826adc431fa920945038d089f32f1d0af022aa07b3c1dc7eb` |
| public_source/tests/package.py | tests/package.py | C | `3045dd8817605edca1624f39ecf9639e89fa15c7d7a9fb4be7b7220e33a16df9` |
| public_source/tests/reviews.py | tests/test_candidate_reviews.py | C | `df4483be2b32453d5c703f686316b52c4f6639cd12aaa1bddbf7aae81f80e127` |
| public_source/tests/security.py | tests/test_candidate_security.py | C | `ca8aaeec688435df55f1628838dbcceb3fb76fea5e95ed628917be4918b3cc76` |
| public_source/tests/support.py | tests/support.py | C | `0bf97c3ab398fb6d51a2d3d2a64c66c7590463336a3bf1c4647164d6e60d977f` |
| requirements-dev.txt | requirements-dev.txt | O | `b9cbd5f33f08355ee2b812680197cb1eb29c68de0c7ddda85e47b473acc6a213` |
| run.ps1 | run.ps1 | O | `e23b7df25c3b824a7245d1b7a9a311f7bdbadb39f299fe7ff418cd51e7347374` |
| run.sh | run.sh | O | `2b800e28d437952bd97bcca7857254e676b8c9c06c6cf28ecd1d167cc38ec663` |
| scripts/install.ps1 | scripts/install.ps1 | O | `d46aabd4584650c8a23aa46ac360aad961b4664b4d7da64ae12e53a7563db8a0` |
| scripts/install.py | scripts/install.py | O | `66e119a2ee999c6dab52b6eb5aaa0e248071d4ea39ebe3c6d2edcc5a29fdb962` |
| scripts/install.sh | scripts/install.sh | O | `fb1ffb3c77e1666dfae823f2d63146550405d0a7c08a9529b7fc5b60b053449f` |
| scripts/launch.py | scripts/launch.py | O | `17177c95b41e55f91e114fa44e897ca252226da20b1665cab293116e4cab2827` |
| scripts/local_runtime.py | scripts/local_runtime.py | O | `52058387e3c1fd855cc5745352cdd13f4ee40d48ecd0b31727a09208b8e0c401` |
| scripts/select_v007_windows.py | scripts/select_v007_windows.py | O | `7ef2cd50757e4b8be31fa77580e53a1051911f685183672d997cd286c4410df7` |
| tests/test_clean_export.py | tests/test_clean_export.py | O | `a80d1e3affa6ca887588e8d78a62bbf475fc56fd0aabd0db39b43c3767d653a1` |
| tests/test_dataset_quality.py | tests/test_dataset_quality.py | O | `7848ca33c4abe7d58ef0a3056435a707baccf7c118a88a671c4d5f00610c1431` |
