"""Request security and receiver refusal on disposable ports only."""
import http.client
from http_client import SingleWriteHTTPConnection as HTTPConnection
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app import server
from app.http_security import CSRF_TOKEN
from test_integrations import IntegrationManager, RuntimeFixture, CONNECTORS, item
from dataclasses import replace


@pytest.fixture
def http_api(tmp_path):
    runtime = RuntimeFixture()
    http = server.NajdiLabHTTPServer(("127.0.0.1", 0), server.NajdiLabHandler)
    specs = {key: replace(spec, port=runtime.port) if spec.port else spec for key, spec in CONNECTORS.items()}
    http.integrations = IntegrationManager(connectors=specs, home=tmp_path)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def request(path, payload=None, *, token=True, origin=None, raw=None):
        conn = HTTPConnection("127.0.0.1", http.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-NajdiLab-CSRF"] = CSRF_TOKEN
        if origin:
            headers["Origin"] = origin
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        conn.request("POST" if body is not None else "GET", path, body=body, headers=headers)
        response = conn.getresponse()
        status, value = response.status, json.loads(response.read())
        conn.close()
        return status, value

    try:
        yield request, runtime, http
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)
        runtime.close()


def test_routes_preserve_consent_csrf_and_origin(http_api):
    request, runtime, _ = http_api
    assert request("/api/v1/integrations")[0] == 200
    assert runtime.requests == []
    for path in ("/api/v1/integrations/discover", "/api/v1/integrations/lmstudio/connect"):
        assert request(path, {"approved": True}, token=False)[0] == 403
        assert request(path, {"approved": True}, origin="http://evil.example")[0] == 403
    assert runtime.requests == []
    status, snapshot = request("/api/v1/integrations/discover", {})
    assert status == 200 and item(snapshot)["availability"] == "AVAILABLE"
    assert request("/api/v1/integrations/lmstudio/connect", {})[0] == 403
    assert request("/api/v1/integrations/lmstudio/connect", {"approved": True})[0] == 200
    assert request("/api/v1/integrations/lmstudio/select", {"approved": True, "model": "synthetic-model"})[0] == 200
    _, current = request("/api/v1/integrations")
    status, snapshot = request("/api/v1/integrations/lmstudio/test", {"approved": True, "selection_revision": item(current).get("selection_revision", 0)})
    assert status == 200 and item(snapshot)["last_test"]["status"] == "PASSED"
    status, snapshot = request("/api/v1/integrations/lmstudio/disconnect", {"approved": True})
    assert item(snapshot)["disconnect"]["local_verified"] is True
    assert request("/api/v1/integrations/lmstudio/test", {"approved": True})[0] == 409
    assert request("/api/v1/integrations/hermes/connect", {"approved": True})[0] == 409
    assert request("/api/v1/integrations/unknown/connect", {"approved": True})[0] == 404
    assert request("/api/v1/integrations/discover", {"url": "http://evil"})[0] == 400


def test_hermes_rejected_before_body_parsing_even_with_legacy_or_secret(http_api):
    request, runtime, _ = http_api
    for legacy in ("0", "1"):
        with patch.dict(os.environ, {"NAJDILAB_ALLOW_LEGACY_INGEST": legacy, "NAJDILAB_INGEST_TOKEN": "synthetic"}), patch.object(server.NajdiLabHandler, "_body", side_effect=AssertionError("Must not read body")), patch.object(server, "ingest_hermes_hook", side_effect=AssertionError("Must not store")):
            status, value = request("/api/v1/hermes-hook", raw=b"private-not-even-json", token=False)
            assert status == 409
            assert value["code"] == "HERMES_UNSAFE_SOURCE"
    assert runtime.requests == []


def test_hermes_rejects_without_waiting_for_body(http_api):
    _, _, http = http_api
    conn = HTTPConnection("127.0.0.1", http.server_port, timeout=2)
    conn.putrequest("POST", "/api/v1/hermes-hook")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", "10000")
    conn.endheaders()  # deliberately never send a body
    response = conn.getresponse()
    assert response.status == 409
    assert response.getheader("Connection") == "close"
    response.read()
    conn.close()


def test_old_acceptance_utility_refuses_before_external_import_or_writes(tmp_path):
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts/acceptance_v11.py")], cwd=tmp_path, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_native_capture_cannot_be_enabled_by_api_or_runtime_consent(http_api):
    request, runtime, _ = http_api
    request("/api/v1/integrations/lmstudio/connect", {"approved": True})
    for key in ("hermes", "lmstudio", "ollama"):
        status, snapshot = request("/api/v1/integrations")
        source = item(snapshot, key)["native_capture"]
        assert source["enabled"] is False
        assert source["connection"] == "DISCONNECTED"
        for action in ("connect", "enable"):
            path = f"/api/v1/integrations/{key}/native/{action}"
            assert request(path, {}, token=False)[0] == 403
            assert request(path, {"approved": True}, origin="http://evil.example")[0] == 403
            assert request(path, {})[0] == 403
            status, result = request(path, {"approved": True})
            assert status == 409
            assert result["code"] == ("NATIVE_CAPTURE_UNSUPPORTED" if key == "lmstudio" else "NATIVE_CAPTURE_BLOCKED")
        for action in ("disable", "disconnect"):
            status, result = request(f"/api/v1/integrations/{key}/native/{action}", {"approved": True})
            assert status == 200
            assert item(result, key)["native_capture"]["enabled"] is False
    assert not any(payload for _, _, payload in runtime.requests)


def test_native_path_fallback_is_ui_api_only_and_reads_no_content(http_api, tmp_path):
    request, _, _ = http_api
    source = tmp_path / "custom/conversations"
    source.mkdir(parents=True)
    (source / "private-synthetic.json").write_text("DO-NOT-READ", encoding="utf-8")
    with patch.object(Path, "open", side_effect=AssertionError("No chat file opens")):
        status, result = request("/api/v1/integrations/lmstudio/native/path", {"approved": True, "path": str(source)})
    assert status == 200
    capture = item(result, "lmstudio")["native_capture"]
    assert capture["source_status"] == "DETECTED"
    assert capture["capability"] == "UNSUPPORTED"
    assert str(source) not in str(result)
