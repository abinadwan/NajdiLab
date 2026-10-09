#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

if [ -n "${NAJDILAB_PYTHON:-}" ]; then PYTHON_BIN="$NAJDILAB_PYTHON"
elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then PYTHON_BIN=python
else echo "Python 3.11+ is required." >&2; exit 1
fi

exec "$PYTHON_BIN" scripts/backup.py

