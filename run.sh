#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -n "${NAJDILAB_PYTHON:-}" ]; then
  PYTHON_BIN="$NAJDILAB_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "Python 3.11+ is required. Set NAJDILAB_PYTHON to its executable." >&2
  exit 1
fi

exec "$PYTHON_BIN" -m app.server

