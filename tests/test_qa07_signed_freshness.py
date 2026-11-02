"""QA-07: optional timestamped ingest signatures give freshness and replay rejection."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import threading
from email.message import Message
from unittest.mock import patch

import pytest

from app import http_security, server
from app.http_security import RequestSecurityError, validate_ingest

SECRET = "synthetic-test-secret"
NOW = 1_800_000_000
BODY = b'{"synthetic":true}'


def headers(*pairs) -> Message:
    message = Message()
    for name, value in pairs:
        message[name] = value
    return message


def sign(body: bytes, timestamp: str | None = None, secret: str = SECRET) -> str:
    payload = body if timestamp is None else timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("NAJDILAB_INGEST_TOKEN", SECRET)
    monkeypatch.setenv("NAJDILAB_ALLOW_LEGACY_INGEST", "0")
    monkeypatch.delenv("NAJDILAB_REQUIRE_FRESH_SIGNATURE", raising=False)
    http_security._seen_signatures.clear()
    yield
    http_security._seen_signatures.clear()


def v2(body=BODY, timestamp=str(NOW)):
    return headers(("X-NajdiLab-Timestamp", timestamp), ("X-Hermes-Signature-256", sign(body, timestamp)))


def test_timestamped_signature_is_accepted_once_and_replay_is_refused():
    validate_ingest(v2(), BODY, now=NOW)
    with pytest.raises(RequestSecurityError) as replay:
        validate_ingest(v2(), BODY, now=NOW + 5)
    assert replay.value.status == 409 and replay.value.code == "INGEST_REPLAY"
    validate_ingest(v2(timestamp=str(NOW + 1)), BODY, now=NOW + 5)  # re-signed retry is fine


@pytest.mark.parametrize("skew", [-301, 301, 86_400])
def test_timestamp_outside_window_is_refused(skew):
    with pytest.raises(RequestSecurityError) as stale:
        validate_ingest(v2(timestamp=str(NOW + skew)), BODY, now=NOW)
    assert stale.value.status == 401 and stale.value.code == "STALE_SIGNATURE"


@pytest.mark.parametrize("skew", [-300, 0, 300])
def test_timestamp_at_window_edge_is_accepted(skew):
    validate_ingest(v2(timestamp=str(NOW + skew)), BODY, now=NOW)


def test_timestamp_must_be_covered_by_the_signature():
    body_only = headers(("X-NajdiLab-Timestamp", str(NOW)), ("X-Hermes-Signature-256", sign(BODY)))
    with pytest.raises(RequestSecurityError) as error:
        validate_ingest(body_only, BODY, now=NOW)
    assert error.value.status == 401
    moved = headers(("X-NajdiLab-Timestamp", str(NOW + 10)), ("X-Hermes-Signature-256", sign(BODY, str(NOW))))
    with pytest.raises(RequestSecurityError):
        validate_ingest(moved, BODY, now=NOW)


@pytest.mark.parametrize("value", ["abc", "-5", "1.5", "9" * 13, ""])
def test_malformed_timestamp_is_refused(value):
    with pytest.raises(RequestSecurityError) as error:
        validate_ingest(headers(("X-NajdiLab-Timestamp", value), ("X-Hermes-Signature-256", sign(BODY, value))), BODY, now=NOW)
    assert error.value.status in (400, 401)


def test_duplicate_timestamp_headers_are_refused():
    message = headers(("X-NajdiLab-Timestamp", str(NOW)), ("X-NajdiLab-Timestamp", str(NOW)),
                      ("X-Hermes-Signature-256", sign(BODY, str(NOW))))
    with pytest.raises(RequestSecurityError) as error:
        validate_ingest(message, BODY, now=NOW)
    assert error.value.status == 400


def test_invalid_signatures_never_enter_the_replay_cache():
    for i in range(50):
        with pytest.raises(RequestSecurityError):
            validate_ingest(headers(("X-NajdiLab-Timestamp", str(NOW)), ("X-Hermes-Signature-256", f"sha256={i:064x}")), BODY, now=NOW)
    assert len(http_security._seen_signatures) == 0


def test_replay_cache_forgets_entries_after_the_window():
    validate_ingest(v2(), BODY, now=NOW)
    validate_ingest(v2(timestamp=str(NOW + 400)), BODY, now=NOW + 400)
    assert list(http_security._seen_signatures.values()) == [NOW + 400]


def test_legacy_body_only_signature_and_bearer_still_work_by_default():
    validate_ingest(headers(("X-Hermes-Signature-256", sign(BODY))), BODY, now=NOW)
    validate_ingest(headers(("X-Hermes-Signature-256", sign(BODY))), BODY, now=NOW)  # documented: no replay protection
    validate_ingest(headers(("Authorization", "Bearer " + SECRET)), BODY, now=NOW)


def test_require_fresh_refuses_legacy_signature_bearer_and_unauthenticated_legacy_mode(monkeypatch):
    monkeypatch.setenv("NAJDILAB_REQUIRE_FRESH_SIGNATURE", "1")
    for message in (headers(("X-Hermes-Signature-256", sign(BODY))), headers(("Authorization", "Bearer " + SECRET))):
        with pytest.raises(RequestSecurityError) as error:
            validate_ingest(message, BODY, now=NOW)
        assert error.value.status == 401 and error.value.code == "FRESH_SIGNATURE_REQUIRED"
    monkeypatch.setenv("NAJDILAB_ALLOW_LEGACY_INGEST", "1")
    with pytest.raises(RequestSecurityError):
        validate_ingest(headers(), BODY, now=NOW)
    validate_ingest(v2(), BODY, now=NOW)


def test_http_turn_accepts_a_fresh_request_once_and_refuses_its_replay():
    httpd = server.NajdiLabHTTPServer(("127.0.0.1", 0), server.NajdiLabHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    timestamp = str(int(__import__("time").time()))
    request_headers = {"Host": f"127.0.0.1:{httpd.server_port}", "Content-Type": "application/json",
                       "X-NajdiLab-Timestamp": timestamp, "X-Hermes-Signature-256": sign(BODY, timestamp)}
    try:
        with patch.object(server, "ingest_turn", return_value={"accepted": True}) as ingest:
            statuses = []
            for _ in range(2):
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
                conn.request("POST", "/api/v1/turn", BODY, request_headers)
                response = conn.getresponse()
                statuses.append((response.status, json.loads(response.read() or b"{}").get("code")))
                conn.close()
        assert statuses[0][0] in (200, 201)
        assert statuses[1] == (409, "INGEST_REPLAY")
        assert ingest.call_count == 1, "a replay must not reach ingestion"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
