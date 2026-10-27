# Phase 5 issue register

Statuses require observed regression evidence before VERIFIED_CLOSED. Historical RED results remain in [execution](public-core-phase5-execution.md) and [verification](public-core-phase5-verification.md). No ownership/license/history approval is inferred from engineering success.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-01 | Critical/P0 | Correction UI omits flags; shared service defaults clear privacy/evaluation/exclusion and may enable eligibility | Candidate transaction; test_omitted_flags_notes_and_tags_survive_correction and explicit/repeated-save/hash tests PASS; actual browser flag readback + independent review | VERIFIED_CLOSED |
| P5-02 | Critical/P0 | Optional stale token and timestamp reuse permit silent overwrite | Mandatory token/transaction/fresh revision; concurrent same-token200/409 and zero-write stale tests PASS; actual browser conflict/reload + review | VERIFIED_CLOSED |
| P5-03 | High/P0 | Minimal UI lacks context, saved readback and explicit eligibility | Contextual UI + real browser context/save/flag/approval/exclusion/restart acceptance | VERIFIED_CLOSED |
| P5-04 | High/P0 | Missing actionable readiness/version inspection and constrained artifact handoff | Dataset/artifact suites and actual browser preparation/download/backup acceptance PASS | VERIFIED_CLOSED |
| P5-05 | Release gate | Historical Git privacy, ownership, license and exact rights remain uncleared | B07 exact manifest/provenance/owner decision package | BLOCKED |

New findings and review outcomes are appended during implementation; no finding is closed merely because code changes.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-06 | High/P0 | New lifecycle SQL initially omitted required timestamps | Fresh exclude/ignore/delete/restore HTTP regression RED then PASS; independent recheck | VERIFIED_CLOSED |
| P5-07 | High | Reviewer assertion mapping and lifecycle reasons initially lost | Preserve/map reviewer, persist reason; HTTP regression RED then PASS; independent recheck | VERIFIED_CLOSED |
| P5-08 | Critical/P0 | Generic save/approval could discard retained correction | All-action no-discard regression RED then PASS; independent recheck | VERIFIED_CLOSED |

Historical Goal1 checkpoint (superseded by Goal2 evidence below): backend defects P5-01/P5-02 are FIXED with passing privacy/race tests; complete UI closure awaits Goal2 browser evidence. Same-status edits use existing schema without unapproved review-event migrations. Ordinary-decision reason is a lifecycle-only API field, not a complete event-history guarantee.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-09 | High/P0 | Same-page/confirmed navigation could abandon dirty protection | Browser RED exclusion probe; preserve same-page dirty and clear accepted discard; real browser PASS + review | VERIFIED_CLOSED |
| P5-10 | High/P0 | In-flight saves/detail reads could replace drafts or selection | Freeze controls and serialize selection; delayed real-request browser assertions PASS + review | VERIFIED_CLOSED |
| P5-11 | High | New review-detail GET opened writable DB/create path | Missing-DB HTTP RED; mode=ro wrapper + unchanged rows/no-created-state PASS + review | VERIFIED_CLOSED |

Goal1 privacy/staleness closures now include actual browser persistence/conflict evidence. Candidate current-state schema still does not supply a full append-only event audit; no proposed migration is activated.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-12 | Critical/P0 | Later eligible targets could copy restricted earlier context | Context-aware fail-closed gate; real API RED and independent memory reproduction, regression PASS/review | VERIFIED_CLOSED |
| P5-13 | High/P0 | Manual source privacy omitted from readiness | All selected manual-table privacy gates; corrected-fixture RED then PASS/review | VERIFIED_CLOSED |
| P5-14 | High/P0 | Legacy diagnostics ignored/misclassified actual holdout | Verified in-memory alias + actual-format balance; format/mask tests PASS/review | VERIFIED_CLOSED |
| P5-15 | Critical/P0 | Linked exports root could redirect archive writes | Check write root before export; linked-root RED then denial/no-writes PASS/review | VERIFIED_CLOSED |
| P5-16 | High/P0 | Weak masks/empty holdout could receive READY | Strict assistant-target validation and actual minimum/diversity/fraction/count checks; RED then PASS/review | VERIFIED_CLOSED |
| P5-17 | High/P0 | Another server process could bypass per-instance mutation lock | OS storage guard, second-server RED then refusal/first-server health PASS; review | VERIFIED_CLOSED |

Direct/preference preparation is explicitly deferred to B08 and blocked before version writes; no false compatible evaluation is claimed. Same-root out-of-band DB/library writers are unsupported. Current candidate does not claim a complete historical review-event log or automatic PII detection.

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-18 | High/P0 | Old backup could mix DB snapshot with live/unregistered/linked exports | Candidate snapshot-registered verified-byte backup; staging RED, concurrent preparation/restore PASS | VERIFIED_CLOSED |
| P5-19 | High/P0 | Restore destination race and incomplete version inventory | Exclusive mkdir + xb copying; shared structural validation, incomplete ZIP RED then PASS | VERIFIED_CLOSED |
| P5-20 | Critical/P0 | Cleanup could delete an unowned colliding incomplete file | Ownership tracking; forced-name preservation PASS and cleanup-mutation expected FAIL; review | VERIFIED_CLOSED |
| P5-21 | High/P0 | Backup size bounds applied after allocation | Pre-read DB and incremental version budgets; bounded-read RED then PASS; review | VERIFIED_CLOSED |
| P5-22 | High/P0 | Backup archive/member name shadow broke publication | Separate names; six failures retained, full backup suites now PASS; review | VERIFIED_CLOSED |

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-23 | High | SVG stylesheet PI, xml:base and CSS image-set could load external resources | Three RED resource probes; preparse PI/namespaced attribute rejection and restricted fragment-only CSS; passing builder regression and independent recheck | VERIFIED_CLOSED |
| P5-24 | High | Recovery guide copied data after installer created target dirs | Copy-before-install guide and actual separate-candidate install/launch/readback acceptance PASS | VERIFIED_CLOSED |

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-25 | High/P0 | Acceptance helpers copied a whole checkout, risking accidental original-app execution | Manifest/profile/selected hash guard before setup, Python+Node fake-source negative tests; unlisted state never copied; independent review PASS | VERIFIED_CLOSED |
| P5-26 | High | Unsupported methods used generic HTML501/error body including HEAD | Boundary-first structured405/Allow and empty HEAD; seven RED subtests now PASS; independent review | VERIFIED_CLOSED |
| P5-27 | High | Runtime import checker allowed separately installed pytest outside tests | Two RED runtime-import probes; test-only dependency allowlist now PASS; independent review | VERIFIED_CLOSED |
| P5-28 | High/P0 | Shell/PowerShell install wrappers absent from candidate | Actual shell installation test failed; reviewed unchanged wrapper bytes explicitly included; repeat/state-preservation PASS; independent selection review | VERIFIED_CLOSED |

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-29 | High/P0 | Valid Windows restore staging alias failed strict canonical path comparison | Two hosted failures + direct-function trace; nonlinked staging alias RED, normalize only newly owned stage; full recheck pending | IN_PROGRESS |
| P5-30 | High | Test fixture Arabic reads/writes used platform default cp1252 | Three real Windows failures; explicit UTF-8 test fixture IO; hosted recheck68PASS/2 unrelated restore failures, all three encoding failures closed | VERIFIED_CLOSED |

| ID | Severity | Finding / root cause | Fix / regression / evidence | Status |
|---|---|---|---|---|
| P5-31 | High/P0 | Inherited legacy-ingest override bypassed the Core credential contract | Raw invalid-JSON2RED subtests; actual unauthenticated write plus four credential/path failures and row-count failure; candidate503 before shared auth/parse/DB; final recheck pending | IN_PROGRESS |
