# Dataset roadmap

The product boundary is local Chat → human review/correction → quality/dedup → immutable dataset versions → external Unsloth export. LM Studio/Ollama are externally managed inference services; native application history capture and Hermes collection are unsupported. No internal trainer, model acquisition/benchmark/merge/GGUF/deployment or WSL worker is planned in this application.

Current work removes the internal execution source and obsolete documentation while retaining dataset tools, originals/overlays, privacy gates, manifests/provenance and applied migrations. APIs use dataset terminology; removed execution routes have no compatibility shim. This change is source-only and needs no data rollback.

Remaining product verification is actual installed-model/owner acceptance, honest hardware estimates, recovery rehearsal and exact source-only candidate checks after source changes. Future review improvements include identity/accountability and canonical dataset catalog/event semantics, each requiring its own design and schema review. Physical erasure and old-export retention require an explicit data-owner decision; cleanup does not remove private state.

[Status](../PROJECT_STATUS.md), [external export contract](dataset-export.md), [verification limits](verification-evidence.md), [publication gates](public-release-decision.md).
