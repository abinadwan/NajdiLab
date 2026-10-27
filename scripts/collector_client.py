"""Bind write-capable local collector tools to their checkout and configured port."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import request


def collector_url(path: str) -> str:
    value = os.environ.get('NAJDILAB_PORT', '8770')
    try:
        port = int(value)
    except ValueError as exc:
        raise SystemExit('NAJDILAB_PORT must be an integer from 1 to 65535.') from exc
    if not 1 <= port <= 65535:
        raise SystemExit('NAJDILAB_PORT must be an integer from 1 to 65535.')
    return f'http://127.0.0.1:{port}{path}'


def verify_collector(database: Path) -> None:
    """Read health before any write; never send credentials during this check."""
    try:
        with request.urlopen(collector_url('/api/v1/health'), timeout=5) as response:
            health = json.load(response)
        matches = health.get('ok') is True and health.get('service') == 'NajdiLab'
        matches = matches and Path(health['database']).resolve() == database.resolve()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit('Unable to verify the local collector. Check NAJDILAB_PORT and start this checkout server.') from exc
    if not matches:
        raise SystemExit('Collector belongs to a different NajdiLab checkout; no data was sent.')
