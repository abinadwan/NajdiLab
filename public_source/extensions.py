"""Explicit private-extension interface. No discovery, loader or historical imports."""
from typing import Protocol


class Extension(Protocol):
    def handle(self, method: str, path: str, payload: dict) -> tuple[int, dict]: ...


class UnavailableExtension:
    def handle(self, method: str, path: str, payload: dict) -> tuple[int, dict]:
        return 503, {'ok': False, 'code': 'EXTENSION_UNAVAILABLE',
                     'message': 'Private research and model execution are not included in this source-only candidate.'}
