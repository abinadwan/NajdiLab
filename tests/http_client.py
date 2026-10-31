"""Real session bootstrap for disposable feature-integration HTTP tests."""
import json
from http.client import HTTPConnection
from urllib.parse import urlsplit
from urllib.request import Request, urlopen as raw_urlopen


class SingleWriteHTTPConnection(HTTPConnection):
    """Send small fixture headers/body together; never retry or fake a response.

    An early security refusal may close before HTTPConnection's separate body
    write arrives. Windows can then reset instead of delivering the refusal.
    Headers-only fixtures still go immediately, preserving the no-body proof.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fixture_output = bytearray()

    def send(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise AssertionError("Disposable HTTP fixtures require bounded bytes")
        self._fixture_output.extend(data)

    def endheaders(self, message_body=None, *, encode_chunked=False):
        super().endheaders(message_body, encode_chunked=encode_chunked)
        try:
            super().send(self._fixture_output)
        finally:
            self._fixture_output.clear()


def urlopen(request, *args, **kwargs):
    if isinstance(request, Request) and request.get_method() in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        url = urlsplit(request.full_url)
        if url.hostname not in {'127.0.0.1', 'localhost'} or url.port == 8770:
            raise AssertionError('Feature HTTP tests must use a disposable loopback port')
        with raw_urlopen(f'{url.scheme}://{url.netloc}/api/v1/session', timeout=5) as response:
            token = json.load(response)['csrf_token']
        request.add_header('X-NajdiLab-CSRF', token)
    return raw_urlopen(request, *args, **kwargs)
