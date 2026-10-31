"""Request-boundary regressions using disposable loopback ports and no project data."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import os
import json
import threading
import unittest
from unittest.mock import patch
from email.message import Message

from app import server
from app.http_security import validate_request
from http_client import SingleWriteHTTPConnection


class HttpSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.NajdiLabHTTPServer(("127.0.0.1", 0), server.NajdiLabHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.http.server_address[1]
        cls.authority = f"127.0.0.1:{cls.port}"
        cls.origin = f"http://{cls.authority}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=5)

    def request(self, method="GET", path="/api/v1/config", headers=(), body=None):
        connection = SingleWriteHTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.putrequest(method, path, skip_host=True)
            for name, value in headers:
                connection.putheader(name, value)
            if body is not None:
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def session_token(self):
        status, body, headers = self.request(path="/api/v1/session", headers=[("Host", self.authority), ("Origin", self.origin)])
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers["Cache-Control"])
        token = json.loads(body)["csrf_token"]
        self.assertGreaterEqual(len(token), 32)
        return token

    def test_rejects_rebinding_host_on_reads_and_writes(self):
        for method in ("GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            with self.subTest(method=method):
                status, _, _ = self.request(method, headers=[("Host", f"attacker.example:{self.port}")])
                self.assertEqual(status, 403)

    def test_rejects_missing_duplicate_and_malformed_host(self):
        for hosts in ([], [self.authority, self.authority], ["localhost"], ["user@" + self.authority], [self.authority + "/"], [f"127.0.0.1:{self.port + 1}"], ["127.1:" + str(self.port)]):
            with self.subTest(hosts=hosts):
                status, _, _ = self.request(headers=[("Host", host) for host in hosts])
                self.assertIn(status, (400, 403))

    def test_accepts_only_loopback_host_at_listening_port(self):
        for host in (self.authority, f"localhost:{self.port}", f"LOCALHOST:{self.port}"):
            status, _, _ = self.request(headers=[("Host", host)])
            self.assertEqual(status, 200)

    def test_standard_http_port_can_use_implicit_port(self):
        for host in ("127.0.0.1", "localhost"):
            headers = Message()
            headers["Host"] = host
            headers["Origin"] = "http://" + host
            try:
                validate_request(headers, "GET", 80, "/api/v1/session")
            except Exception as exc:
                self.fail(f"Standard HTTP origin was rejected: {exc}")

    def test_rejects_cross_origin_and_null_on_every_method(self):
        for method in ("GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            for origin in ("https://attacker.example", "null", "http://localhost:1", self.origin + "/", self.origin + "@attacker.example"):
                with self.subTest(method=method, origin=origin):
                    status, _, _ = self.request(method, headers=[("Host", self.authority), ("Origin", origin)])
                    self.assertEqual(status, 403)

    def test_rejects_duplicate_origin_and_cross_site_metadata(self):
        for headers in ([('Origin', self.origin), ('Origin', self.origin)], [('Sec-Fetch-Site', 'cross-site')], [('Sec-Fetch-Site', 'same-site')]):
            status, _, _ = self.request(headers=[("Host", self.authority), *headers])
            self.assertEqual(status, 403)

    def test_cross_origin_static_and_session_are_protected(self):
        for path in ("/", "/app.js", "/api/v1/session"):
            status, body, _ = self.request(path=path, headers=[("Host", self.authority), ("Origin", "https://attacker.example")])
            self.assertEqual(status, 403)
            self.assertNotIn(b"csrf_token", body)

    def test_browser_writes_require_valid_session_token(self):
        for method in ("POST", "PATCH", "DELETE"):
            for token in (None, "wrong"):
                headers = [("Host", self.authority), ("Origin", self.origin), ("Content-Type", "application/json")]
                if token is not None:
                    headers.append(("X-NajdiLab-CSRF", token))
                status, body, _ = self.request(method, "/api/v1/no-such-route", headers, b"{}")
                self.assertEqual(status, 403)
                self.assertEqual(json.loads(body).get("code"), "CSRF_TOKEN_INVALID")

    def test_session_allows_browser_and_machine_writes(self):
        token = self.session_token()
        for method in ("POST", "PATCH", "DELETE"):
            for extra in ([("X-NajdiLab-CSRF", token)], [("Origin", self.origin), ("X-NajdiLab-CSRF", token)], [("Sec-Fetch-Site", "same-origin"), ("X-NajdiLab-CSRF", token)]):
                status, _, _ = self.request(method, "/api/v1/no-such-route", [("Host", self.authority), ("Content-Type", "application/json"), *extra], b"{}")
                self.assertEqual(status, 404)

    def test_native_non_ingest_writes_require_session_token(self):
        for method in ("POST", "PATCH", "DELETE"):
            for token in (None, "wrong", "é"):
                headers = [("Host", self.authority), ("Content-Type", "application/json")]
                if token is not None:
                    headers.append(("X-NajdiLab-CSRF", token))
                status, body, _ = self.request(method, "/api/v1/no-such-route", headers, b"{}")
                self.assertEqual(status, 403)
                self.assertEqual(json.loads(body).get("code"), "CSRF_TOKEN_INVALID")

    def test_rejects_non_ascii_browser_token(self):
        status, _, _ = self.request("POST", "/api/v1/no-such-route", [("Host", self.authority), ("Origin", self.origin), ("Content-Type", "application/json"), ("X-NajdiLab-CSRF", "é")], b"{}")
        self.assertEqual(status, 403)

    def test_rejects_missing_simple_and_duplicate_content_type(self):
        for content_types in ([], ["text/plain"], ["application/x-www-form-urlencoded"], ["application/json", "text/plain"]):
            status, _, _ = self.request("POST", "/api/v1/no-such-route", [("Host", self.authority), *[("Content-Type", value) for value in content_types]], b"{}")
            self.assertEqual(status, 415)

    def test_rejects_duplicate_csrf_headers(self):
        token = self.session_token()
        status, _, _ = self.request("POST", "/api/v1/no-such-route", [("Host", self.authority), ("Origin", self.origin), ("Content-Type", "application/json"), ("X-NajdiLab-CSRF", token), ("X-NajdiLab-CSRF", token)], b"{}")
        self.assertEqual(status, 403)

    def test_rejects_ambiguous_body_framing(self):
        token = self.session_token()
        for extra in ([('Content-Length', '2')], [('Transfer-Encoding', 'chunked')]):
            status, _, _ = self.request("POST", "/api/v1/no-such-route", [("Host", self.authority), ("Content-Type", "application/json"), ("X-NajdiLab-CSRF", token), *extra], b"{}")
            self.assertEqual(status, 400)

    def ingest(self, path="/api/v1/turn", extra=(), body=b"{}"):
        return self.request("POST", path, [("Host", self.authority), ("Content-Type", "application/json"), *extra], body)

    def test_ingest_is_closed_without_secret(self):
        with patch.dict(os.environ, {"NAJDILAB_INGEST_TOKEN": "", "NAJDILAB_ALLOW_LEGACY_INGEST": "0"}), patch.object(server, "ingest_turn", return_value={"accepted": True}) as ingest:
            status, _, _ = self.ingest()
            self.assertEqual(status, 503)
            ingest.assert_not_called()

    def test_ingest_requires_valid_single_bearer_or_signature(self):
        with patch.dict(os.environ, {"NAJDILAB_INGEST_TOKEN": "synthetic-test-secret", "NAJDILAB_ALLOW_LEGACY_INGEST": "0"}), patch.object(server, "ingest_turn", return_value={"accepted": True}) as ingest:
            for extra in ([], [("Authorization", "Bearer wrong")], [("Authorization", "Basic synthetic-test-secret")], [("Authorization", "Bearer synthetic-test-secret"), ("Authorization", "Bearer synthetic-test-secret")], [("X-Hermes-Signature-256", "sha256=wrong")]):
                with self.subTest(extra=extra):
                    status, _, _ = self.ingest(extra=extra)
                    self.assertEqual(status, 401)
            ingest.assert_not_called()
            status, _, _ = self.ingest(extra=[("Authorization", "Bearer synthetic-test-secret")])
            self.assertEqual(status, 201)
            ingest.assert_called_once_with({})

    def test_signed_hermes_and_tampered_body_both_fail_closed(self):
        secret = "synthetic-test-secret"
        body = b'{"synthetic":true}'
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"NAJDILAB_INGEST_TOKEN": secret, "NAJDILAB_ALLOW_LEGACY_INGEST": "0"}), patch.object(server, "ingest_hermes_hook", return_value={"accepted": True}) as ingest:
            status, _, _ = self.ingest("/api/v1/hermes-hook", [("X-Hermes-Signature-256", signature)], body)
            self.assertEqual(status, 409)
            ingest.assert_not_called()
            for extra, candidate in (([("X-Hermes-Signature-256", signature)], b'{"synthetic":false}'), ([("X-Hermes-Signature-256", signature), ("X-Hermes-Signature-256", signature)], body)):
                status, _, _ = self.ingest("/api/v1/hermes-hook", extra, candidate)
                self.assertEqual(status, 409)
            ingest.assert_not_called()

    def test_legacy_ingest_requires_explicit_opt_in_and_does_not_bypass_browser_csrf(self):
        with patch.dict(os.environ, {"NAJDILAB_INGEST_TOKEN": "", "NAJDILAB_ALLOW_LEGACY_INGEST": "1"}), patch.object(server, "ingest_turn", return_value={"accepted": True}):
            status, _, _ = self.ingest()
            self.assertEqual(status, 201)
            status, _, _ = self.ingest(extra=[("Origin", self.origin)])
            self.assertEqual(status, 403)

    def test_static_traversal_cannot_read_files_outside_static_root(self):
        for path in ("/../app/server.py", "/..%2fapp/server.py", "/%2e%2e/app/server.py"):
            status, body, _ = self.request(path=path, headers=[("Host", self.authority)])
            self.assertNotIn(b"class NajdiLabHandler", body)
            self.assertIn(status, (200, 403))


if __name__ == "__main__":
    unittest.main()
