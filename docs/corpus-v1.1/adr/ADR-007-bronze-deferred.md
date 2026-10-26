# ADR-007 — Bronze (LLM-assisted drafting) is optional and deferred

- Status: Accepted (Phase 1, owner approval 2026-10-23) · Date: 2026-10-23

## Decision
No LLM provider is connected in v1.1 until decision OA-04 (provider, local vs external, data governance). Connecting through Hermes or Ollama is outside current authorizations. If enabled, Bronze items carry `origin='llm_draft'` with model, prompt-template hash and sampling recorded, enter `PENDING_REVIEW`, and are 100% human-reviewed in the pilot. The tier is dropped if the pilot yield is below 51/60.
