"""A synthetic Hugging Face for tests and the browser fixture. No network, no real model.

It answers the three documented endpoints NajdiLab uses (search, pinned details with LFS blobs,
resolve → CDN redirect with Range support) for invented repositories whose GGUF files are tiny
random-weight models from tests/ollama_disposable.py. Failure modes are switches on the object.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit

from app.hf_hub import Response
from ollama_disposable import write_gguf

COMMIT_A = 'a' * 40
COMMIT_B = 'b' * 40


def synthetic_gguf() -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'synthetic.gguf'
        write_gguf(path)
        return path.read_bytes()


class _Body(io.BytesIO):
    def __init__(self, data, fail_after=None):
        super().__init__(data)
        self.fail_after = fail_after

    def read(self, n=-1):
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise OSError('connection reset (synthetic)')
        return super().read(n)


class FakeHub:
    def __init__(self):
        self.gguf = synthetic_gguf()
        digest = hashlib.sha256(self.gguf).hexdigest()
        self.calls = []
        self.rate_limited = False
        self.redirect_host = 'cas-bridge.xethub.hf.co'
        self.fail_after = None
        self.serve_bytes = None  # override the bytes served (corruption tests)
        self.repos = {
            'najdi-synthetic/Tiny-Chat-GGUF': {
                'sha': COMMIT_A, 'gated': False, 'license': 'apache-2.0', 'downloads': 1200, 'likes': 7,
                'gguf': {'total': 1_000_000, 'architecture': 'llama', 'context_length': 2048},
                'files': {
                    'Tiny-Chat-Q4_K_M.gguf': (len(self.gguf), digest),
                    'Tiny-Chat-Q8_0-00001-of-00002.gguf': (4096, 'c' * 64),
                    'mmproj-Tiny-Chat-f16.gguf': (4096, 'd' * 64),
                    'README.md': (100, None),
                }},
            'najdi-synthetic/Wrong-Digest-GGUF': {
                'sha': COMMIT_B, 'gated': False, 'license': 'mit', 'downloads': 3, 'likes': 0,
                'gguf': {}, 'files': {'Wrong-Q4_K_M.gguf': (len(self.gguf), 'e' * 64)}},
            'gated-org/Locked-GGUF': {
                'sha': COMMIT_A, 'gated': 'manual', 'license': 'other', 'downloads': 50, 'likes': 1,
                'gguf': {}, 'files': {'Locked-Q4_K_M.gguf': (len(self.gguf), digest)}},
        }

    # ---- transport ------------------------------------------------------
    def __call__(self, method, url, headers, timeout):
        parts = urlsplit(url)
        self.calls.append((method, parts.hostname, parts.path, headers.get('Range')))
        assert 'authorization' not in {k.lower() for k in headers}, 'no credentials may be sent'
        if self.rate_limited:
            return self._reply(429, {'ratelimit': '"api";r=0;t=42'}, b'{}')
        if parts.hostname == 'huggingface.co' and parts.path == '/api/models':
            return self._search(parse_qs(parts.query))
        if parts.hostname == 'huggingface.co' and parts.path.startswith('/api/models/'):
            return self._details(unquote(parts.path[len('/api/models/'):]))
        if parts.hostname == 'huggingface.co' and '/resolve/' in parts.path:
            return self._resolve(unquote(parts.path), headers)
        if parts.hostname == self.redirect_host:
            return self._cdn(parts.path, headers)
        return self._reply(404, {}, b'')

    @staticmethod
    def _reply(status, headers, body, fail_after=None):
        return Response(status, {k.lower(): v for k, v in headers.items()}, _Body(body, fail_after), lambda: None)

    def _json(self, value, status=200):
        return self._reply(status, {'content-type': 'application/json'}, json.dumps(value).encode())

    def _search(self, query):
        term = (query.get('search') or [''])[0].lower()
        author = (query.get('author') or [''])[0]
        rows = [{'id': repo, 'downloads': r['downloads'], 'likes': r['likes'], 'private': False,
                 'tags': ['gguf', f"license:{r['license']}", 'text-generation'], 'pipeline_tag': 'text-generation',
                 'createdAt': '2026-10-01T00:00:00.000Z'}
                for repo, r in self.repos.items()
                if (not term or term in repo.lower()) and (not author or repo.split('/')[0] == author)]
        rows.append({'id': '../../etc/passwd', 'tags': []})  # hostile entry: must be dropped
        return self._json(rows)

    def _details(self, path):
        match = re.fullmatch(r'([^/]+/[^/]+?)(?:/revision/([0-9a-f]{40}))?', path)
        repo = self.repos.get(match.group(1)) if match else None
        if repo is None or (match.group(2) and match.group(2) != repo['sha']):
            return self._reply(401, {}, b'{"error":"Repository not found"}')
        siblings = []
        for name, (size, sha) in repo['files'].items():
            entry = {'rfilename': name, 'size': size}
            if sha:
                entry['lfs'] = {'sha256': sha, 'size': size, 'pointerSize': 134}
            siblings.append(entry)
        return self._json({'id': match.group(1), 'sha': repo['sha'], 'gated': repo['gated'], 'private': False, 'disabled': False,
                           'cardData': {'license': repo['license']}, 'tags': ['gguf', f"license:{repo['license']}"],
                           'gguf': repo['gguf'], 'pipeline_tag': 'text-generation', 'lastModified': '2026-10-02T00:00:00.000Z',
                           'siblings': siblings})

    def _resolve(self, path, headers):
        match = re.fullmatch(r'/([^/]+/[^/]+)/resolve/([0-9a-f]{40})/(.+)', path)
        repo = self.repos.get(match.group(1)) if match else None
        if repo is None or repo['gated'] or match.group(2) != repo['sha'] or match.group(3) not in repo['files']:
            return self._reply(401, {}, b'')
        size, sha = repo['files'][match.group(3)]
        return self._reply(302, {'location': f'https://{self.redirect_host}/blob/{sha}', 'x-repo-commit': repo['sha'],
                                 'x-linked-size': str(size), 'x-linked-etag': f'"{sha}"'}, b'')

    def _cdn(self, path, headers):
        data = self.serve_bytes if self.serve_bytes is not None else self.gguf
        start, end = 0, len(data) - 1
        if headers.get('Range'):
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', headers['Range'])
            start = int(match.group(1))
            end = min(int(match.group(2)), len(data) - 1) if match.group(2) else len(data) - 1
            if start >= len(data):
                return self._reply(416, {}, b'')
            return self._reply(206, {'content-range': f'bytes {start}-{end}/{len(data)}'}, data[start:end + 1],
                               None if self.fail_after is None else max(self.fail_after - start, 0))
        return self._reply(200, {}, data, self.fail_after)
