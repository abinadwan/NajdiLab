# 13 — Decision Register

Status: **Phase 1 CLOSED 2026-10-23: all P1 decisions resolved or confirmed by the owner. DF and OA items unchanged.** This register supersedes the decision list in `09-implementation-roadmap.md` (old IDs are given for cross-reference).

Categories:
- **P1**: required before Phase 1 approval
- **DF**: deferred until its implementation phase
- **OA**: requires separate owner approval (an action or authorization, not a design choice)

## A. Required before Phase 1 approval (P1)

| ID | Decision | Recommended default | Impact | Status |
|---|---|---|---|---|
| P1-01 | Naturalness principle: no dialect-marker quotas or stock phrases | Adopt (`01` §3.0) | Removes v1.0-style marker stuffing; G2 flags only excess, never too few | **RESOLVED + CONFIRMED by owner (2026-10-23)** |
| P1-02 | Model independence; Gemma 4 E2B IT as initial model only | Adopt (`01` §1.1) | Data stays template-free; any model change goes through registry, tokenizer and template validation; no extra model authorized | **RESOLVED + CONFIRMED by owner (2026-10-23)** |
| P1-03 | Reply register when the user writes MSA (old D-B1) | **Owner decision:** follow the user's language and register. MSA input receives clear, natural MSA unless the user requests otherwise. Don't impose Najdi unnecessarily | Fixes the MSA row of the register matrix and the `register_adherence` rubric | **RESOLVED by owner (2026-10-23)** |
| P1-04 | Persona gender and user addressing (old D-B2) | **Owner decision:** AbuAdwan uses a masculine first-person persona. Address users according to available context, adapting to feminine forms when indicated and using natural gender-neutral phrasing when appropriate | Fixes BR-03/BR-04 and two advisory signals | **RESOLVED by owner (2026-10-23)** |
| P1-05 | Accept G2 scope: deterministic defects only; advisory signals; human-only semantics | Adopt (`04`, `12`) | Prevents over-claiming automation; G3 carries meaning and naturalness | **CONFIRMED by owner (2026-10-23)** |
| P1-06 | Migration posture: 005/006/007/008 blocked; loader guard required first | Adopt (`15`) | No SQL can reach `migrations/` before the loader guard and a guarded runner exist | **CONFIRMED by owner (2026-10-23)** |
| P1-07 | Accept the K12 reconciliation **plan** (`14`); execution stays OA-01 | Adopt | Phase 1A starts from a known baseline without destroying evidence | **CONFIRMED by owner (2026-10-23)** |
| P1-08 | UI-first scope (`16`) | Adopt | Fixes which pages and approvals Phases 2–8 must deliver | **CONFIRMED by owner (2026-10-23)** |

## B. Deferred until implementation phase (DF)

| ID | Decision | Phase | Recommended default | Impact |
|---|---|---|---|---|
| DF-01 | Gold peer review by a second native reviewer (old D-06) | 2 | Yes | Doubles Gold review effort; reduces idiolect bias (K17) |
| DF-02 | Second-reviewer confirmation of FULL corrections (old D-07) | 2 | Yes | Prevents a reviewer rewriting and approving alone |
| DF-03 | Identity mechanism (old D-08) | 2 | Local profiles + PBKDF2 PIN + session; re-auth for data-owner actions | Needed for author ≠ approver and the audit trail |
| DF-04 | Register Corpus v1.0 in the catalog vs keep external (old D-10) | 2 | Keep external; read-only fixtures only | Avoids a NO-GO dataset in the platform catalog |
| DF-05 | G2-H thresholds (length bands, excess-marker level, template concentration %) | 3 | Calibrate on pilot data; advisory only | No blocking effect; tunes reviewer routing |
| DF-06 | Final controlled domain vocabulary | 5 | List in `01` §6.2 | Metadata validation and coverage reports |
| DF-07 | G3 sampling rate for Silver at scale | After pilot (7) | Decide from pilot yield and κ | Review cost vs risk |
| DF-08 | Pilot sizes per tier | 7 | Gold 60 / Silver 180 (≥ 60 reviewed) | Statistical power (±8 pp at n = 60) |
| DF-09 | Template-level leakage threshold for G4 | 8 | Zero shared skeletons above the G2-H concentration threshold between train and eval | Eval validity |
| DF-10 | Fix for observation O-1 (fractional-epoch step rounding) | 1A-2 | Restore ceiling semantics if R3 confirms | Prevents false plan mismatches |

## C. Requires separate owner approval (OA)

| ID | Action | Old ID | Recommended default | Impact |
|---|---|---|---|---|
| OA-01 | Execute the K12 reconciliation (archive, per-group commits, `.tmp` archival) | D-04 | Approve W1 archive first; commits per group after isolated tests | Establishes the Phase 1A baseline |
| OA-02 | Choose the authoritative adapter and deploy it through `deploy-adapter` | D-09 | Expected `b14c7c…` if R2/R3 confirm, with O-1 resolved | Ends the K2 drift; invalidates stale dry runs |
| OA-03 | Authorize any training model other than Gemma 4 E2B IT | — | Not now | Keeps model scope fixed |
| OA-04 | Bronze tier: enable, provider, local vs external, governance | D-05 | Defer; no provider connected | Avoids dialect bleed and governance risk until justified |
| OA-05 | Implement the migration loader guard (`15`) | — | Approve in Phase 1A before any migration work | Unblocks safe migrations later |
| OA-06 | Execute 006 (after loader guard and guarded runner) | — | Approve after rehearsal evidence | Enables the authoritative review audit |
| OA-07 | Execute 005 / REG-09 | D-11 | After 006; independent of v1.1 | Registry canonicalization |
| OA-08 | Execute 008 | — | After 006 and Phase 2 code review | Enables lifecycle, identity and eligibility guard |
| OA-09 | Lift the hold on 007 | — | Keep on hold until a cutover design | Avoids a competing training registry |
| OA-10 | Hermes configuration change for the ingest token (S5) | D-12 | Later | Authenticates ingest |
| OA-11 | Appoint the native linguistic lead and reviewers (≥ 2) | D-02 | Required before the pilot | Unblocks PRQ-LANG-01 and G3 |
| OA-12 | Each generation batch run, dataset freeze and training authorization | — | Always explicit in the UI | Human oversight of every consequential action |

## D. Prerequisites (not decisions)

| ID | Prerequisite | Gates |
|---|---|---|
| PRQ-LANG-01 | Native validation of all Arabic word lists and examples (`01` §3, §7) | Pilot (Phase 7), any release, and switching dialect-list detectors from advisory to blocking |
| PRQ-BASE-01 | Clean Phase 1A baseline (K12 resolved) | Any Phase 1A code work |
| PRQ-MIG-01 | Migration loader guard implemented and tested | Any SQL entering `migrations/` |
