"""Native capture capability gates. No source content reader or collector is enabled.

Detection is metadata, not installed-version/schema or completed-turn proof.
See docs/native-capture-research.md for the independent source investigation.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .db import utc_now
from .local_sources import source_metadata, valid_local_path


class NativeCaptureError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


CAPABILITIES = {
    "hermes": ("BLOCKED", "No verified zero-write acquisition of native completed-turn receipts. Live SQLite/WAL reads can coordinate through source sidecars; raw live copies are not proven atomic. Hermes webhook remains blocked."),
    "lmstudio": ("UNSUPPORTED", "No validated native-chat completion format. Official LM Studio documentation warns against relying on its conversation JSON structure; its documented inference API is not native chat-history access."),
    "ollama": ("BLOCKED", "Ollama Desktop persists partial assistant text while stream may already be false. Its database lacks a reliable durable success/error/cancel marker and rewrites message IDs. Polling cannot prove completed turns."),
}
SOURCE_NAMES = {"hermes": ("state.db", "file"), "lmstudio": ("conversations", "directory"), "ollama": ("db.sqlite", "file")}


class NativeCaptureDiagnostics:
    """Owned/serialized by IntegrationManager. Consent never overrides a blocker."""

    def __init__(self, *, home: Path, local_app_data: Path, platform: str):
        self._defaults = {
            "hermes": home / ".hermes/state.db",
            "lmstudio": home / ".lmstudio/conversations",
            "ollama": local_app_data / "Ollama/db.sqlite" if platform == "win32" else home / "Library/Application Support/Ollama/db.sqlite" if platform == "darwin" else None,
        }
        self._paths = dict(self._defaults)
        self._states = {}
        for key, (capability, reason) in CAPABILITIES.items():
            self._states[key] = {
                "capability": capability, "reason": reason, "mechanism": "NONE_ENABLED",
                "source_status": "NOT_CHECKED", "source_location": "DEFAULT",
                "version": "NOT_VERIFIED", "format_verification": "NOT_TESTED",
                "connection": "DISCONNECTED", "enabled": False,
                "last_checked_at": None, "last_capture_at": None, "last_action_at": None,
                "last_error": None, "local_disconnect_verified": True,
            }

    def snapshot(self, key: str) -> dict:
        return copy.deepcopy(self._states[key])

    def _probe(self, key: str, path: Path | None) -> str:
        return "NOT_APPLICABLE" if path is None else source_metadata(path, SOURCE_NAMES[key][1])

    def discover(self) -> None:
        for key, path in self._paths.items():
            state = self._states[key]
            state["source_status"] = self._probe(key, path)
            state["last_checked_at"] = utc_now()
            state["last_error"] = None if state["source_status"] == "DETECTED" else {
                "code": "NATIVE_SOURCE_" + state["source_status"],
                "message": "Native source metadata was not detected or could not be inspected safely. No contents were read.",
            }

    def action(self, key: str, action: str, payload: dict) -> None:
        if key not in self._states or action not in {"path", "connect", "enable", "disable", "disconnect"}:
            raise NativeCaptureError("UNKNOWN_ACTION", "Unknown native capture action.", 404)
        if payload.get("approved") is not True:
            raise NativeCaptureError("APPROVAL_REQUIRED", "Separate explicit approval is required for this native action.", 403)
        if set(payload) - ({"approved", "path"} if action == "path" else {"approved"}):
            raise NativeCaptureError("INVALID_PAYLOAD", "Only documented native action fields are allowed.")
        state = self._states[key]
        if action in {"connect", "enable"}:
            code = "NATIVE_CAPTURE_" + state["capability"]
            state["last_error"] = {"code": code, "message": state["reason"]}
            raise NativeCaptureError(code, state["reason"], 409)
        if action == "path":
            value = payload.get("path")
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise NativeCaptureError("INVALID_SOURCE_PATH", "Choose an absolute local source path.")
            path = Path(value)
            if not valid_local_path(path) or path.name != SOURCE_NAMES[key][0]:
                raise NativeCaptureError("INVALID_SOURCE_PATH", "Choose the expected local source filename/directory; network, URI, device, traversal and stream paths are refused.")
            if self._probe(key, self._defaults[key]) == "DETECTED":
                raise NativeCaptureError("AUTO_SOURCE_AVAILABLE", "Automatic source detection succeeded; manual fallback is unavailable.", 409)
            result = self._probe(key, path)
            if result != "DETECTED":
                raise NativeCaptureError("NATIVE_SOURCE_" + result, "Selected source is missing, inaccessible or unsafe; no contents were read.")
            self._paths[key] = path
            state.update(source_status="DETECTED", source_location="CUSTOM", last_checked_at=utc_now(), last_error=None)
        # No supported collector exists. OFF is a verifiable local invariant,
        # never a claim that an external application stopped communicating.
        state.update(enabled=False, connection="DISCONNECTED", local_disconnect_verified=True, last_action_at=utc_now())
