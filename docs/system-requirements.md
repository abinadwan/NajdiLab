# System requirements

Core review/dataset work uses Python3.11+, Python sqlite3 with SQLite3.24+ and a modern JS/CSS browser. Python's standard library supplies the server; HTML/CSS/JavaScript has no frontend build step. Provide writable space for SQLite WAL, exports, private backups and a separate restore copy. No universal CPU/RAM/disk minimum has been measured.

Chat requires an explicitly connected local engine. LM Studio needs the optional pinned SDK1.5.0 in NajdiLab's own environment and an already-loaded model. Ollama's supported resolver behavior is verified only for0.40.13; unknown versions fail closed. These services/models are installed and managed separately. No GPU/model framework or training runtime is installed by core setup. Suggested context is an unverified estimate, not a safe memory guarantee.

Windows11 and Ubuntu/WSL checks have dated evidence in [verification](verification-evidence.md). They do not certify every Python/browser/OS, actual installed models, a complete private backup or public hosting. [Installation](installation.md), [owner Chat acceptance](chat-windows-acceptance.md).
