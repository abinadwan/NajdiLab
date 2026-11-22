"""QA-06: the blocked legacy receiver gives local evidence about the external sender.

The external sender (an installed Hermes) is outside NajdiLab and is not inspected or
changed. NajdiLab can only show whether anything still tries to deliver to the blocked hook.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import threading
from unittest.mock import patch

import pytest

from app import server


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(server, "HERMES_REFUSALS", server.HookRefusals())
    httpd = server.NajdiLabHTTPServer(("127.0.0.1", 0), server.NajdiLabHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _request(httpd, method, path, body=b"", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
    conn.request(method, path, body, {"Host": f"127.0.0.1:{httpd.server_port}", "Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    payload = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, payload


def test_refusals_are_counted_without_storing_request_content(running):
    status, snapshot = _request(running, "GET", "/api/v1/hermes-hook/refusals")
    assert status == 200 and snapshot["refused"] == 0 and snapshot["last_refused_at"] is None
    assert snapshot["receiver"] == "BLOCKED"
    secret_marker = "synthetic-private-payload-marker"
    with patch.object(server, "ingest_hermes_hook") as ingest:
        for _ in range(3):
            status, error = _request(running, "POST", "/api/v1/hermes-hook", json.dumps({"text": secret_marker}).encode())
            assert status == 409 and error["code"] == "HERMES_UNSAFE_SOURCE"
        ingest.assert_not_called()
    status, snapshot = _request(running, "GET", "/api/v1/hermes-hook/refusals")
    assert snapshot["refused"] == 3 and snapshot["last_refused_at"] >= snapshot["since"]
    assert secret_marker not in json.dumps(snapshot)
    assert set(snapshot) == {"refused", "last_refused_at", "since", "receiver"}


def test_a_validly_signed_delivery_is_refused_and_counted(running, monkeypatch):
    secret = "synthetic-test-secret"
    monkeypatch.setenv("NAJDILAB_INGEST_TOKEN", secret)
    body = b'{"synthetic":true}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch.object(server, "ingest_hermes_hook") as ingest:
        status, _ = _request(running, "POST", "/api/v1/hermes-hook", body, {"X-Hermes-Signature-256": signature})
        ingest.assert_not_called()
    assert status == 409
    assert _request(running, "GET", "/api/v1/hermes-hook/refusals")[1]["refused"] == 1


def test_other_routes_do_not_count_as_hook_deliveries(running):
    _request(running, "GET", "/api/v1/health")
    assert _request(running, "GET", "/api/v1/hermes-hook/refusals")[1]["refused"] == 0
