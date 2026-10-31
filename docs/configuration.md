# Configuration

Set variables in the launching shell. `.env.example` is a reference only; the app and launchers do not automatically load `.env`.

| Variable | Meaning | Default |
|---|---|---|
| `NAJDILAB_PYTHON` | Executable used by `run.ps1`/`run.sh` | Explicit override, otherwise checkout .venv, otherwise available interpreter |
| `NAJDILAB_PORT` | Loopback HTTP port | `8770` |
| `NAJDILAB_NO_DEMO` | `1` disables demo seeding | Off in launchers; on for direct app.server unless set |
| `NAJDILAB_INGEST_TOKEN` | Private shared ingest secret | Unset: ingestion fails closed (HTTP 503) |
| `NAJDILAB_ALLOW_LEGACY_INGEST` | Explicit `1` permits native ingest without credentials | Disabled |

Windows example:

```powershell
$env:NAJDILAB_PORT = '8870'
$env:NAJDILAB_NO_DEMO = '1'
.\run.ps1
```

Linux/WSL example:

```bash
NAJDILAB_PORT=8870 NAJDILAB_NO_DEMO=1 sh ./run.sh
```

The host remains `127.0.0.1`; changing the port does not enable remote access. Configure external local collectors to use the same port. Check [SECURITY.md](../SECURITY.md) before integration; the interface can launch without an ingest secret, but collection is disabled until `NAJDILAB_INGEST_TOKEN` is configured. Same-user local processes remain outside the isolation boundary.

Data paths are based on the repository root (`data/najdilab.db`, `exports/`, `datasets/`, `training/`). Generated model/runtime registries store installation-specific paths. Do not commit them or assume historical default paths exist on a new machine. Configure the actual model/runtime through the platform, validate compatibility and retain fresh evidence for each job.

`.gitignore` keeps generated/private material out of normal staging; it does not remove previously tracked files or sanitize Git history. Never put credentials or personal conversation text in public examples, logs or issue attachments.

## Ingest authentication

Generate a high-entropy secret locally, for example with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, and store it in authorized private secret storage. Set `NAJDILAB_INGEST_TOKEN` in the server launch environment and configure the same value in the collector; do not paste it into a tracked script, `.env.example`, issue or terminal transcript intended for publication. A new environment value takes effect when the intended process is deliberately relaunched.

`/api/v1/turn` requires either `Authorization: Bearer <secret>` or raw-body HMAC authentication. Without a configured secret it returns 503; missing, wrong, duplicate or mixed credentials return 401 when configured. `/api/v1/hermes-hook` is BLOCKED with 409 before body reading regardless of credentials/legacy mode: see [Hermes safety correction](hermes-integration.md). Never route unsafe Hermes events through the generic collector as a workaround.

[Settings integrations](integrations.md) use fixed loopback runtime endpoints and in-memory consent. No API keys, endpoint overrides, external config edits or new environment variables are introduced.

`NAJDILAB_ALLOW_LEGACY_INGEST=1` is an explicit compatibility exception for native clients and prints a startup warning. Do not enable it for a new setup; bad supplied credentials still fail, and browser CSRF rules remain in force. All other writes, including native scripts, need `X-NajdiLab-CSRF` from `GET /api/v1/session`. The browser UI handles its own token. CSRF tokens are not reviewer authentication or ingest credentials.

Launchers reject Python below 3.11 and invalid ports before server import; explicit NAJDILAB_PYTHON takes priority. Local setup does not initialize a DB or load .env. Direct module startup is lower-level and retains its historical demo-on behavior.
