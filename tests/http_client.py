"""Real session bootstrap for disposable feature-integration HTTP tests."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen as raw_urlopen


def urlopen(request, *args, **kwargs):
    if isinstance(request, Request) and request.get_method() in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        url = urlsplit(request.full_url)
        if url.hostname not in {'127.0.0.1', 'localhost'} or url.port == 8770:
            raise AssertionError('Feature HTTP tests must use a disposable loopback port')
        with raw_urlopen(f'{url.scheme}://{url.netloc}/api/v1/session', timeout=5) as response:
            token = json.load(response)['csrf_token']
        request.add_header('X-NajdiLab-CSRF', token)
    return raw_urlopen(request, *args, **kwargs)
