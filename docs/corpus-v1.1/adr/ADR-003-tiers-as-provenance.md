# ADR-003 — Gold, Silver and Bronze are provenance on existing manual items

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
Tiers aren't separate stores. All three are `manual_sft_items` rows distinguished by `origin`/`source_type` (existing `manual`/`human_written` for Gold; new `synthetic_variant` for Silver and `llm_draft` for Bronze), `parent_item_id` lineage (existing column), and `generation_batch_id` (migration 008). Taxonomy attributes go in `metadata_json.corpus_v11` until approved columns exist.

## Consequences
Existing versioning, cloning, export, health and balancing apply unchanged. New provenance values need service validation and, for tables with CHECK constraints, a rebuild in 008.
