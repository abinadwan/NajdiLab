"""A synthetic Hugging Face for tests and the browser fixture. No network, no real model.

It answers the three documented endpoints NajdiLab uses (search, pinned details with LFS blobs,
resolve → CDN redirect with Range support) for invented repositories whose GGUF files are tiny
random-weight models from tests/ollama_disposable.py. Failure modes are switches on the object.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, quote, unquote, urlsplit

from app.hf_hub import Response
from ollama_disposable import write_gguf

COMMIT_A = 'a' * 40
COMMIT_B = 'b' * 40


def _entry(repo, params, score, downloads, likes, updated, *, base=None, relation='quantized', license='apache-2.0',
           chat=True, gated=False):
    return {'id': repo, 'params': params, 'trendingScore': score, 'downloads': downloads, 'likes': likes,
            'lastModified': f'2026-{updated}T00:00:00.000Z', 'base': base, 'relation': relation, 'license': license,
            'chat': chat, 'gated': gated}


# Invented repositories for the Trending / Recommended tests: official, community, modified, unknown,
# misleading, mixture-of-experts, over-12B and base (non-chat) models. Order on purpose differs per sort.
CATALOG = [
    _entry('community-quant/Najm-3B-Instruct-GGUF', 3_090_000_000, 400, 9000, 40, '10-20', base='najdi-labs/Najm-3B-Instruct'),
    _entry('remix-lab/Najm-3B-Uncensored-GGUF', 3_090_000_000, 350, 800, 90, '10-29', base='najdi-labs/Najm-3B-Instruct'),
    _entry('najdi-labs/Najm-3B-Instruct-GGUF', 3_090_000_000, 300, 5000, 60, '10-25', base='najdi-labs/Najm-3B-Instruct'),
    _entry('najdi-labs/Najm-MoE-30B-A3B-GGUF', 30_500_000_000, 280, 4000, 70, '10-27', base='najdi-labs/Najm-MoE-30B-A3B'),
    _entry('mystery/Model-GGUF', None, 260, 300, 5, '10-30'),
    _entry('najdi-labs/Najm-0.5B-Chat-GGUF', 494_000_000, 250, 7000, 30, '10-21', base='najdi-labs/Najm-0.5B-Chat'),
    _entry('liar-org/Big-70B-Instruct-GGUF', 7_000_000_000, 240, 100, 2, '10-31', base='liar-org/Big-70B-Instruct'),
    _entry('najdi-labs/Najm-7B-Base-GGUF', 7_200_000_000, 200, 3000, 20, '10-22', base='najdi-labs/Najm-7B-Base', chat=False),
    _entry('tuner/Najm-3B-Instruct-DPO-GGUF', 3_090_000_000, 190, 200, 3, '10-28', base='najdi-labs/Najm-3B-Instruct', relation='finetune'),
    _entry('najdi-labs/Najm-12B-Instruct-GGUF', 12_200_000_000, 180, 2500, 25, '10-23', base='najdi-labs/Najm-12B-Instruct'),
    _entry('najdi-labs/Najm-11B-Instruct-GGUF', 11_500_000_000, 170, 2000, 15, '10-24', base='najdi-labs/Najm-11B-Instruct',
           license='llama3.1'),
    _entry('partner-ai/Partner-4B-Instruct-GGUF', 4_020_000_000, 160, 1500, 12, '10-26', base='partner-ai/Partner-4B-Instruct'),
]
# What each base model declares about its own origin (the lineage NajdiLab checks before saying "official").
LINEAGE = {base: [('finetune', base.rsplit('-', 1)[0] + '-Base')] for base in
           {e['base'] for e in CATALOG if e['base'] and e['base'].startswith('najdi-labs/')} - {'najdi-labs/Najm-7B-Base'}}
LINEAGE['partner-ai/Partner-4B-Instruct'] = [('finetune', 'najdi-labs/Najm-3B-Instruct')]  # derived from another account
LINEAGE['liar-org/Big-70B-Instruct'] = []


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
        self.list_queries = []
        self.catalog_extra = []
        self.nominal = {}  # sha256 -> published size, for files served with the synthetic GGUF bytes
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
        for entry in CATALOG:
            name = entry['id'].split('/')[1].removesuffix('-GGUF')
            files = {}
            for quant, ratio in (('Q4_K_M', .6), ('Q8_0', 1.07)):
                size = int((entry['params'] or 1_000_000_000) * ratio)
                sha = hashlib.sha256(f"{entry['id']}/{quant}".encode()).hexdigest()
                files[f'{name}-{quant}.gguf'] = (size, sha)
                self.nominal[sha] = size
            self.repos[entry['id']] = {'sha': COMMIT_A, 'gated': entry['gated'], 'license': entry['license'],
                                       'downloads': entry['downloads'], 'likes': entry['likes'],
                                       'gguf': {'total': entry['params'], 'architecture': 'llama'} if entry['params'] else {},
                                       'files': files}

    # ---- transport ------------------------------------------------------
    def __call__(self, method, url, headers, timeout):
        parts = urlsplit(url)
        self.calls.append((method, parts.hostname, parts.path, headers.get('Range')))
        assert 'authorization' not in {k.lower() for k in headers}, 'no credentials may be sent'
        if self.rate_limited:
            return self._reply(429, {'ratelimit': '"api";r=0;t=42'}, b'{}')
        if parts.hostname == 'huggingface.co' and parts.path == '/api/models' and 'expand[]' in parse_qs(parts.query):
            return self._list(parse_qs(parts.query))
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

    def _list(self, query):
        """Hugging Face's list API: sorted descending by the requested field, cursor pages, Link header."""
        self.list_queries.append(query)
        key = {'trendingScore': 'trendingScore', 'downloads': 'downloads', 'likes': 'likes', 'lastModified': 'lastModified'}[query['sort'][0]]
        ordered = sorted(CATALOG, key=lambda e: e[key], reverse=True)
        start = int(base64.urlsafe_b64decode(query['cursor'][0]).decode()) if 'cursor' in query else 0
        limit = int(query['limit'][0])
        rows = []
        for entry in ordered[start:start + limit]:
            tags = ['gguf', 'text-generation', f"license:{entry['license']}"] + (['conversational'] if entry['chat'] else [])
            card = {'license': entry['license']}
            if entry['base']:
                tags += [f"base_model:{entry['base']}", f"base_model:{entry['relation']}:{entry['base']}"]
                card['base_model'] = entry['base']
            files = self.repos[entry['id']]['files']
            rows.append({'id': entry['id'], 'trendingScore': entry['trendingScore'], 'downloads': entry['downloads'],
                         'likes': entry['likes'], 'lastModified': entry['lastModified'], 'gated': entry['gated'], 'tags': tags,
                         'cardData': card, 'gguf': {'total': entry['params'], 'architecture': 'llama'} if entry['params'] else {},
                         'siblings': [{'rfilename': n} for n in files] + [{'rfilename': 'README.md'}]})
        if start == 0:
            rows += self.catalog_extra
        headers = {'content-type': 'application/json'}
        if start + limit < len(ordered):
            following = base64.urlsafe_b64encode(str(start + limit).encode()).decode()
            headers['link'] = f'<https://huggingface.co/api/models?sort={key}&cursor={quote(following)}>; rel="next"'
        return self._reply(200, headers, json.dumps(rows).encode())

    def _details(self, path):
        match = re.fullmatch(r'([^/]+/[^/]+?)(?:/revision/([0-9a-f]{40}))?', path)
        if match and match.group(1) not in self.repos and (match.group(1) in LINEAGE or match.group(1).endswith('-Base')):
            relations = LINEAGE.get(match.group(1), [])
            return self._json({'id': match.group(1), 'tags': [f'base_model:{r}:{b}' for r, b in relations] + [f'base_model:{b}' for _, b in relations]})
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
            total = self.nominal.get(path.rsplit('/', 1)[-1], len(data))
            return self._reply(206, {'content-range': f'bytes {start}-{end}/{total}'}, data[start:end + 1],
                               None if self.fail_after is None else max(self.fail_after - start, 0))
        return self._reply(200, {}, data, self.fail_after)
