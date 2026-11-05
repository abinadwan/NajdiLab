"""A synthetic GitHub release for the managed runtime tests and the browser fixture. No network.

github.com answers the pinned release URL with a redirect to the asset host, like the real download;
the archives are small synthetic zips built here, never real llama.cpp binaries.
"""
from __future__ import annotations

import hashlib
import io
import zipfile

from app import managed_runtime
from app.hf_hub import Response
from app.runtime_catalog import RELEASE_URL

SERVER_ZIP = {'llama-server.exe': b'MZ synthetic server', 'ggml-base.dll': b'synthetic library' * 100,
              'LICENSE-LLVM-OpenMP': b'license text'}


def make_zip(members: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in members.items():
            if isinstance(data, zipfile.ZipInfo):
                archive.writestr(data, b'target')
            else:
                archive.writestr(name, data)
    return buffer.getvalue()


def package(blobs: dict, pid='windows-x64-cpu', system='Windows', backend='CPU', label='Synthetic'):
    assets = tuple({'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'url': RELEASE_URL + name}
                   for name, data in blobs.items())
    return {'id': pid, 'system': system, 'backend': backend, 'label': label, 'assets': assets}


class FakeGitHub:
    def __init__(self, blobs):
        self.blobs, self.calls, self.redirect_host = dict(blobs), [], 'release-assets.githubusercontent.com'
        self.on_read = None
        self.ranges, self.drop_after, self.honour_range = [], None, True  # resume tests

    def __call__(self, url, headers, timeout):
        managed_runtime.checked_url(url)
        self.calls.append(url)
        name = url.rsplit('/', 1)[-1].split('?')[0]
        if url.startswith(RELEASE_URL):
            return Response(302, {'location': f'https://{self.redirect_host}/github-production-release-asset/{name}?sig=x'}, io.BytesIO(), lambda: None)
        data = self.blobs[name]
        start = int(headers['Range'].split('=')[1].rstrip('-')) if 'Range' in headers else 0
        self.ranges.append(start)
        status, extra = 200, {}
        if start and self.honour_range:
            status, extra, data = 206, {'content-range': f'bytes {start}-{len(data) - 1}/{len(data)}'}, data[start:]
        body = io.BytesIO(data)
        if self.drop_after is not None:
            limit, self.drop_after, served = self.drop_after, None, [0]
            plain = body.read

            def dropping(n):
                if served[0] >= limit:
                    raise OSError('connection reset (fixture)')
                block = plain(min(n, limit - served[0]))
                served[0] += len(block)
                return block
            body.read = dropping
        if self.on_read:
            read, hook = body.read, self.on_read
            body.read = lambda n: (hook(), read(n))[1]
        return Response(status, {'content-length': str(len(data)), **extra}, body, lambda: None)
