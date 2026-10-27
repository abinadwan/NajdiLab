# Base model selection

## Supported sources

- **Local / WSL:** a Hugging Face-format directory containing `config.json`, tokenizer files and trainable weights.
- **Hugging Face repository ID:** register a reference and `revision`; registration alone does not download weights. The separate acquisition workflow requires explicit approval.
- **Ollama:** informational inference candidate only; GGUF files are not trainable base weights.

Local discovery is limited to 10 roots, one directory level and 100 results. It does not scan the entire machine or expose arbitrary private paths.

## Selection

1. Open **Training → Training Setup**.
2. Enter a stable ID, display name and local directory or repository ID in the model registry.
3. Register the candidate. Registration is neither a download nor proof of compatibility.
4. Run live compatibility validation. Require `validation_status=VALID` and `excluded=false`.
5. Select the candidate and dataset version, then run preflight.
6. Create a DRAFT job. Changed model or dataset fingerprints must block READY.

Historical Ministral remains `EXCLUDED/HISTORICAL` for traceability and is not the default. With no valid candidate, the interface shows **Not configured** and disables job creation. Historical discoveries and model approvals do not make a fresh clone ready to train. Review the exact selected revision's model license and acceptable-use terms before download, use or redistribution.

## Execution contract

The job snapshot stores `id`, `path/repository_id`, `revision` and `fingerprint`. Runtime passes `--model-path`, `--model-id` and `--model-revision` to `najdilab_training_adapter.py`; there is no hidden fallback to Ministral.

## API

- `GET/POST /api/v1/training/models`
- `POST /api/v1/training/models/discover`
- `POST /api/v1/training/models/{id}/validate`
- `POST /api/v1/training/preflight`
