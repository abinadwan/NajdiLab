# ADR-001 — NajdiLab is the single source of truth; NajdiTrain is its runtime

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Context
The read-only inspection of 2026-10-23 found that NajdiLab already provides review, versioning, quality findings, export gating, a training control plane and evaluation. NajdiTrain is registered as runtime `najditrain-wsl` (`training/runtimes.json`) and receives staged frozen datasets and adapter invocations. An independent pipeline would duplicate these and create competing records.

## Decision
All Corpus v1.1 records, reviews, datasets, jobs and decisions live in NajdiLab. NajdiTrain only executes training through the existing staging, execution manifest and authorization contract. No new database, review service, export format or training launcher will be created.

## Consequences
- Every new capability is an extension of a NajdiLab module or page.
- Generated content enters only through the service layer (DB on the Windows filesystem; no direct WSL writes).
- Migration 007 stays on hold, because it would create a competing training registry (`../07-migration-review-005-007.md`).
