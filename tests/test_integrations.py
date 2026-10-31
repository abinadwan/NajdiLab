"""Real connector behavior against disposable servers, never installed runtimes."""
import json
import os
import socket
import tempfile
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from app.integrations import CONNECTORS, IntegrationError, IntegrationManager, request_json


class RuntimeFixture:
    def __init__(self):
        self.requests = []
        self.models = ["synthetic-model"]
        self.status = 200
        self.raw = None
        self.delay = 0
        self.wire = None
        self.wire_delay = 0
        self.started = threading.Event()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.respond(None)

            def do_POST(self):
                self.respond(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))

            def respond(self, payload):
                fixture.requests.append((self.path, dict(self.headers), payload))
                fixture.started.set()
                time.sleep(fixture.delay)
                if fixture.wire is not None:
                    try:
                        for fragment in fixture.wire:
                            self.connection.sendall(fragment)
                            time.sleep(fixture.wire_delay)
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                if payload is None:
                    value = ({"data": [{"id": m} for m in fixture.models]} if self.path == "/v1/models"
                             else {"models": [{"name": m} for m in fixture.models]})
                else:
                    value = ({"choices": [{"message": {"content": "OK"}}]} if self.path == "/v1/chat/completions"
                             else {"response": "OK", "done": True})
                raw = fixture.raw if fixture.raw is not None else json.dumps(value).encode()
                try:
                    self.send_response(fixture.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Location", "http://169.254.169.254/secret")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (OSError, ConnectionError):
                    pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.http.server_port

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(3)


@pytest.fixture
def runtime():
    fixture = RuntimeFixture()
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.fixture
def manager(runtime, tmp_path):
    # Only the fixed registry's ports are replaced, never endpoint data from a request.
    registry = {key: replace(value, port=runtime.port) if value.kind == "model_runtime" else value
                for key, value in CONNECTORS.items()}
    return IntegrationManager(connectors=registry, home=tmp_path)


def item(snapshot, key="lmstudio"):
    return next(value for value in snapshot["items"] if value["id"] == key)


def connect_and_select(manager, key="lmstudio"):
    manager.action(key, "connect", {"approved": True})
    return manager.action(key, "select", {"approved": True, "model": "synthetic-model"})


def test_approval(manager, key="lmstudio"):
    return {"approved": True, "selection_revision": item(manager.snapshot(), key).get("selection_revision", 0)}


test_approval.__test__ = False


def test_snapshot_is_passive_and_discovery_never_connects(manager, runtime):
    assert item(manager.snapshot())["connection"] == "DISCONNECTED"
    assert runtime.requests == []
    snapshot = manager.discover()
    for key in ("lmstudio", "ollama"):
        service = item(snapshot, key)
        assert service["availability"] == "AVAILABLE"
        assert service["connection"] == "DISCONNECTED"
        assert service["models"] == ["synthetic-model"]
        assert service["last_checked_at"]
    assert len(runtime.requests) == 2
    manager.discover()  # bounded automatic rescans
    assert len(runtime.requests) == 2
    assert all(payload is None for _, _, payload in runtime.requests)


@pytest.mark.parametrize("key", ["lmstudio", "ollama"])
def test_test_uses_only_synthetic_payload_and_verified_disconnect(manager, runtime, key):
    connect_and_select(manager, key)
    result = item(manager.action(key, "test", test_approval(manager, key)), key)
    assert result["last_test"]["status"] == "PASSED"
    path, headers, payload = runtime.requests[-1]
    assert not any(name.lower() in {"authorization", "cookie", "x-hermes-signature-256"} for name in headers)
    if key == "lmstudio":
        assert path == "/v1/chat/completions"
        assert payload == {"model": "synthetic-model", "messages": [{"role": "user", "content": "Reply with OK."}], "stream": False, "max_tokens": 16, "temperature": 0}
    else:
        assert path == "/api/generate"
        assert payload == {"model": "synthetic-model", "prompt": "Reply with OK.", "stream": False, "options": {"num_predict": 16, "temperature": 0}}
    assert "OK" not in json.dumps(result)
    result = item(manager.action(key, "disconnect", {"approved": True}), key)
    assert result["connection"] == "DISCONNECTED"
    assert result["selected_model"] is None
    assert result["disconnect"]["local_verified"] is True
    count = len(runtime.requests)
    with pytest.raises(IntegrationError, match="Connect"):
        manager.action(key, "test", {"approved": True})
    assert len(runtime.requests) == count


@pytest.mark.parametrize("action", ["connect", "disconnect", "select", "test"])
@pytest.mark.parametrize("approval", [None, False, "true", 1])
def test_consent_requires_exact_true_and_has_no_network_side_effect(manager, runtime, action, approval):
    with pytest.raises(IntegrationError) as exc:
        manager.action("lmstudio", action, {"approved": approval})
    assert exc.value.code == "APPROVAL_REQUIRED"
    assert runtime.requests == []


@pytest.mark.parametrize("payload", [{"url": "http://evil"}, {"headers": {"Authorization": "secret"}}, {"prompt": "private"}, {"model": ["bad"]}])
def test_rejects_unexpected_or_invalid_payload_before_network(manager, runtime, payload):
    with pytest.raises(IntegrationError):
        manager.action("lmstudio", "connect", {"approved": True, **payload})
    assert runtime.requests == []


def test_stale_model_revokes_selection_and_prevents_generation(manager, runtime):
    connect_and_select(manager)
    runtime.models = ["replacement"]
    result = item(manager.action("lmstudio", "test", test_approval(manager)))
    assert result["selected_model"] is None
    assert result["last_error"]["code"] == "MODEL_UNAVAILABLE"
    assert not any(payload for _, _, payload in runtime.requests)


@pytest.mark.parametrize("status,raw,expected", [(401, b"secret-body", "AUTH_REQUIRED"), (403, b"secret-body", "AUTH_REQUIRED"), (302, b"secret-body", "REDIRECT_BLOCKED"), (500, b"secret-body", "HTTP_ERROR"), (200, b"not-json-secret", "INVALID_RESPONSE"), (200, b"{}", "INVALID_RESPONSE"), (200, b"[1]", "INVALID_RESPONSE"), (200, b"x" * 262145, "RESPONSE_TOO_LARGE")], ids=["unauthorized", "forbidden", "redirect", "upstream", "json", "schema", "array", "oversize"])
def test_detailed_errors_discard_untrusted_response(manager, runtime, status, raw, expected):
    runtime.status, runtime.raw = status, raw
    service = item(manager.discover())
    assert service["last_error"]["code"] == expected
    assert service["availability"] == "ERROR"
    assert service["selected_model"] is None
    assert "secret" not in json.dumps(service)
    assert len(runtime.requests) == 2  # no redirect request


def test_known_directories_only_metadata_no_configs_or_history(manager, tmp_path):
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "config.yaml").write_text("secret: DO-NOT-READ")
    with patch.object(Path, "read_text", side_effect=AssertionError("No content reads")):
        service = item(manager.discover(), "hermes")
    assert service["installation"] == "DETECTED"
    assert "DO-NOT-READ" not in json.dumps(service)
    assert str(tmp_path) not in json.dumps(service)


def test_symlink_marker_is_not_followed(manager, tmp_path):
    target = tmp_path / "other"
    target.mkdir()
    try:
        (tmp_path / ".hermes").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted by this Windows account")
    assert item(manager.discover(), "hermes")["installation"] == "NOT_DETECTED"


def test_hermes_is_blocked_and_external_disconnect_never_claimed(manager, runtime):
    for action in ("connect", "select", "test"):
        with pytest.raises(IntegrationError) as exc:
            manager.action("hermes", action, {"approved": True})
        assert exc.value.code == "HERMES_UNSAFE_SOURCE"
    service = item(manager.action("hermes", "disconnect", {"approved": True}), "hermes")
    assert service["connection"] == "BLOCKED"
    assert service["disconnect"]["local_verified"] is True
    assert service["disconnect"]["external_status"] == "UNVERIFIED"
    assert runtime.requests == []


def test_transport_ignores_proxies_and_never_resolves_hostnames(runtime):
    spec = replace(CONNECTORS["lmstudio"], port=runtime.port)
    with patch.dict(os.environ, {"HTTP_PROXY": "http://example.invalid:1", "ALL_PROXY": "http://example.invalid:1"}), patch.object(socket, "getaddrinfo", side_effect=AssertionError("No DNS")):
        assert request_json(spec, "/v1/models")["data"] == [{"id": "synthetic-model"}]


def test_transport_has_total_deadline(runtime):
    runtime.delay = .6
    spec = replace(CONNECTORS["lmstudio"], port=runtime.port)
    start = time.monotonic()
    with pytest.raises(IntegrationError) as exc:
        request_json(spec, "/v1/models", timeout=.1)
    assert exc.value.code == "TIMEOUT"
    assert time.monotonic() - start < .5


def test_disconnect_waits_for_inflight_test_then_revokes(manager, runtime):
    connect_and_select(manager)
    runtime.started.clear()
    runtime.delay = .1
    approval = test_approval(manager)
    testing = threading.Thread(target=lambda: manager.action("lmstudio", "test", approval))
    testing.start()
    assert runtime.started.wait(2)
    snapshot = manager.action("lmstudio", "disconnect", {"approved": True})
    testing.join(2)
    assert not testing.is_alive()
    assert item(snapshot)["disconnect"]["local_verified"] is True
    assert item(manager.snapshot())["connection"] == "DISCONNECTED"


def test_restart_revokes_consent(manager):
    connect_and_select(manager)
    fresh = IntegrationManager(connectors=manager.connectors, home=manager.home)
    assert item(fresh.snapshot())["connection"] == "DISCONNECTED"
    assert item(fresh.snapshot())["selected_model"] is None


def test_unknown_connector_or_action_is_rejected(manager, runtime):
    for key, action in (("http://127.0.0.1", "connect"), ("lmstudio", "generate")):
        with pytest.raises(IntegrationError):
            manager.action(key, action, {"approved": True})
    assert runtime.requests == []


def test_stale_tab_cannot_generate_with_unapproved_model(manager, runtime):
    connect_and_select(manager)
    approval = test_approval(manager)
    runtime.models.append("replacement")
    manager.action("lmstudio", "select", {"approved": True, "model": "replacement"})
    with pytest.raises(IntegrationError) as exc:
        manager.action("lmstudio", "test", approval)
    assert exc.value.code == "STALE_APPROVAL"
    assert not any(payload for _, _, payload in runtime.requests)


def test_unverified_filesystem_is_rejected_before_stat(tmp_path):
    from app import integrations
    with patch.object(integrations, "local_filesystem", return_value=False), patch.object(Path, "lstat", side_effect=AssertionError("No metadata access on unverified drive")):
        assert integrations.marker_present(tmp_path, ".hermes") is False


def test_total_wire_budget_counts_headers(runtime):
    from app.integrations import BoundedReader
    import io
    reader = BoundedReader(io.BytesIO(b"abc\ndef\n"), limit=6)
    assert reader.readline() == b"abc\n"
    with pytest.raises(IntegrationError) as exc:
        reader.readline()
    assert exc.value.code == "RESPONSE_TOO_LARGE"


def test_chunk_trailers_cannot_escape_total_wire_limit(runtime):
    # Fewer than CPython's newer 100-trailer guard, but above our wire budget.
    runtime.wire = [b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n', *[b'X-Trailer: ' + b'x' * 9000 + b'\r\n'] * 48, b'\r\n']
    with pytest.raises(IntegrationError) as exc:
        request_json(replace(CONNECTORS["lmstudio"], port=runtime.port), "/v1/models")
    assert exc.value.code == "RESPONSE_TOO_LARGE"


def test_trickled_headers_cannot_extend_total_deadline(runtime):
    runtime.wire = [b'HTTP/1.1 200 OK\r\n', *[b'X'] * 40]
    runtime.wire_delay = .02
    # Force the total-deadline shutdown path rather than a per-read timeout.
    class SlowTimeoutSocket(socket.socket):
        def settimeout(self, value):
            super().settimeout(value * 10 if value else value)

    start = time.monotonic()
    with patch.object(socket, 'socket', SlowTimeoutSocket), pytest.raises(IntegrationError) as exc:
        request_json(replace(CONNECTORS["lmstudio"], port=runtime.port), "/v1/models", timeout=.1)
    assert exc.value.code == "TIMEOUT"
    assert time.monotonic() - start < .5


def test_deadline_takes_precedence_over_partial_headers(runtime):
    from email.message import Message
    from types import SimpleNamespace
    from app import integrations

    def partial_response(connection):
        # Some CPython/platform versions return partial headers after shutdown.
        time.sleep(.03)
        return SimpleNamespace(status=200, headers=Message())

    with patch.object(integrations.http.client.HTTPConnection, 'getresponse', partial_response), pytest.raises(IntegrationError) as exc:
        request_json(replace(CONNECTORS["lmstudio"], port=runtime.port), "/v1/models", timeout=.01)
    assert exc.value.code == "TIMEOUT"


@pytest.mark.skipif(os.name != "nt", reason="Windows drive type boundary")
def test_mapped_network_drive_is_rejected_without_stat():
    from app import integrations
    with patch("ctypes.windll.kernel32.GetDriveTypeW", return_value=4), patch.object(Path, "lstat", side_effect=AssertionError("No remote stat")):
        assert integrations.marker_present(Path("H:/synthetic-home"), ".hermes") is False


@pytest.mark.parametrize("models", [["bad\nmodel"], ["../escape"], ["x" * 257], ["valid"] * 1001], ids=["control", "pathlike", "long", "many"])
def test_invalid_model_lists_fail_closed(manager, runtime, models):
    runtime.models = models
    assert item(manager.discover())["last_error"]["code"] == "INVALID_RESPONSE"


def test_no_models_and_unreachable_are_distinct(manager, runtime):
    runtime.models = []
    assert item(manager.discover())["availability"] == "NO_MODELS"
    runtime.http.shutdown()
    runtime.http.server_close()
    service = item(manager.action("lmstudio", "connect", {"approved": True}))
    assert service["last_error"]["code"] == "UNREACHABLE"
