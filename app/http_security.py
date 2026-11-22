"""Browser request boundaries for the single-user loopback HTTP service."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import OrderedDict
from email.message import Message
from http import HTTPStatus
from urllib.parse import urlsplit

CSRF_TOKEN = secrets.token_urlsafe(32)
INGEST_PATHS = frozenset({"/api/v1/turn", "/api/v1/hermes-hook"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class RequestSecurityError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.FORBIDDEN, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def validate_request(headers: Message, method: str, port: int, path: str) -> None:
    """Reject untrusted authorities/origins before any route or static read runs.

    Origin and Fetch Metadata are browser-controlled. Clients without those
    headers still require a session token for non-ingest mutations. This is
    request-intent protection, not an OS user authentication boundary.
    """
    hosts = headers.get_all("Host", [])
    if len(hosts) != 1:
        raise RequestSecurityError("Exactly one Host header is required", HTTPStatus.BAD_REQUEST)
    host = hosts[0].lower()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if port == 80:
        allowed_hosts.update({"127.0.0.1", "localhost"})
    if host not in allowed_hosts:
        raise RequestSecurityError("Host must name this loopback server and port")

    origins = headers.get_all("Origin", [])
    if origins:
        if len(origins) != 1 or origins[0].lower() != f"http://{host}":
            raise RequestSecurityError("Only same-origin requests are allowed")
        # Exact serialized origin comparison rejects paths, credentials, null,
        # multiple origins, alternate ports, and non-HTTP schemes.
        try:
            origin = urlsplit(origins[0])
            if origin.hostname not in {"localhost", "127.0.0.1"} or (origin.port or 80) != port:
                raise ValueError("Unexpected origin authority")
        except ValueError as exc:
            raise RequestSecurityError("Invalid request origin") from exc

    sites = headers.get_all("Sec-Fetch-Site", [])
    if sites and (len(sites) != 1 or sites[0] not in {"same-origin", "none"}):
        raise RequestSecurityError("Cross-site browser requests are not allowed")

    if method in WRITE_METHODS:
        content_types = headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise RequestSecurityError("Content-Type must be application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        if path not in INGEST_PATHS or origins or any(name.lower().startswith("sec-fetch-") for name in headers):
            tokens = headers.get_all("X-NajdiLab-CSRF", [])
            if len(tokens) != 1 or not tokens[0].isascii() or not secrets.compare_digest(tokens[0], CSRF_TOKEN):
                raise RequestSecurityError("A valid session token is required; reload the page", code="CSRF_TOKEN_INVALID")

    lengths = headers.get_all("Content-Length", [])
    if len(lengths) > 1 or headers.get_all("Transfer-Encoding", []):
        raise RequestSecurityError("Ambiguous or unsupported request body framing", HTTPStatus.BAD_REQUEST)
    if lengths and (not lengths[0].isascii() or not lengths[0].isdigit()):
        raise RequestSecurityError("Invalid Content-Length", HTTPStatus.BAD_REQUEST)


# QA-07: a timestamped signature (v2) covers "<unix seconds>.<raw body>" and is accepted once
# within the freshness window. Body-only signatures (v1) and bearer tokens keep working but
# cannot prove freshness; NAJDILAB_REQUIRE_FRESH_SIGNATURE=1 refuses them.
SIGNATURE_MAX_SKEW_SECONDS = 300
_REPLAY_CACHE_LIMIT = 10_000
_seen_signatures: OrderedDict[str, int] = OrderedDict()
_seen_lock = threading.Lock()


def _remember_signature(signature: str, timestamp: int, now: int) -> None:
    with _seen_lock:
        while _seen_signatures and (len(_seen_signatures) >= _REPLAY_CACHE_LIMIT
                                    or next(iter(_seen_signatures.values())) < now - SIGNATURE_MAX_SKEW_SECONDS):
            _seen_signatures.popitem(last=False)
        if signature in _seen_signatures:
            raise RequestSecurityError("This signed request was already accepted; sign each request with a new timestamp",
                                       HTTPStatus.CONFLICT, code="INGEST_REPLAY")
        _seen_signatures[signature] = timestamp


def validate_ingest(headers: Message, raw_body: bytes, *, now: float | None = None) -> None:
    """Authenticate bounded raw bytes before JSON parsing or ingestion."""
    secret = os.environ.get("NAJDILAB_INGEST_TOKEN", "")
    authorization = headers.get_all("Authorization", [])
    signatures = headers.get_all("X-Hermes-Signature-256", [])
    timestamps = headers.get_all("X-NajdiLab-Timestamp", [])
    require_fresh = os.environ.get("NAJDILAB_REQUIRE_FRESH_SIGNATURE") == "1"
    if os.environ.get("NAJDILAB_ALLOW_LEGACY_INGEST") == "1" and not authorization and not signatures and not require_fresh:
        return
    if not secret:
        raise RequestSecurityError("Ingestion is disabled until NAJDILAB_INGEST_TOKEN is configured", HTTPStatus.SERVICE_UNAVAILABLE)
    valid = False
    if len(authorization) == 1 and not signatures and not timestamps:
        if require_fresh:
            raise RequestSecurityError("A timestamped request signature is required; bearer tokens cannot prove freshness",
                                       HTTPStatus.UNAUTHORIZED, code="FRESH_SIGNATURE_REQUIRED")
        expected = ("Bearer " + secret).encode("utf-8")
        valid = hmac.compare_digest(authorization[0].encode("utf-8"), expected)
    elif len(signatures) == 1 and not authorization:
        signature = signatures[0]
        if timestamps:
            if len(timestamps) != 1 or not timestamps[0].isascii() or not timestamps[0].isdigit() or len(timestamps[0]) > 12:
                raise RequestSecurityError("Invalid X-NajdiLab-Timestamp", HTTPStatus.BAD_REQUEST)
            timestamp, current = int(timestamps[0]), int(time.time() if now is None else now)
            message = timestamps[0].encode("ascii") + b"." + raw_body
        elif require_fresh:
            raise RequestSecurityError("A timestamped request signature is required", HTTPStatus.UNAUTHORIZED,
                                       code="FRESH_SIGNATURE_REQUIRED")
        else:
            message = raw_body
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        valid = signature.isascii() and hmac.compare_digest(signature, expected)
        if valid and timestamps:
            # Checked only after the signature is valid, so unauthenticated requests cannot fill the cache.
            if abs(current - timestamp) > SIGNATURE_MAX_SKEW_SECONDS:
                raise RequestSecurityError("The signed request is outside the freshness window", HTTPStatus.UNAUTHORIZED,
                                           code="STALE_SIGNATURE")
            _remember_signature(signature, timestamp, current)
    if not valid:
        raise RequestSecurityError("A valid ingestion credential is required", HTTPStatus.UNAUTHORIZED)
