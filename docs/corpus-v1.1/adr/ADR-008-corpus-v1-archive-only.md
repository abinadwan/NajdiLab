# ADR-008 — Corpus v1.0 stays an external frozen archive

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
Corpus v1.0 (`<corpus-archive-root>`, frozen, NO-GO for training and evaluation, `governance/v1.0/STATUS.json`) isn't imported into NajdiLab's catalog. Read-only, hash-verified copies may be used as negative fixtures for G1/G2 tests only. Decision DF-04 can revisit registering it as a non-trainable reference.
