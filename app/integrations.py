"""Local integration consent and bounded probes; never manages external services."""
from __future__ import annotations

import copy
import http.client
import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .db import utc_now
from .local_sources import marker_present
from .native_capture import NativeCaptureDiagnostics, NativeCaptureError


class IntegrationError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Connector:
    name: str
    kind: str
    marker: str
    port: int = 0
    models_path: str = ""
    test_path: str = ""


CONNECTORS = {
    "hermes": Connector("Hermes Agent", "conversation_source", ".hermes"),
    "lmstudio": Connector("LM Studio", "model_runtime", ".lmstudio", 1234, "/v1/models", "/v1/chat/completions"),
    "ollama": Connector("Ollama", "model_runtime", ".ollama", 11434, "/api/tags", "/api/generate"),
}
HERMES_BLOCK = "Hermes collection is BLOCKED: sender-side filtering and external disconnect are unverified."
MAX_RESPONSE = 256 * 1024
MAX_MODELS = 1000
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@+\-]{0,255}")


class BoundedReader:
    """Count headers, chunk framing, trailers and body together, before parsing."""

    def __init__(self, source, *, limit=MAX_RESPONSE + 64 * 1024):
        self.source = source
        self.remaining = limit

    def _read(self, method, size):
        size = self.remaining + 1 if size is None or size < 0 else min(size, self.remaining + 1)
        value = method(size)
        self.remaining -= len(value)
        if self.remaining < 0:
            raise IntegrationError("RESPONSE_TOO_LARGE", "Runtime response exceeds the total wire limit.")
        return value

    def read(self, size=-1):
        return self._read(self.source.read, size)

    def readline(self, size=-1):
        return self._read(self.source.readline, size)

    def close(self):
        self.source.close()

    def flush(self):
        self.source.flush()


class BoundedResponse(http.client.HTTPResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fp = BoundedReader(self.fp)


def request_json(connector: Connector, path: str, payload: dict | None = None, *, timeout: float = 3) -> dict:
    """Numeric IPv4 socket: no DNS, proxy, redirect, credential or user URL support.

    A deadline shuts down the socket even if a peer trickles headers/body bytes.
    Neither upstream body nor exception text is returned in an error.
    """
    if not connector.port or path not in {connector.models_path, connector.test_path}:
        raise IntegrationError("ENDPOINT_BLOCKED", "Endpoint is not in the connector registry.")
    connection = http.client.HTTPConnection("127.0.0.1", connector.port, timeout=timeout)
    connection.response_class = BoundedResponse
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    expired = threading.Event()
    deadline = time.monotonic() + timeout

    def expire():
        expired.set()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    try:
        sock.settimeout(timeout)
        timer.start()
        sock.connect(("127.0.0.1", connector.port))
        connection.sock = sock
        if expired.is_set():
            raise TimeoutError
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request("GET" if body is None else "POST", path, body=body, headers=headers)
        response = connection.getresponse()
        # Shutdown can yield partial headers instead of raising on some platforms.
        if expired.is_set() or time.monotonic() >= deadline:
            raise TimeoutError
        if response.status in {401, 403}:
            raise IntegrationError("AUTH_REQUIRED", "Runtime requires authentication; credential forwarding is unsupported.")
        if 300 <= response.status < 400:
            raise IntegrationError("REDIRECT_BLOCKED", "Runtime redirects are refused.")
        if response.status != 200:
            raise IntegrationError("HTTP_ERROR", "Runtime returned an unsuccessful HTTP status.")
        lengths = response.headers.get_all("Content-Length", [])
        encodings = response.headers.get_all("Transfer-Encoding", [])
        if len(lengths) > 1 or (lengths and encodings) or (encodings and encodings != ["chunked"]):
            raise IntegrationError("INVALID_RESPONSE", "Runtime response framing is unsupported.")
        if lengths and (not lengths[0].isascii() or not lengths[0].isdigit()):
            raise IntegrationError("INVALID_RESPONSE", "Runtime response length is invalid.")
        if lengths and int(lengths[0]) > MAX_RESPONSE:
            raise IntegrationError("RESPONSE_TOO_LARGE", "Runtime response exceeds the size limit.")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise IntegrationError("INVALID_RESPONSE", "Compressed runtime responses are unsupported.")
        if response.headers.get_content_type() != "application/json":
            raise IntegrationError("INVALID_RESPONSE", "Runtime response must be JSON.")
        raw = response.read(MAX_RESPONSE + 1)
        if expired.is_set() or time.monotonic() >= deadline:
            raise TimeoutError
        if len(raw) > MAX_RESPONSE:
            raise IntegrationError("RESPONSE_TOO_LARGE", "Runtime response exceeds the size limit.")
        if lengths and len(raw) != int(lengths[0]):
            raise IntegrationError("INVALID_RESPONSE", "Runtime response was incomplete.")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except IntegrationError:
        raise
    except (TimeoutError, socket.timeout):
        raise IntegrationError("TIMEOUT", "Runtime request exceeded its deadline.") from None
    except ConnectionRefusedError:
        raise IntegrationError("UNREACHABLE", "No runtime API is listening at the known endpoint.") from None
    except (OSError, http.client.HTTPException, ValueError, RecursionError):
        if expired.is_set():
            raise IntegrationError("TIMEOUT", "Runtime request exceeded its deadline.") from None
        raise IntegrationError("INVALID_RESPONSE", "Runtime is unavailable or returned an invalid response.") from None
    finally:
        timer.cancel()
        connection.close()
        sock.close()


class IntegrationManager:
    """One process owns consent. Lock covers I/O so disconnect waits for in-flight work."""

    def __init__(self, *, connectors=None, home: Path | None = None, local_app_data: Path | None = None, platform: str | None = None):
        self.connectors = dict(CONNECTORS if connectors is None else connectors)
        self.home = Path.home() if home is None else home
        if local_app_data is None:
            # Explicit fixture homes never inspect the operator's AppData.
            local_app_data = Path(os.environ.get("LOCALAPPDATA", str(self.home / "AppData/Local"))) if home is None else self.home / "AppData/Local"
        self.native_capture = NativeCaptureDiagnostics(home=self.home, local_app_data=local_app_data, platform=sys.platform if platform is None else platform)
        self._lock = threading.RLock()
        self._last_discovery = float("-inf")
        self._states = {}
        for key, spec in self.connectors.items():
            blocked = spec.kind == "conversation_source"
            self._states[key] = {
                "id": key, "name": spec.name, "kind": spec.kind,
                "endpoint": f"http://127.0.0.1:{spec.port}" if spec.port else None,
                "installation": "NOT_CHECKED", "availability": "BLOCKED" if blocked else "NOT_CHECKED",
                "connection": "BLOCKED" if blocked else "DISCONNECTED", "models": [], "selected_model": None, "selection_revision": 0,
                "last_checked_at": None, "last_success_at": None, "last_test": None,
                "last_error": {"code": "HERMES_UNSAFE_SOURCE", "message": HERMES_BLOCK} if blocked else None,
                "disconnect": {"local_verified": blocked, "external_status": "UNVERIFIED" if blocked else "NOT_MANAGED", "verified_at": None},
            }

    def snapshot(self) -> dict:
        with self._lock:
            items = copy.deepcopy(list(self._states.values()))
            for state in items:
                state["native_capture"] = self.native_capture.snapshot(state["id"])
            return {"ok": True, "consent_scope": "server_process", "items": items}

    def _failure(self, state: dict, error: IntegrationError):
        state["selection_revision"] += 1
        state.update(availability="ERROR", models=[], selected_model=None,
                     last_error={"code": error.code, "message": str(error)})

    def _refresh(self, key: str) -> bool:
        state, spec = self._states[key], self.connectors[key]
        state["last_checked_at"] = utc_now()
        try:
            value = request_json(spec, spec.models_path)
            rows = value.get("data" if key == "lmstudio" else "models")
            field = "id" if key == "lmstudio" else "name"
            if not isinstance(rows, list) or len(rows) > MAX_MODELS:
                raise ValueError
            models = []
            for row in rows:
                model = row.get(field) if isinstance(row, dict) else None
                if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
                    raise ValueError
                models.append(model)
            state.update(models=sorted(set(models)), availability="AVAILABLE" if models else "NO_MODELS",
                         last_success_at=utc_now(), last_error=None)
            if state["selected_model"] not in models:
                if state["selected_model"] is not None:
                    state["selection_revision"] += 1
                state["selected_model"] = None
            return True
        except (ValueError, TypeError):
            self._failure(state, IntegrationError("INVALID_RESPONSE", "Runtime returned an invalid model list."))
        except IntegrationError as error:
            self._failure(state, error)
        return False

    def discover(self) -> dict:
        with self._lock:
            if time.monotonic() - self._last_discovery < 10:
                return self.snapshot()
            self.native_capture.discover()
            for key, spec in self.connectors.items():
                state = self._states[key]
                state["installation"] = "DETECTED" if marker_present(self.home, spec.marker) else "NOT_DETECTED"
                if spec.kind == "model_runtime":
                    self._refresh(key)
                else:
                    state["last_checked_at"] = utc_now()
            self._last_discovery = time.monotonic()
            return self.snapshot()

    def native_action(self, key: str, action: str, payload: dict) -> dict:
        with self._lock:
            try:
                self.native_capture.action(key, action, payload)
            except NativeCaptureError as error:
                raise IntegrationError(error.code, str(error), error.status) from None
            return self.snapshot()

    def action(self, key: str, action: str, payload: dict) -> dict:
        with self._lock:
            if key not in self.connectors or action not in {"connect", "disconnect", "select", "test"}:
                raise IntegrationError("UNKNOWN_ACTION", "Unknown integration or action.", 404)
            if payload.get("approved") is not True:
                raise IntegrationError("APPROVAL_REQUIRED", "Explicit human approval is required.", 403)
            allowed = {"approved", "model"} if action == "select" else {"approved", "selection_revision"} if action == "test" else {"approved"}
            if set(payload) - allowed:
                raise IntegrationError("INVALID_PAYLOAD", "Only the documented action fields are allowed.")
            state, spec = self._states[key], self.connectors[key]
            if action == "disconnect":
                self.native_capture.action(key, "disconnect", {"approved": True})
                state["selection_revision"] += 1
                state.update(connection="BLOCKED" if spec.kind == "conversation_source" else "DISCONNECTED",
                             models=[], selected_model=None, last_test=None)
                state["disconnect"] = {"local_verified": True, "external_status": "UNVERIFIED" if spec.kind == "conversation_source" else "NOT_MANAGED", "verified_at": utc_now()}
                return self.snapshot()
            if spec.kind == "conversation_source":
                raise IntegrationError("HERMES_UNSAFE_SOURCE", HERMES_BLOCK, 409)
            if action == "connect":
                if self._refresh(key):
                    state["selection_revision"] += 1
                    state["connection"] = "CONNECTED"
                    state["disconnect"]["local_verified"] = False
                return self.snapshot()
            if state["connection"] != "CONNECTED":
                raise IntegrationError("NOT_CONNECTED", "Connect the runtime before selecting or testing a model.", 409)
            if action == "select":
                model = payload.get("model")
                if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
                    raise IntegrationError("INVALID_MODEL", "Choose a model from the discovered list.")
            else:
                revision = payload.get("selection_revision")
                if type(revision) is not int or revision != state["selection_revision"]:
                    raise IntegrationError("STALE_APPROVAL", "Model selection changed; refresh and approve the displayed model again.", 409)
                model = state["selected_model"]
                if model is None:
                    raise IntegrationError("MODEL_REQUIRED", "Select a model before testing.", 409)
            if not self._refresh(key):
                if action == "test":
                    state["last_test"] = {"status": "FAILED", "at": utc_now()}
                return self.snapshot()
            if model not in state["models"]:
                state.update(selected_model=None, last_error={"code": "MODEL_UNAVAILABLE", "message": "Selected model is no longer available; choose again."})
                return self.snapshot()
            state["selected_model"] = model
            if action == "select":
                state["selection_revision"] += 1
            state["last_test"] = None
            if action == "test":
                self._test(key, model)
            return self.snapshot()

    def _test(self, key: str, model: str):
        state, spec = self._states[key], self.connectors[key]
        if key == "lmstudio":
            payload = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}], "stream": False, "max_tokens": 16, "temperature": 0}
        else:
            payload = {"model": model, "prompt": "Reply with OK.", "stream": False, "options": {"num_predict": 16, "temperature": 0}}
        try:
            value = request_json(spec, spec.test_path, payload, timeout=15)
            if key == "lmstudio":
                content = value["choices"][0]["message"]["content"]
            else:
                content = value["response"]
                if value.get("done") is not True:
                    raise ValueError
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            state["last_test"] = {"status": "PASSED", "at": utc_now()}
            state["last_success_at"] = utc_now()
        except (KeyError, IndexError, TypeError, ValueError):
            self._failure(state, IntegrationError("INVALID_RESPONSE", "Runtime did not return a completed text response."))
            state["last_test"] = {"status": "FAILED", "at": utc_now()}
        except IntegrationError as error:
            self._failure(state, error)
            state["last_test"] = {"status": "FAILED", "at": utc_now()}
