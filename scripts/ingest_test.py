#!/usr/bin/env python3
"""Send one synthetic turn to a running local NajdiLab collector."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

INGEST_TOKEN = os.environ.get("NAJDILAB_INGEST_TOKEN", "")
if not INGEST_TOKEN:
    raise SystemExit("Set NAJDILAB_INGEST_TOKEN to the collector shared secret before sending a test turn.")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.collector_client import collector_url, verify_collector

URL = collector_url("/api/v1/turn")
verify_collector(PROJECT_ROOT / "data" / "najdilab.db")
payload = {
    "conversation_id": f"cli-test-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    "title": "Collector smoke test from CLI",
    "source": "import",
    "channel": "cli",
    "provider": "test-provider",
    "model_name": "synthetic-test-model",
    "model_version": "demo-only",
    "system_prompt_version": "none",
    "user_message": "هذه رسالة تجريبية. وش وظيفة NajdiLab؟",
    "assistant_response": "يجمع المحادثات محليًا ويرتب مراجعتها البشرية.",
    "generation_settings": {"temperature": 0.2, "seed": 42},
    "metadata": {"synthetic": True, "purpose": "collector smoke test"},
    "demo": True,
}

request = urllib.request.Request(
    URL,
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + INGEST_TOKEN},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
except urllib.error.URLError as exc:
    print(f"Unable to reach NajdiLab at {URL}: {exc}", file=sys.stderr)
    raise SystemExit(1)

