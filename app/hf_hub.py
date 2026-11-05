"""Hugging Face Direct: a narrow, read-only client for public GGUF model repositories.

Boundaries (docs/development/HUGGING_FACE_DIRECT.md):
- Documented endpoints only: `/api/models` (search), `/api/models/{repo}[/revision/{sha}]?blobs=true`
  (pinned details with LFS sizes and SHA-256) and `/{repo}/resolve/{sha}/{file}` (download).
- HTTPS only. Every request and every redirect hop must target huggingface.co, *.huggingface.co
  or *.hf.co on port 443; at most three redirects; no user-supplied URL is ever fetched.
- No credentials, cookies, proxies-from-config or tokens are sent. Gated and private repositories
  are reported as not accessible; nothing is bypassed.
- Repository content is untrusted: identifiers, names and file names are validated by strict
  patterns and length caps, JSON bodies are size-capped, and only `.gguf` files are ever fetched.
  No repository code is downloaded or executed.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import re
import ssl
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from .gguf import GGUFError, describe, read_header_bytes
from .version import APP_VERSION

API_HOST = 'huggingface.co'
USER_AGENT = f'NajdiLab/{APP_VERSION} (local; Hugging Face Direct)'
MAX_JSON = 4 * 1024 * 1024
MAX_REDIRECTS = 3
HEADER_STEPS = (1024 * 1024, 8 * 1024 * 1024, 32 * 1024 * 1024)
TIMEOUT = 20
REPO_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z')
AUTHOR = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
GGUF_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,250}\.gguf\Z')
# Training checkpoints (V2.2.0): top-level config, tokenizer and Safetensors files only, never code or pickles.
TRAINING_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,250}\.(?:json|safetensors|model|txt|jinja|tiktoken)\Z')
SPLIT = re.compile(r'-\d{5}-of-\d{5}\.gguf\Z', re.IGNORECASE)
QUANT = re.compile(r'(?<![A-Za-z0-9])((?:I?Q[1-8](?:_[0-9A-Z]{1,4}){0,3})|F16|BF16|F32|MXFP4(?:_MOE)?|TQ[12]_0)(?![A-Za-z0-9])',
                   re.IGNORECASE)
GATED = {False: 'OPEN', 'auto': 'GATED_AUTO', 'manual': 'GATED_MANUAL'}


class HubError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.status, self.retry_after = code, status, retry_after


def allowed_host(host: str | None) -> bool:
    host = (host or '').lower().rstrip('.')
    return host == API_HOST or host.endswith('.huggingface.co') or host.endswith('.hf.co')


def checked_url(url: str) -> str:
    """Only HTTPS to an allowed host on the default port, with no credentials."""
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not allowed_host(parts.hostname) or parts.username or parts.password
            or parts.port not in (None, 443)):
        raise HubError('HUB_URL_REFUSED', 'A response pointed to a location outside Hugging Face; nothing was fetched.')
    return url


@dataclass
class Response:
    status: int
    headers: dict
    body: object  # file-like with read(n)
    close: object


def https_transport(method: str, url: str, headers: dict, timeout: float) -> Response:
    """One request, no automatic redirects, certificate verification on."""
    parts = urlsplit(checked_url(url))
    connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=timeout,
                                             context=ssl.create_default_context())
    target = parts.path + (f'?{parts.query}' if parts.query else '')
    try:
        connection.request(method, target, headers=headers)
        reply = connection.getresponse()
    except (OSError, http.client.HTTPException):
        connection.close()
        raise HubError('HUB_UNREACHABLE', 'Hugging Face could not be reached. Check the internet connection.') from None
    return Response(reply.status, {k.lower(): v for k, v in reply.getheaders()}, reply, connection.close)


def _text(value, limit=200):
    return value[:limit] if isinstance(value, str) else None


def _int(value):
    return value if type(value) is int and value >= 0 else None


def license_of(card: dict | None, tags) -> str | None:
    value = (card or {}).get('license') if isinstance(card, dict) else None
    if isinstance(value, list):
        value = value[0] if value and isinstance(value[0], str) else None
    if not isinstance(value, str):
        value = next((t[8:] for t in tags or [] if isinstance(t, str) and t.startswith('license:')), None)
    return _text(value, 100)


def quantization(filename: str) -> str | None:
    found = QUANT.findall(filename.rsplit('/', 1)[-1])
    return found[-1].upper() if found else None


def variant(sibling: dict) -> dict | None:
    """One GGUF file of a repository, with the reasons it is or is not supported."""
    name = sibling.get('rfilename') if isinstance(sibling, dict) else None
    if not isinstance(name, str) or not name.lower().endswith('.gguf') or len(name) > 400:
        return None
    lfs = sibling.get('lfs') if isinstance(sibling.get('lfs'), dict) else {}
    size = _int(lfs.get('size')) or _int(sibling.get('size'))
    digest = lfs.get('sha256') if isinstance(lfs.get('sha256'), str) and SHA256.fullmatch(lfs['sha256']) else None
    reasons = []
    if '/' in name:
        reasons.append('IN_SUBFOLDER')
    elif not GGUF_NAME.fullmatch(name):
        reasons.append('UNSAFE_FILE_NAME')
    if SPLIT.search(name):
        reasons.append('SPLIT_UNSUPPORTED')
    if 'mmproj' in name.lower():
        reasons.append('PROJECTOR_NOT_A_TEXT_MODEL')
    if not size:
        reasons.append('SIZE_UNKNOWN')
    if not digest:
        reasons.append('DIGEST_UNKNOWN')
    return {'filename': name, 'size_bytes': size, 'sha256': digest, 'quantization': quantization(name),
            'supported': not reasons, 'unsupported_reasons': reasons}


LIST_SORTS = ('trendingScore', 'downloads', 'likes', 'lastModified')
LIST_FIELDS = ('trendingScore', 'downloads', 'likes', 'lastModified', 'gguf', 'cardData', 'tags', 'siblings', 'gated')
CURSOR = re.compile(r'[A-Za-z0-9+/=_-]{1,4096}\Z')
RELATIONS = ('quantized', 'finetune', 'merge', 'adapter')


def next_cursor(link: str) -> str | None:
    """The `cursor` of the rel="next" page in a Link header, if it points back to the same API."""
    match = re.search(r'<([^>]{1,8192})>;\s*rel="next"', link or '')
    if not match:
        return None
    parts = urlsplit(match.group(1))
    if parts.scheme != 'https' or parts.hostname != API_HOST or parts.path != '/api/models':
        return None
    value = parse_qs(parts.query).get('cursor', [None])[0]
    return value if isinstance(value, str) and CURSOR.fullmatch(value) else None


def listing(row) -> dict | None:
    """One list entry, reduced to validated facts. Everything else from the list is ignored."""
    repo = row.get('id') if isinstance(row, dict) else None
    if not isinstance(repo, str) or not REPO_ID.fullmatch(repo):
        return None
    tags = [t for t in row.get('tags') or [] if isinstance(t, str)][:128] if isinstance(row.get('tags'), list) else []
    card = row.get('cardData') if isinstance(row.get('cardData'), dict) else {}
    gguf = row.get('gguf') if isinstance(row.get('gguf'), dict) else {}
    relations = []
    for tag in tags:
        parts = tag.split(':')
        if parts[0] == 'base_model' and len(parts) == 3 and parts[1] in RELATIONS and REPO_ID.fullmatch(parts[2]):
            relations.append((parts[1], parts[2]))
    declared = {b for _, b in relations}
    relations += [('', t[11:]) for t in tags if t.startswith('base_model:') and t.count(':') == 1
                  and REPO_ID.fullmatch(t[11:]) and t[11:] not in declared]
    siblings = row.get('siblings') if isinstance(row.get('siblings'), list) else []
    files = [s['rfilename'] for s in siblings[:2000] if isinstance(s, dict) and isinstance(s.get('rfilename'), str)
             and GGUF_NAME.fullmatch(s['rfilename']) and not SPLIT.search(s['rfilename']) and 'mmproj' not in s['rfilename'].lower()]
    gated = row.get('gated')
    score = row.get('trendingScore')
    return {'id': repo, 'author': repo.split('/')[0], 'name': repo.split('/')[1],
            'trending_score': score if type(score) in (int, float) and score >= 0 else None,
            'downloads': _int(row.get('downloads')), 'likes': _int(row.get('likes')),
            'last_modified': _text(row.get('lastModified'), 40), 'license': license_of(card, tags),
            'access': GATED.get(gated, 'UNKNOWN') if gated in GATED else 'UNKNOWN',
            'parameters': _int(gguf.get('total')) or None, 'architecture': _text(gguf.get('architecture'), 60),
            'context_length': _int(gguf.get('context_length')), 'tags': [t for t in tags if t == 'conversational'],
            'base_models': relations[:8], 'gguf_files': files[:200]}


class HubClient:
    def __init__(self, transport=https_transport):
        self.transport = transport
        self._headers_cache = {}

    # ----- plumbing ------------------------------------------------------
    def _request(self, method, url, headers=None, timeout=TIMEOUT):
        sent = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity', **(headers or {})}
        for _ in range(MAX_REDIRECTS + 1):
            response = self.transport(method, checked_url(url), sent, timeout)
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get('location')
                response.close()
                if not location:
                    raise HubError('INVALID_RESPONSE', 'Hugging Face sent a redirect without a target.')
                if location.startswith('/'):
                    location = f'https://{urlsplit(url).hostname}{location}'
                url = location
                continue
            return response
        raise HubError('HUB_URL_REFUSED', 'Too many redirects; nothing was fetched.')

    def _json(self, path, params=None):
        return self._json_with_headers(path, params)[0]

    def _json_with_headers(self, path, params=None):
        url = f'https://{API_HOST}{path}' + (f'?{urlencode(params, doseq=True)}' if params else '')
        response = self._request('GET', url, {'Accept': 'application/json'})
        try:
            self._raise_for(response)
            body = response.body.read(MAX_JSON + 1)
        finally:
            response.close()
        if len(body) > MAX_JSON:
            raise HubError('INVALID_RESPONSE', 'Hugging Face sent an unexpectedly large response; it was discarded.')
        try:
            return json.loads(body.decode('utf-8')), response.headers
        except (UnicodeDecodeError, ValueError):
            raise HubError('INVALID_RESPONSE', 'Hugging Face sent a response NajdiLab cannot read.') from None

    @staticmethod
    def _raise_for(response):
        status = response.status
        if status in (200, 206):
            return
        if status == 429:
            match = re.search(r't=(\d+)', response.headers.get('ratelimit', ''))
            wait = int(match.group(1)) if match else None
            raise HubError('RATE_LIMITED', 'Hugging Face is limiting requests right now. Try again in a minute.', 429, wait)
        if status in (401, 403, 404):
            raise HubError('NOT_ACCESSIBLE', 'This repository or file does not exist, is private, or needs an account and license approval on Hugging Face.', 404)
        if status == 416:
            raise HubError('RANGE_REFUSED', 'Hugging Face refused to resume from this point.', 409)
        raise HubError('HUB_UNAVAILABLE', f'Hugging Face answered with HTTP {status}. Try again later.')

    # ----- discovery -----------------------------------------------------
    def search(self, query='', author='', limit=20):
        query = query.strip() if isinstance(query, str) else ''
        author = author.strip() if isinstance(author, str) else ''
        if len(query) > 100 or (author and not AUTHOR.fullmatch(author)):
            raise HubError('INVALID_SEARCH', 'Use up to 100 characters, and a publisher name made of letters, digits, dot, dash or underscore.', 400)
        if not query and not author:
            raise HubError('INVALID_SEARCH', 'Enter a model name or a publisher.', 400)
        params = {'filter': 'gguf', 'limit': max(1, min(int(limit), 50)), 'sort': 'downloads', 'direction': '-1'}
        if query:
            params['search'] = query
        if author:
            params['author'] = author
        rows = self._json('/api/models', params)
        if not isinstance(rows, list):
            raise HubError('INVALID_RESPONSE', 'Hugging Face sent search results NajdiLab cannot read.')
        items = []
        for row in rows[:50]:
            repo = row.get('id') if isinstance(row, dict) else None
            if not isinstance(repo, str) or not REPO_ID.fullmatch(repo):
                continue  # malformed or hostile entries are skipped, never shown
            tags = [t for t in row.get('tags') or [] if isinstance(t, str)][:64]
            items.append({'id': repo, 'author': repo.split('/')[0], 'name': repo.split('/')[1],
                          'downloads': _int(row.get('downloads')), 'likes': _int(row.get('likes')),
                          'license': license_of(None, tags), 'pipeline_tag': _text(row.get('pipeline_tag'), 60),
                          'last_modified': _text(row.get('lastModified') or row.get('createdAt'), 40),
                          'private': row.get('private') is True, 'gguf': 'gguf' in tags})
        return {'items': items, 'source': 'huggingface.co /api/models', 'format_filter': 'gguf'}

    def list_models(self, sort, cursor=None, limit=50):
        """One page of GGUF text-generation repositories in Hugging Face's own order for `sort`
        (trendingScore, downloads, likes or lastModified), and the cursor of the next page."""
        if sort not in LIST_SORTS:
            raise HubError('INVALID_SEARCH', 'Unknown ranking.', 400)
        if cursor is not None and not (isinstance(cursor, str) and CURSOR.fullmatch(cursor)):
            raise HubError('INVALID_CURSOR', 'The page marker is not valid; start the list again.', 400)
        params = [('filter', 'gguf'), ('pipeline_tag', 'text-generation'), ('sort', sort), ('direction', '-1'),
                  ('limit', max(1, min(int(limit), 100)))] + [('expand[]', field) for field in LIST_FIELDS]
        if cursor:
            params.append(('cursor', cursor))
        rows, headers = self._json_with_headers('/api/models', params)
        if not isinstance(rows, list):
            raise HubError('INVALID_RESPONSE', 'Hugging Face sent a model list NajdiLab cannot read.')
        return [item for item in (listing(row) for row in rows[:100]) if item], next_cursor(headers.get('link', ''))

    def relations(self, repo_id):
        """The base models a repository declares, with their relation (quantized, finetune, merge, adapter)."""
        if not isinstance(repo_id, str) or not REPO_ID.fullmatch(repo_id):
            raise HubError('INVALID_REPOSITORY', 'Use a repository id such as publisher/model-name.', 400)
        data = self._json(f'/api/models/{quote(repo_id)}', [('expand[]', 'tags')])
        if not isinstance(data, dict) or data.get('id') != repo_id:
            raise HubError('INVALID_RESPONSE', 'Hugging Face returned details for a different repository.')
        return listing(data)['base_models']

    def model(self, repo_id, revision=None):
        if not isinstance(repo_id, str) or not REPO_ID.fullmatch(repo_id):
            raise HubError('INVALID_REPOSITORY', 'Use a repository id such as publisher/model-name.', 400)
        if revision is not None and (not isinstance(revision, str) or not COMMIT.fullmatch(revision)):
            raise HubError('INVALID_REVISION', 'A revision must be a full 40-character commit id.', 400)
        path = f'/api/models/{quote(repo_id)}' + (f'/revision/{revision}' if revision else '')
        data = self._json(path, {'blobs': 'true'})
        if not isinstance(data, dict) or data.get('id') != repo_id:
            raise HubError('INVALID_RESPONSE', 'Hugging Face returned details for a different repository.')
        commit = data.get('sha')
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            raise HubError('INVALID_RESPONSE', 'Hugging Face did not report an immutable revision for this repository.')
        if revision and commit != revision:
            raise HubError('REVISION_CHANGED', 'The repository no longer matches the reviewed revision. Review it again before downloading.', 409)
        tags = [t for t in data.get('tags') or [] if isinstance(t, str)][:128]
        card = data.get('cardData') if isinstance(data.get('cardData'), dict) else {}
        gated = data.get('gated') if data.get('gated') in GATED else 'UNKNOWN'
        reported = data.get('gguf') if isinstance(data.get('gguf'), dict) else {}
        variants = [v for v in (variant(s) for s in (data.get('siblings') or [])[:2000]) if v]
        return {
            'id': repo_id, 'author': repo_id.split('/')[0], 'name': repo_id.split('/')[1], 'revision': commit,
            'access': GATED.get(gated, 'UNKNOWN') if gated != 'UNKNOWN' else 'UNKNOWN',
            'private': data.get('private') is True, 'disabled': data.get('disabled') is True,
            'license': license_of(card, tags), 'license_name': _text(card.get('license_name'), 100),
            'license_link': _text(card.get('license_link'), 300), 'pipeline_tag': _text(data.get('pipeline_tag'), 60),
            'last_modified': _text(data.get('lastModified'), 40),
            'base_models': [t[11:] for t in tags if t.startswith('base_model:') and not t.startswith('base_model:quantized:')
                            and REPO_ID.fullmatch(t[11:])][:5],
            # Reported by Hugging Face's own GGUF parser; shown as "reported", never as measured.
            'reported': {'parameters': _int(reported.get('total')), 'architecture': _text(reported.get('architecture'), 60),
                         'context_length': _int(reported.get('context_length'))},
            'variants': sorted(variants, key=lambda v: (not v['supported'], v['size_bytes'] or 0)),
            'formats': 'GGUF only; other formats are not supported by NajdiLab yet.',
        }

    def files(self, repo_id, revision=None):
        """Every file of a repository at one immutable revision, with size and the hash Hugging Face publishes
        (LFS SHA-256, or the git blob id for small files). Used for training checkpoints, which span many files."""
        if not isinstance(repo_id, str) or not REPO_ID.fullmatch(repo_id):
            raise HubError('INVALID_REPOSITORY', 'Use a repository id such as publisher/model-name.', 400)
        if revision is not None and (not isinstance(revision, str) or not COMMIT.fullmatch(revision)):
            raise HubError('INVALID_REVISION', 'A revision must be a full 40-character commit id.', 400)
        data = self._json(f'/api/models/{quote(repo_id)}' + (f'/revision/{revision}' if revision else ''), {'blobs': 'true'})
        if not isinstance(data, dict) or data.get('id') != repo_id or not COMMIT.fullmatch(str(data.get('sha') or '')):
            raise HubError('INVALID_RESPONSE', 'Hugging Face did not report an immutable revision for this repository.')
        if revision and data['sha'] != revision:
            raise HubError('REVISION_CHANGED', 'The repository no longer matches the reviewed revision. Review it again before downloading.', 409)
        tags = [t for t in data.get('tags') or [] if isinstance(t, str)][:128]
        card = data.get('cardData') if isinstance(data.get('cardData'), dict) else {}
        gated = data.get('gated') if data.get('gated') in GATED else 'UNKNOWN'
        rows = []
        for sibling in (data.get('siblings') or [])[:5000]:
            name, lfs = sibling.get('rfilename'), sibling.get('lfs') if isinstance(sibling.get('lfs'), dict) else {}
            if not isinstance(name, str):
                continue
            sha256 = lfs.get('sha256') if isinstance(lfs.get('sha256'), str) and SHA256.fullmatch(lfs['sha256']) else None
            blob = sibling.get('blobId') if isinstance(sibling.get('blobId'), str) and re.fullmatch(r'[0-9a-f]{40}', sibling['blobId']) else None
            rows.append({'name': name, 'size_bytes': _int(lfs.get('size') if lfs else sibling.get('size')), 'sha256': sha256, 'git_blob': blob})
        return {'id': repo_id, 'revision': data['sha'], 'access': GATED.get(gated, 'UNKNOWN') if gated != 'UNKNOWN' else 'UNKNOWN',
                'private': data.get('private') is True, 'disabled': data.get('disabled') is True,
                'license': license_of(card, tags), 'license_name': _text(card.get('license_name'), 100),
                'license_link': _text(card.get('license_link'), 300), 'tags': tags,
                'base_models': [t[11:] for t in tags if t.startswith('base_model:') and REPO_ID.fullmatch(t[11:])][:5],
                'files': rows}

    # ----- files ---------------------------------------------------------
    def _resolve_url(self, repo_id, revision, filename, names=GGUF_NAME):
        if not REPO_ID.fullmatch(repo_id or '') or not COMMIT.fullmatch(revision or '') or not names.fullmatch(filename or ''):
            raise HubError('INVALID_FILE', 'Only a supported top-level file at a pinned revision can be fetched.', 400)
        return f'https://{API_HOST}/{quote(repo_id)}/resolve/{revision}/{quote(filename)}'

    def open_file(self, repo_id, revision, filename, *, start=0, end=None, expected_size=None, expected_sha256=None, names=GGUF_NAME):
        """A pinned GGUF file stream (optionally a byte range). The first hop's headers must agree
        with the reviewed metadata: commit, size and SHA-256."""
        url = self._resolve_url(repo_id, revision, filename, names)
        sent = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
        if start or end is not None:
            sent['Range'] = f'bytes={start}-' + ('' if end is None else str(end))
        first = self.transport('GET', checked_url(url), sent, TIMEOUT)
        commit = first.headers.get('x-repo-commit')
        linked_size = first.headers.get('x-linked-size')
        linked_etag = (first.headers.get('x-linked-etag') or '').strip('"').lower()
        if commit and commit != revision:
            first.close()
            raise HubError('REVISION_CHANGED', 'Hugging Face served a different revision than the one reviewed.', 409)
        if expected_size is not None and linked_size is not None and linked_size != str(expected_size):
            first.close()
            raise HubError('SIZE_MISMATCH', 'Hugging Face reports a different file size than the reviewed metadata.', 409)
        if expected_sha256 and linked_etag and SHA256.fullmatch(linked_etag) and linked_etag != expected_sha256:
            first.close()
            raise HubError('DIGEST_MISMATCH', 'Hugging Face reports a different SHA-256 than the reviewed metadata.', 409)
        response = first
        hops = 0
        while response.status in (301, 302, 303, 307, 308):
            location = response.headers.get('location')
            response.close()
            hops += 1
            if not location or hops > MAX_REDIRECTS:
                raise HubError('HUB_URL_REFUSED', 'The download redirect was missing or too long; nothing was fetched.')
            if location.startswith('/'):
                location = f'https://{API_HOST}{location}'
            response = self.transport('GET', checked_url(location), sent, TIMEOUT)
        try:
            self._raise_for(response)
        except HubError:
            response.close()
            raise
        if start and response.status != 206:
            response.close()
            raise HubError('RANGE_REFUSED', 'The server did not resume from the saved point.', 409)
        if 'Range' in sent:
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)', response.headers.get('content-range', ''))
            if response.status == 206 and (not match or int(match.group(1)) != start
                                           or (expected_size is not None and match.group(3) not in ('*', str(expected_size)))):
                response.close()
                raise HubError('RANGE_MISMATCH', 'The server returned a different part of the file than requested.', 409)
        return response

    def remote_header(self, repo_id, revision, filename, expected_size=None, expected_sha256=None):
        """GGUF metadata from the first bytes of the file (bounded Range reads), before any download."""
        key = (repo_id, revision, filename)
        if key in self._headers_cache:
            return self._headers_cache[key]
        error = 'TRUNCATED'
        for step in HEADER_STEPS:
            end = step - 1 if expected_size is None else min(step, expected_size) - 1
            response = self.open_file(repo_id, revision, filename, start=0, end=end,
                                      expected_size=expected_size, expected_sha256=expected_sha256)
            try:
                data = response.body.read(step + 1)
            finally:
                response.close()
            if len(data) > step:
                raise HubError('INVALID_RESPONSE', 'Hugging Face sent more bytes than requested.')
            try:
                info = describe(read_header_bytes(data))
            except GGUFError as failure:
                error = failure.code
                if error == 'TRUNCATED' and len(data) == step and (expected_size is None or step < expected_size):
                    continue
                break
            info['source'] = 'remote_header'
            self._headers_cache[key] = info
            return info
        return {'source': 'remote_header', 'error': error}
