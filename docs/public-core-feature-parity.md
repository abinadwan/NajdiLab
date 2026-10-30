# Public core feature parity

Date: 2026-10-27. This is **analysis and planning**, not a feature migration or publication clearance. The recommended product boundary and ordered backlog are in [public core release scope](public-core-release-scope.md). Existing [release decision](public-release-decision.md), [isolation specification](public-private-boundary.md), historical reports and private implementations remain authoritative within their stated scope.

## Baseline, method and limits

Remote references were fetched and GitHub metadata reviewed before editing. Main is `2015a085c1de88a9d1fc4bd4e9e5f45b8394c2a2`. [PR #2](https://github.com/abinadwan/NajdiLab/pull/2) is open Draft at `d5e8c2d60a84822e4587a7fd47688ed65f29e491`, targeting main. [PR #3](https://github.com/abinadwan/NajdiLab/pull/3) is open Draft at `555647fcfc6c2d73c792adfa0c02977d4b4cacdd`, targeting PR #2's branch. Repository visibility is Private. The clean analysis branch `dev/public-core-release-scope` starts at PR #3 head; neither existing PR branch is changed.

The **original application** below means the original `app/`, `static/` and associated schemas at this baseline, not an observed production installation. The **candidate** means the exact 37-file mapped distribution from `public_source/policy.json`, with its replacement server/UI, not a Git clone containing the original UI. Original application bytes are the same across these two PR heads. Review used AST inspection without executing historical loaders, the generated 101-route inventory, all 27 app modules, all 19 navigation views, dialogs, the legacy redirect page, frontend API calls, candidate dispatch/UI, distribution mapping, tests and current documentation. No private production evidence was opened.

Counts are inventories, not parity percentages: original **46 GET + 52 POST + 2 PATCH + 1 DELETE = 101 dispatch branches**; candidate **20 concrete dispatch branches**, covering **22 original method/path patterns** because its health/quality/balance alternatives share one branch. Its extension prefix dispatcher is additional and supplies no research capability. The candidate uses GET/POST only. Regex alternatives such as review actions count once in both inventories. UI capability, route existence, underlying Python logic and exercised behavior are assessed separately.

| Classification | Meaning in this report |
|---|---|
| IMPLEMENTED | Candidate exposes the named operation with its core behavior; does not assert exhaustive test or legal clearance |
| PARTIAL | Candidate exposes a reduced contract/UI, or ships relevant logic without the complete workflow |
| MISSING | Reusable capability absent from the candidate surface; implementation/review still needed |
| PRIVATE_ONLY | Historical records or a workflow fixed to that evidence; preserve privately, do not port records |
| PLANNED | Design/proposed capability without completed operational implementation |
| BLOCKED | Deliberately unavailable pending safety, rights, schema or execution approval |

These are candidate feature dispositions. Evidence strength is separately stated as static inspection, fresh test, previous browser/CI evidence, or NOT_VERIFIED. An original route can exist while requiring absent artifacts or refusing execution. Public-safe reuse means a technical candidate for review, not an ownership/license finding.

## UI comparison matrix

Source: [original navigation and forms](../static/index.html), [original event/API wiring](../static/app.js), [candidate markup](../public_source/static/index.html) and [candidate actions](../public_source/static/app.js). The candidate is one page with Conversation review, Dataset preparation and an unavailable-research explanation; it has no equivalent sidebar.

| Original view / secondary surface | Original workflow | Candidate status | Actual candidate surface / gap |
|---|---|---|---|
| Dashboard (`dashboard`) | Counts, overview and platform/research status | MISSING | Readiness sentence only; analytics API exists, no dashboard cards |
| Review queue (`review-queue`) | Context, approve/correct/exclude/restore/ignore/delete, eligibility and flags | PARTIAL | Pending original responses and correction textarea only; no question/context, approval button or editable privacy/eligibility controls |
| Conversations (`conversations`) | Search/list and conversation detail | MISSING | List/detail API exists; no conversation browser |
| Reviewed (`reviewed`) | Inspect/filter saved decisions | MISSING | API exists; corrected row leaves pending UI with no saved-review inspection |
| Add data (`add-data`) | Manual SFT, direct language text, preference pair forms | MISSING | No input form; conversation/message/turn APIs remain available |
| Manual data (`manual-data`) | Filter, edit, clone, archive, exclude, version/bulk operations | MISSING | Service/schema retained, routes and UI absent |
| Training data (`dataset`) | Inspect eligible records and demo inclusion | MISSING | Eligibility API exists, no eligible-record browser |
| Dataset health (`dataset-health`) | Version selection and diagnostics | MISSING | Health/quality APIs exist, no rendered diagnostics |
| Dataset balancer (`balancer`) | Balance findings and non-mutating candidate preview | MISSING | Balance analysis API exists; selection preview route absent |
| Dataset versions (`dataset-versions`) | Detail, lineage, hashes, derive, overlap plan, freeze | PARTIAL | Raw JSON list only; no detail/actions UI or mutation endpoints |
| Training setup (`training`) | Model references/config, acquisition plan, preflight, runtime check | MISSING | Training unavailable explanation; all training API prefixes return 503 |
| Training jobs (`training-jobs`) | Draft/ready/cancel, Dry Run, Smoke/Full approvals, attempts/logs/recovery | BLOCKED | No job UI or execution; needs independent generic extraction and security review |
| Evaluation sets (`eval-sets`) | Locked holdout/leakage inspection | MISSING | Health includes leakage findings; separate evaluation-set route/UI absent |
| Human review (`human-review`) | Fixed historical Base/Adapter comparison and final decision | PRIVATE_ONLY | Not included; a generic future comparison workflow must use new explicit evidence |
| Remediation review (`phase38-review`) | Fixed v009 review cases/freeze gate | PRIVATE_ONLY | 503; no embedded cases distributed |
| Verify edits (`phase39-review`) | Fixed historical edits/post-edit verification | PRIVATE_ONLY | 503; no edit manifest distributed |
| Export center (`exports`) | Readiness/dedup preview, new version and history | PARTIAL | Confirmed preparation with include_demo=true and raw version list; no readiness details, dedup preview or download UI |
| Analytics (`analytics`) | Model/channel/error-tag statistics | MISSING | API exists; no rendered statistics |
| Settings (`settings`) | Theme/local-scope/storage/training/demo explanation | PARTIAL | Local/research scope explanation only; no theme selector or settings view |
| Manual detail/version dialog | Inspect/edit versions and export history | MISSING | No manual-data UI/routes |
| Review-delete confirmation dialog | Confirm soft deletion of the review overlay | MISSING | API action exists; no delete UI; do not add destructive actions to MVP casually |
| Legacy `phase38-review.html` entry | Redirect to unified remediation route | PRIVATE_ONLY | Asset excluded; candidate static fallback may return its home page, not this view |

The original detail panels for conversations, dataset health/version, training results/jobs and human comparison belong to the views above, rather than extra navigation screens. Original styling includes theme controls and English LTR/Arabic direction handling. Candidate text uses DOM `textContent` and `dir=auto`, but original styling, localization catalogs, theme behavior and richer accessibility are not carried over. No claim of complete RTL/accessibility parity is made.

## Backend module inventory

Every original `app/*.py` file is represented below. “Shipped” means in the candidate manifest, even if not reachable over HTTP. All original files remain unchanged.

| Original module | Responsibility / dependency | Candidate disposition | Reuse and risk |
|---|---|---|---|
| [__init__.py](../app/__init__.py) | Package initialization | IMPLEMENTED; shipped | No research loader |
| [db.py](../app/db.py) | SQLite, WAL/FKs, transactions, key redaction, migrations | IMPLEMENTED; shipped | Startup 001–004 only; unguarded/non-atomic loader debt remains |
| [http_security.py](../app/http_security.py) | Host/Origin/Fetch Metadata, CSRF, Ingest credentials | IMPLEMENTED; shipped | Trusted loopback; legacy override and HMAC replay limits retained |
| [service.py](../app/service.py) | Ingest, originals/reviews, manual records, eligibility, exports, analytics | PARTIAL; shipped | Much generic logic already present; missing HTTP/UI surfaces, not a reason to copy historical data |
| [review_integrity.py](../app/review_integrity.py) | Integrity/staleness/readiness gate | IMPLEMENTED core; shipped | Readiness endpoint exists; missing standalone alias/UI |
| [review_lifecycle.py](../app/review_lifecycle.py) | Transition/event helpers | PARTIAL; shipped | Helpers do not activate proposed review-events schema; do not claim complete append-only event history |
| [clean_export.py](../app/clean_export.py) | Reconstruction, cleaning, dedup/holdout, validation | PARTIAL; shipped | Unit-tested library; current create_export is the separate service implementation, not a dedicated clean-export route |
| [dataset_platform.py](../app/dataset_platform.py) | Version discovery, health, derive/overlap/freeze/detail | PARTIAL; shipped | List/health exposed; mutations/detail not routed. Roots are checkout-local exports/datasets |
| [dataset_quality.py](../app/dataset_quality.py) | Quality findings, loss-mask/release validation | PARTIAL; shipped | Findings endpoint exists; release-validation route absent |
| [dataset_balancer.py](../app/dataset_balancer.py) | Read-only distributions/balance | IMPLEMENTED core; shipped | API yes, UI missing; dataset_platform imports generic select_v007_windows logic |
| [dataset_registry.py](../app/dataset_registry.py) | Discover/plan/apply canonical registry | BLOCKED; excluded | Proposed 005 SQL is not active; filesystem catalog is a different capability |
| [evaluation_guard.py](../app/evaluation_guard.py) | Validate caller-supplied Base/Adapter identity evidence | PARTIAL; shipped | HTTP route returns 503; not inference, independent proof of loading, or a human-review workflow |
| [generation_hardening.py](../app/generation_hardening.py) | Generation config/repetition diagnostics | MISSING; excluded | Potentially reusable pure validation; imports tool_runtime, needs separate closure review |
| [native_tool_data.py](../app/native_tool_data.py) | Native tool record contract | MISSING; excluded | Generic schema logic; depends on tool_runtime/catalog, not cleared by Arabic/phase naming |
| [tool_runtime.py](../app/tool_runtime.py) | Tool visibility, schema, controller, authority/benchmark | MISSING; excluded | Explicit handlers/approval matter; not automatic permission to execute tools |
| [platform_state.py](../app/platform_state.py) | Historical reports/platform catalog | PRIVATE_ONLY as shipped; excluded | Generic status replacement possible; do not expose fixed report discovery |
| [training_control.py](../app/training_control.py) | Models, acquisition, config/plan, preflight, jobs | MISSING generic workflows; excluded | Mixed generic algorithms and fixed model/runtime/output references; not safe to import whole module |
| [runtime_control.py](../app/runtime_control.py) | Registered WSL runtime, staging/workers, gates, attempts/recovery | BLOCKED; excluded | Subprocess/GPU/filesystem side effects, fixed environment assumptions; optional future adapter only |
| [phase3_review.py](../app/phase3_review.py) | Historical comparison loader/blinding/decision | PRIVATE_ONLY; excluded | Generic comparison concepts reusable, recorded cases/decisions stay private |
| [phase35_analysis.py](../app/phase35_analysis.py) | Historical failure analysis | PRIVATE_ONLY; excluded | Imports phase3_review |
| [phase36_readiness.py](../app/phase36_readiness.py) | Historical readiness analysis | PRIVATE_ONLY; excluded | Imports phase3_review |
| [phase37_hardening.py](../app/phase37_hardening.py) | Historical hardening report | PRIVATE_ONLY; excluded | Imports phase3_review plus generic tool/generation helpers |
| [phase38_dataset.py](../app/phase38_dataset.py) | Fixed corpus creation/review/holdout | PRIVATE_ONLY; excluded | Embedded historical records; not a generic dataset service |
| [phase39_edits.py](../app/phase39_edits.py) | Fixed correction/repair/verification | PRIVATE_ONLY; excluded | Imports phase38; preserved corrections are research evidence |
| [phase39a_resolution.py](../app/phase39a_resolution.py) | Historical overlap resolution | PRIVATE_ONLY; excluded | Imports phase38/39 |
| [phase310_freeze.py](../app/phase310_freeze.py) | Historical freeze orchestration | PRIVATE_ONLY; excluded | Imports phase38/39 and training_control |
| [server.py](../app/server.py) | Original HTTP routing/startup/static UI | PARTIAL replacement; original excluded | New candidate server imports core only; original compatibility patch remains approval-gated |

Supporting inventory: four existing startup migrations are shipped; proposed 005/006/007 SQL under `plans/` is excluded and not applied. Of the original utilities, backup/install/launch/local_runtime/select_v007_windows and run.sh/run.ps1 are shipped. Collector clients, registry CLI, dataset-specific builders/audits, benchmarks/trainers/model export utilities and the original frontend remain excluded. Their exclusion is not proof that all are sensitive; each needs an explicit purpose, closure, provenance and side-effect review before addition. Existing [code map](codebase-navigation.md), [source provenance](source-provenance.md) and [protected inventory](public-private-boundary.md#conservative-source-disposition-inventory) preserve the full source context.

## API comparison matrix

Every original method/path dispatch branch appears below. Patterns are literal source patterns; `&#124;` represents regex alternatives in tables. Source links point to original handlers and candidate behavior is grounded in [dispatch](../public_source/server.py). IMPLEMENTED describes core operation availability, not byte-for-byte response compatibility. Candidate groups health/quality/balance into one branch. The retained [original API inventory](api-routes.md) records original fields/handlers in more detail.

| Method | Original path / pattern | Candidate status | Candidate behavior / gap | Original source |
|---|---|---|---|---|
| GET | `/api/v1/session` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L196) |
| GET | `/api/v1/health` | PARTIAL | 200: candidate profile/storage scope replaces original version/database fields. | [handler](../app/server.py#L198) |
| GET | `/api/v1/platform/status` | MISSING | 404: historical status loader excluded; generic status replacement needed. | [handler](../app/server.py#L200) |
| GET | `/api/v1/dataset-catalog` | MISSING | 404: local version listing remains, original catalog aggregation absent. | [handler](../app/server.py#L202) |
| GET | `/api/v1/review-integrity` | MISSING | 404: equivalent core readiness available at /exports/readiness; alias absent. | [handler](../app/server.py#L204) |
| GET | `/api/v1/exports/readiness` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L206) |
| GET | `/api/v1/conversations` | PARTIAL | 200: search only; channel/model filters are not forwarded. | [handler](../app/server.py#L208) |
| GET | `/api/v1/conversations/(\d+)` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L216) |
| GET | `/api/v1/review-queue` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L218) |
| GET | `/api/v1/reviewed` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L220) |
| GET | `/api/v1/training-dataset` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L222) |
| GET | `/api/v1/exports` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L224) |
| GET | `/api/v1/dataset-versions` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L226) |
| GET | `/api/v1/training/datasets` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L228) |
| GET | `/api/v1/training/quality-gate` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L230) |
| GET | `/api/v1/training/models` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L232) |
| GET | `/api/v1/training/model-acquisition/catalog` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L234) |
| GET | `/api/v1/training/runtimes` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L236) |
| GET | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/latest-check` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L238) |
| GET | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L240) |
| GET | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/staging/([A-Za-z0-9._-]+)` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L242) |
| GET | `/api/v1/training/jobs` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L244) |
| GET | `/api/v1/training/jobs/(train-\d{8}-\d{3})/execution-gate` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L246) |
| GET | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L248) |
| GET | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/logs` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L250) |
| GET | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/metrics` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L252) |
| GET | `/api/v1/training/jobs/(train-\d{8}-\d{3})` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L254) |
| GET | `/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L256) |
| GET | `/api/v1/phase38/v009/human-review` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L258) |
| GET | `/api/v1/phase38/v009/freeze-gate` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L260) |
| GET | `/api/v1/phase39/post-edit-verification` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L262) |
| GET | `/api/v1/phase39/readiness` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L264) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/health` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L266) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/quality-findings` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L268) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/release-validation` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L270) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/balance` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L274) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/balance-candidate` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L276) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/eval-sets` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L278) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/conversation-overlaps` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L280) |
| GET | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L282) |
| GET | `/api/v1/exports/dedup-report` | MISSING | 404: generic service.dedup_report shipped but not routed. | [handler](../app/server.py#L284) |
| GET | `/api/v1/analytics` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L286) |
| GET | `/api/v1/manual-data` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L288) |
| GET | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)/versions` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L290) |
| GET | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L292) |
| GET | `/api/v1/config` | IMPLEMENTED | 200: same core fields/enums, now sorted; training_actions=false also in original. | [handler](../app/server.py#L294) |
| POST | `/api/v1/conversations` | IMPLEMENTED | 201: reused validated creation/ingestion contract. | [handler](../app/server.py#L330) |
| POST | `/api/v1/messages` | IMPLEMENTED | 201: reused validated creation/ingestion contract. | [handler](../app/server.py#L332) |
| POST | `/api/v1/turn` | IMPLEMENTED | 201: reused validated creation/ingestion contract. | [handler](../app/server.py#L334) |
| POST | `/api/v1/hermes-hook` | IMPLEMENTED | 201: reused validated creation/ingestion contract. | [handler](../app/server.py#L336) |
| POST | `/api/v1/reviews/(\d+)` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L338) |
| POST | `/api/v1/reviews/(\d+)/(approve&#124;correct&#124;exclude&#124;restore&#124;ignore&#124;delete)` | IMPLEMENTED | 200 on valid request: reused core operation; UI coverage separate. | [handler](../app/server.py#L340) |
| POST | `/api/v1/reviews/bulk` | MISSING | 404: generic service.bulk_review_actions shipped but not routed. | [handler](../app/server.py#L352) |
| POST | `/api/v1/training-data/sft` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L354) |
| POST | `/api/v1/training-data/direct` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L356) |
| POST | `/api/v1/training-data/preference` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L358) |
| POST | `/api/v1/exports` | PARTIAL | 201 when gates pass; include_demo only; original filters provenance metadata is not forwarded (original service does not apply it as selection). | [handler](../app/server.py#L360) |
| POST | `/api/v1/training/models` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L373) |
| POST | `/api/v1/training/model-acquisition/prepare` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L375) |
| POST | `/api/v1/training/model-acquisition/acquire` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L377) |
| POST | `/api/v1/training/models/discover` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L379) |
| POST | `/api/v1/training/models/([A-Za-z0-9._-]+)/validate` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L381) |
| POST | `/api/v1/training/runtimes` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L383) |
| POST | `/api/v1/training/preflight` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L385) |
| POST | `/api/v1/evaluation/verify-adapter` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L387) |
| POST | `/api/v1/training/runtime-check` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L389) |
| POST | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/stage` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L391) |
| POST | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/deploy-adapter` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L393) |
| POST | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker/start` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L395) |
| POST | `/api/v1/training/runtimes/([A-Za-z0-9._-]+)/worker/heartbeat` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L397) |
| POST | `/api/v1/training/jobs` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L399) |
| POST | `/api/v1/training/production-jobs` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L401) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/ready` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L403) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/cancel` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L405) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/dry-run` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L407) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/full-dry-run` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L409) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/authorize-full-training` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L411) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/start-full-training` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L413) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/prepare-recovery` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L415) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/resume` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L417) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/validate-adapter` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L419) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/smoke` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L421) |
| POST | `/api/v1/training/jobs/(train-\d{8}-\d{3})/attempts/(attempt-\d{3})/cancel` | MISSING | 503 EXTENSION_UNAVAILABLE; generic metadata/planning/validation surface absent. | [handler](../app/server.py#L425) |
| POST | `/api/v1/training/full-start` | BLOCKED | 503 EXTENSION_UNAVAILABLE; runtime/acquisition/execution or fixed catalog excluded; separate safety review required. | [handler](../app/server.py#L427) |
| POST | `/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review/cases/([^/]+)` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L429) |
| POST | `/api/v1/phase3/(phase3-train-\d{8}-\d{3})/human-review/final-decision` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L431) |
| POST | `/api/v1/phase38/v009/human-review/([^/]+)` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L433) |
| POST | `/api/v1/phase39/apply-edits` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L435) |
| POST | `/api/v1/phase39/post-edit-verification/([^/]+)` | PRIVATE_ONLY | GET/POST 503 EXTENSION_UNAVAILABLE; fixed historical workflow excluded. | [handler](../app/server.py#L437) |
| POST | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/derive` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L442) |
| POST | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/overlap-plan` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L444) |
| POST | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/apply-overlap-plan` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L446) |
| POST | `/api/v1/dataset-versions/([A-Za-z0-9._-]+)/freeze` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L448) |
| POST | `/api/v1/manual-data/bulk` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L450) |
| POST | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)/clone` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L452) |
| POST | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)/archive` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L457) |
| POST | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)/exclude` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L463) |
| POST | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)/ignore` | MISSING | 404: generic implementation exists in retained library, but no candidate route. | [handler](../app/server.py#L469) |
| PATCH | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)` | MISSING | 501: no candidate PATCH handler; generic manual-data service exists. | [handler](../app/server.py#L497) |
| PATCH | `/api/v1/training/jobs/(train-\d{8}-\d{3})` | MISSING | 501: no candidate PATCH handler; generic job update excluded. | [handler](../app/server.py#L499) |
| DELETE | `/api/v1/manual-data/(sft&#124;direct&#124;dpo)/(\d+)` | MISSING | 501: no candidate DELETE handler; generic manual-data service exists. | [handler](../app/server.py#L515) |

Classification totals: **27 BLOCKED**, **19 IMPLEMENTED**, **42 MISSING**, **3 PARTIAL**, **10 PRIVATE_ONLY**. No candidate route addition is proposed merely to improve these counts.

## Workflow comparison and reusable boundaries

| Workflow | Candidate status / evidence | Dependency, gap and disposition |
|---|---|---|
| Install/reinstall/start/stop in new checkout | IMPLEMENTED; fresh candidate contract | No GPU/ML packages; install does not create DB; launch initializes local 001–004 |
| Explicit synthetic setup | IMPLEMENTED; fresh contract | Absent DB, manifest and confirmation required; never production auto-demo |
| Authenticated completed-turn ingestion | IMPLEMENTED; fresh Arabic API contract | Bearer/HMAC boundary; Hermes-shaped hook is generic protocol reuse, no Hermes installation exercised |
| Conversation/message creation and inspection | IMPLEMENTED API; MISSING UI | Preserve original context; richer channel/model filtering omitted |
| Correction and original preservation | PARTIAL end-to-end; fresh API contract, previous browser proof | UI lacks context, existing-correction prefill and eligibility choices; a successful correction disappears from queue |
| Approve/exclude/restore/ignore/delete/bulk | PARTIAL | Individual API actions present; bulk absent; no buttons. Destructive review semantics need explicit user confirmation/tests |
| Reviewed search/status/privacy | PARTIAL | Generic service/API present; no UI/history explorer; reviewer label is not authenticated RBAC identity |
| Manual SFT/direct/preference CRUD/history | MISSING surface | Existing service and schema are reusable; not first-release necessity |
| Eligibility/privacy assessment | PARTIAL | Existing flags/integrity gate and training-dataset API; UI hardcodes training_eligible=true on correction. Flags are human assertions, not automated PII/consent clearance |
| Readiness and dedup preview | PARTIAL | Readiness API; dedup calculation in library/export but no preview route/UI; display actionable failure details before export |
| New version preparation, hashes/split | IMPLEMENTED API; PARTIAL UX | Fresh fictional export succeeds without bypassing split gates; UI tiny demo alone cannot meet gate |
| Inspect quality/balance/holdout | PARTIAL | Health/quality/balance APIs and leakage logic; no inspector UI, separate eval/overlap endpoints missing |
| Derive/remediate/freeze/release validation | MISSING surface | Reused library functions exist; state-changing routes need frozen-parent, fingerprint/token and rollback coverage before exposure |
| Canonical registry/review-event extensions | BLOCKED | Proposed SQL and loader safeguards need approval; directory enumeration is not canonical registry activation |
| Model references and hyperparameter planning | MISSING; reusable generic concept | Extract metadata validation and step math independently of fixed catalogs, filesystem scanning and download code |
| Training preflight | MISSING | Depends on quality, explicit model/runtime evidence and tool/template contracts. No generic compatibility guarantee from historical hardcoded model rules |
| Dry Run/job state | BLOCKED in candidate | Original Dry Run includes staging/runtime dependencies despite zero optimizer steps; future pure offline planning must be named distinctly |
| Smoke/Full/recovery/cancel/adapter validation | BLOCKED | Separate execution authorization, stale-token/fingerprint and runtime isolation tests; absent runtime must never mean ready |
| Generic evaluation identity validation | PARTIAL library only | Shipped guard accepts supplied evidence; no route. This alone does not run inference or establish independent trustworthy evidence |
| Generic human comparison/decision | MISSING | New explicit run/case/evidence schema; must not reuse historical IDs/cases/decisions as fixtures |
| Historical evaluation/remediation/freeze | PRIVATE_ONLY | Preserve original comparisons, corrections, rejected decision and frozen Gold privately |
| Tool contracts/generation diagnostics | MISSING | Potential public library reuse after registry/config/handler audit; no execution as documentation proof |
| SQLite/export backup and isolated restore | IMPLEMENTED CLI; fresh contract | ZIP CRC, integrity/FKs verified; not full model/checkpoint/research backup or automatic live restore |
| Themes/accessibility/localization | PARTIAL | English and auto-direction content only; original theme/UI regression coverage does not automatically cover new frontend |
| Corpus v1.1 generation/RBAC/event design | PLANNED / BLOCKED prerequisites | Existing design/ADRs retained; not this release and no implicit migration approval |
| Merge/GGUF/export/deployment | BLOCKED | Existing scripts/routes do not authorize model release or production integration |

### Functional dependency and security risks

1. Original `server` imports historical phase3/38/39 and training/runtime/platform_state. Phase39/39a/310 transitively import protected modules; phase35/36/37 depend on phase3. Importing the original server to regain its UI/API would defeat isolation. The candidate uses its separate entry point; its default extension is a controlled 503, not a private discovery mechanism.
2. `service -> db/review_integrity/review_lifecycle`; `dataset_platform -> db + scripts/select_v007_windows`; quality/balancer depend on dataset_platform. These generic chains are already selected. Generic functions inside excluded training modules are not standalone public dependencies yet; extract/reimplement reviewed interfaces without importing parent modules. Any original protected-source edit still requires separate approval.
3. The candidate's `/api/v1/training/`, `/api/v1/evaluation/` and `/api/v1/phase*` dispatcher uses one extension contract. Adding generic model/preflight endpoints must explicitly route them before this dispatcher or use a revised explicit map; an accidental catch-all delegation must not enable private execution. No dynamic plugin loader is proposed.
4. Existing APIs and diagnostics can return local paths and excerpts of operator data. Loopback is a trust boundary, not redaction of every successful response. Safe errors do not make logs/screenshots/exports public-safe. A future version-download endpoint needs containment, symlink/encoded-path tests and an explicit warning that generated data is private by default.
5. Unsupported GET/POST API routes produce JSON 404; missing static paths can return the candidate home page. PATCH/DELETE/HEAD/OPTIONS are not implemented and receive base-handler 501 responses after request checks. Do not promise universal JSON unavailable responses or infer a legacy screen from HTTP 200 alone.
6. **Release-blocking candidate UI gap:** the correction body sets human identity and training eligibility, omits privacy/evaluation flags and omits `expected_updated_at`. In `service._save_review_conn`, omitted flags default to false; saving from this UI can therefore clear previously set personal/sensitive/evaluation/exclusion flags. The service already supports optimistic staleness checking, but this UI does not supply its token. Missing context/readback also risks incorrect approvals and overwritten corrections. An isolated independently fictional pending review with all four flags set reproduced their clearing and training eligibility becoming true when passed the exact current UI payload. Original response stayed unchanged; a supplied stale token correctly rejected. This **fails proposed release acceptance** despite the existing suite passing. No private record was accessed and no code/test fixture was changed; make permanent synthetic regression cases before any implementation. Restore returns PENDING/ineligible and clears evaluation/exclusion state, so require explicit re-review rather than treating restore as approval. Trusted local operation supplies no RBAC, verified reviewer identity or automated consent check. MVP must make eligibility explicit and preserve original/correction separation.
7. Existing migration loader, concurrent export numbering/filesystem writes, stale diagnostics, frozen-parent mutation, duplicate version IDs and symlinked local artifacts need scoped regression review before adding state-changing routes. Current tests do not prove concurrency safety or a malicious-local-filesystem sandbox. No live migration, training or filesystem probing is authorized.
8. HMAC lacks replay freshness; native authentication has an explicit legacy override. Cross-origin/Host/CSRF/framing protections remain essential for any new route. Adding model paths/subprocess/downloads would expand the attack surface substantially; defer them from MVP. No shared/public hosting claim is made.

## Documentation, screenshots and architecture accuracy

| Material | Verified scope / discrepancy | Resolution in this phase / planned action |
|---|---|---|
| [Candidate README](../public_source/README.md) | Correctly says smaller engineering profile, no training, opt-in demo and insufficient two-row export | Preserved unchanged; MVP needs user-level review/quality walkthrough and complete route/backup documentation |
| [Root README](../README.md) and [user guide](user-guide.md) | Original full interface; dataset/model development language exceeds candidate surface | Add scope labels; do not replace original walkthrough or represent it as candidate proof |
| [Screenshot gallery](screenshots.md) | Seven actual original-UI synthetic captures, including empty training/evaluation states | Add explicit original-versus-candidate label. No committed candidate screenshot exists; private prior browser capture is not a public gallery asset |
| [SVG/Mermaid gallery](architecture-diagrams.md) | Original architecture includes excluded training/runtime/phase code; existing SVG is not candidate topology | Add scope label, preserve SVG/generator/images/Mermaid byte-for-byte; candidate-specific diagram is backlog work |
| [Isolation report](public-source-isolation-report.md) and [boundary](public-private-boundary.md) | Accurate reduced profile and blocked patches | Preserve; API/UI inventory here supplies additional missing-feature detail |
| [Release decision](public-release-decision.md) | Earlier numbered sections are historical; appended candidate engineering section updates isolation outcome | Preserve chronology and add parity/scope cross-reference; no legal gate changed |
| Architecture media/owner illustration rights | Original/AI/third-party provenance still unresolved | Do not ship them merely to improve candidate presentation; candidate policy excludes docs/media by default |

This review did not recapture screenshots or render new diagrams. Previous browser/visual evidence remains dated evidence, not a fresh visual validation. Source comparison confirms the original dashboard/setup/human-review screenshots cannot depict the candidate UI. No screenshot, SVG, Mermaid source or historical record is deleted or modified.

## Verification performed for this analysis

Fresh local environment: Linux container, Python 3.12.14, SQLite 3.53.1; isolated pytest 9.1.1. Source was exported from immutable PR #3 head into a private separate directory, then the exact 37-file candidate was built/verified before tests. No original historical loader was executed by the inventory. Synthetic regression tests use disposable state; no training or live environment operation occurred.

| Check / exact command | Current result | Limitation |
|---|---|---|
| `git fetch origin`, branch/PR/repo metadata | PASS; SHAs above, Private, both Drafts open | Does not inspect owner production working tree |
| Original AST/HTML/API inventory | PASS: 27 app files, 19 nav views, legacy redirect, 101 routes | Static implementation presence, not all original workflow runtime success |
| `python public_source/build.py --output <new-separate-candidate>` then `--verify <candidate>` from immutable baseline snapshot | PASS: 37 files + manifest | Exact baseline selected profile; no legal clearance |
| `PYTHONPATH=/workspace/test-tools python -m pytest -q tests -p no:cacheprovider -rs` inside exact candidate | **22 PASS, 13 subtests PASS, 0 SKIP**, 1.72s | API/security/install/Arabic/export/backup contract, not complete UI parity |
| Same pytest command in original repository | **277 PASS, 24 SKIP, 68 subtests PASS**, 1 existing warning, 6.21s | 23 private-artifact skips + 1 Windows-only skip; warning is existing return-not-None test |
| Disposable synthetic flag/stale-token probe using exact UI request fields | **FAIL proposed release acceptance**: four flags silently cleared and training eligibility enabled; original preserved; explicit stale-token denial PASS | Diagnostic script outside tracked source, no private data; existing passing suite does not cover this UI safety requirement |
| Windows candidate/original execution | NOT_VERIFIED in this phase | Prior exact-baseline Windows/Linux CI: [candidate](https://github.com/abinadwan/NajdiLab/actions/runs/40479920454), [original](https://github.com/abinadwan/NajdiLab/actions/runs/40479920670); not newly executed |
| Fresh browser/screenshot/mobile/diagram rendering | NOT_VERIFIED in this phase | No UI/media changes; prior proof distinguished above |
| Private original dataset/checkpoint/evaluation hashes | NOT_VERIFIED; absent | No evidence of private data integrity is invented |

Final documentation-link, matrix-coverage and preservation results are recorded in the [worklog](worklogs/public-release-remediation.md). File hashes for all 268 baseline tracked files are retained privately. This branch adds analysis documents without changing `public_source/policy.json`: its strict source-classification check will intentionally reject the added paths if building directly from this expanded analysis tree. Reproduce the exact candidate from the reviewed PR #3 commit. A later approved implementation must explicitly exclude reviewed analysis documents in the policy; do not weaken unknown-file refusal or automatically regenerate classifications.

## Conclusion for scope review

The isolated core is a working engineering foundation, not original-feature parity. The useful first public product can be a trusted-local **conversation review and dataset preparation platform** once the small UI, actionable quality/version inspection and artifact handoff are completed. Generic model configuration, offline planning and evaluation are reusable future work, not reasons to ship historical records or enable execution now. See [scope, approvals and backlog](public-core-release-scope.md). Publication remains **NOT READY — BLOCKERS REMAIN**.

## Phase5 implementation continuation

The matrices above are the preserved Phase4 analysis baseline atdc5c82e. Approved B02–B06 have now been implemented and independently tested in the candidate, including contextual review/atomic flags and conflicts, strict readiness/version diagnostics, constrained artifacts and coherent private recovery. [Current Core API/UI/guide](public-core-user-guide.md), [source-grounded Core architecture](../public_source/docs/architecture.md) and [actual73-test/browser evidence](public-core-phase5-verification.md) record current behavior. Original full-platform screenshots and101-route inventory are retained; they are not relabeled as candidate parity. B08–B12, original historical implementations, actual model training/runtime and publication remain separately gated.
