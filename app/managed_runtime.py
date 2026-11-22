"""Managed llama.cpp runtime: install, verify, switch, roll back and remove NajdiLab's own llama-server.

Boundaries (docs/development/MANAGED_RUNTIME.md):
- Only the pinned build in app/runtime_catalog.py, only after an explicit approval naming the package.
  Archives come from the official GitHub release over HTTPS (github.com, then GitHub's asset hosts
  only, at most three redirects) or from the owner's offline `archives/` folder, and must match the
  pinned size and SHA-256 before anything is extracted.
- Extraction is into a fresh staging folder and refuses absolute paths, `..`, odd names, devices,
  hard links and symlinks that leave the folder. Disk space is checked before the download, before
  extraction and during the transfer, with the same reserve as model downloads.
- A build becomes active only after it proves its identity (`--version`: pinned build and commit),
  lists a device of its backend, and computes on that device with a tiny model NajdiLab generates.
  Activation is an atomic replace of `active.json`; the previous install is kept for rollback.
- Nothing changes while NajdiLab Native is running. Every process started here is NajdiLab's own
  child on 127.0.0.1 and is stopped through its handle only.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import shutil
import ssl
import stat
import subprocess
import tarfile
import threading
import time
from urllib.parse import urljoin, urlsplit
import zipfile

from . import runtime_catalog as catalog
from .db import DATA_DIR, utc_now
from .hf_hub import Response
from .integrations import Connector, IntegrationError, request_json
from .model_store import GIB, _gib_env, volume_of
from .native_runtime import default_server_path, free_port, list_devices, sha256_file
from .synthetic_gguf import write_gguf
from .version import APP_VERSION

GITHUB_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
USER_AGENT = f'NajdiLab/{APP_VERSION} (local; managed llama.cpp runtime)'
MAX_REDIRECTS = 3
DOWNLOAD_ATTEMPTS = 3  # one download plus two automatic resumes after a dropped connection
MANIFEST = 'najdilab-runtime.json'
EXPANSION = 4  # unpacked-size bound used before the archive is available
MAX_UNPACKED = 8 * GIB
MAX_MEMBERS = 4000
CHUNK = 1024 * 1024
CHECK_EVERY = 32 * 1024 * 1024
PROBE_TIMEOUT = 120
PART = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z')
OFFLOADED = re.compile(rb'offloaded (\d+)/(\d+) layers to GPU')
PROBE_FAILURES = (
    (re.compile(rb'no kernel image is available', re.I), 'RUNTIME_GPU_ARCHITECTURE_UNSUPPORTED',
     'This build has no GPU code for this GPU\'s architecture. Choose another package.'),
    (re.compile(rb'out of memory|failed to allocate|ErrorOutOfDeviceMemory', re.I), 'RUNTIME_GPU_OUT_OF_MEMORY',
     'The GPU did not have room even for the tiny test model. Close other GPU programs and try again.'),
    (re.compile(rb'CUDA error|ggml_cuda_init: failed|ErrorDeviceLost|ErrorInitializationFailed', re.I), 'RUNTIME_GPU_FAILED',
     'The GPU could not run this build. Choose another package, or update the GPU driver.'),
)


def github_transport(url: str, headers: dict, timeout: float) -> Response:
    """One GET, certificate verification on, no automatic redirects."""
    parts = urlsplit(checked_url(url))
    connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request('GET', parts.path + (f'?{parts.query}' if parts.query else ''), headers=headers)
        reply = connection.getresponse()
    except (OSError, http.client.HTTPException):
        connection.close()
        raise IntegrationError('RUNTIME_DOWNLOAD_UNREACHABLE', 'GitHub could not be reached. Check the internet connection.', 502) from None
    return Response(reply.status, {k.lower(): v for k, v in reply.getheaders()}, reply, connection.close)


def checked_url(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != 'https' or (parts.hostname or '').lower() not in GITHUB_HOSTS or parts.username
            or parts.password or parts.port not in (None, 443)):
        raise IntegrationError('RUNTIME_URL_REFUSED', 'A download pointed outside GitHub\'s release hosts; nothing was fetched.', 502)
    return url


def member_path(name: str, strip: str | None) -> PurePosixPath | None:
    """Safe relative path for an archive member, or None for the stripped top folder itself."""
    if not isinstance(name, str) or len(name) > 512 or '\\' in name or ':' in name or name.startswith('/'):
        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive contains an unsafe file name; nothing was installed.', 409)
    parts = [p for p in name.split('/') if p != '']
    if strip:
        if not parts or parts[0] != strip:
            raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive layout is not the expected one; nothing was installed.', 409)
        parts = parts[1:]
    if not parts:
        return None
    if len(parts) > 6 or not all(PART.match(p) and p not in ('.', '..') for p in parts):
        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive contains an unsafe file name; nothing was installed.', 409)
    return PurePosixPath(*parts)


def _top_folder(names):
    """The single folder every member sits in (Linux archives), or None (flat Windows archives)."""
    top = names[0].split('/', 1)[0] if names else ''
    inside = [n for n in names if n.startswith(top + '/')]
    if top and inside and all(n == top or n.startswith(top + '/') for n in names):
        return top
    return None


def _walk(root: Path):
    """Every file and link under `root`; linked folders are listed, never entered."""
    for folder, dirs, files in os.walk(root):
        links = [d for d in dirs if os.path.islink(os.path.join(folder, d))]
        dirs[:] = [d for d in dirs if d not in links]
        for name in files + links:
            yield Path(folder, name)


def file_list(root: Path, *, hashes: bool) -> list:
    rows = []
    for path in sorted(_walk(root)):
        rel = path.relative_to(root).as_posix()
        if rel == MANIFEST:
            continue
        if path.is_symlink():
            rows.append({'path': rel, 'link': os.readlink(path)})
            continue
        value = path.stat()
        row = {'path': rel, 'size': value.st_size, 'mtime_ns': value.st_mtime_ns}
        if hashes:
            row['sha256'] = sha256_file(path)
        rows.append(row)
    return rows


class _Job:
    def __init__(self, package, reason):
        self.package, self.reason = package, reason
        self.phase, self.asset, self.done, self.total = 'PREPARING', None, 0, sum(a['size'] for a in package['assets'])
        self.cancel = threading.Event()
        self.started_at = utc_now()

    def public(self):
        return {'package': self.package['id'], 'reason': self.reason, 'phase': self.phase, 'asset': self.asset,
                'downloaded_bytes': self.done, 'download_total_bytes': self.total, 'started_at': self.started_at,
                'cancelling': self.cancel.is_set()}


class ManagedRuntime:
    def __init__(self, native, root=None, *, transport=github_transport, disk_usage=shutil.disk_usage,
                 reserve_bytes=None, system_reserve_bytes=None, detect=catalog.detect_host, packages=None,
                 verifier=None, chunk=CHUNK, check_every=CHECK_EVERY, system=None, machine=None):
        self.native = native
        self.root = Path(root) if root else DATA_DIR / 'native' / 'runtime'
        self.transport, self.disk_usage, self.detect_host = transport, disk_usage, detect
        self.reserve = _gib_env('NAJDILAB_DOWNLOAD_RESERVE_GIB', 2) if reserve_bytes is None else reserve_bytes
        self.system_reserve = _gib_env('NAJDILAB_SYSTEM_RESERVE_GIB', 10) if system_reserve_bytes is None else system_reserve_bytes
        self.packages = tuple(packages or catalog.PACKAGES)
        self.verifier = verifier or self.verify_build
        self.chunk, self.check_every = chunk, check_every
        self.retry_delay = 1.0
        self.system = system or platform.system()
        self.machine = machine or platform.machine()
        self._lock = threading.RLock()
        self._job = None
        self.host = None
        self.last_error = None
        self.last_result = None

    # ----- paths and records -------------------------------------------------
    @property
    def installs(self):
        return self.root / 'installs'

    @property
    def archives(self):
        return self.root / 'archives'

    def _pointer(self):
        try:
            value = json.loads((self.root / 'active.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'active': None, 'previous': None}
        names = {k: value.get(k) if isinstance(value.get(k), str) and PART.match(value.get(k)) else None
                 for k in ('active', 'previous')}
        return names

    def _write_pointer(self, active, previous):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / f'.active-{secrets.token_hex(4)}.json'
        temporary.write_text(json.dumps({'active': active, 'previous': previous, 'updated_at': utc_now()}), encoding='utf-8')
        os.replace(temporary, self.root / 'active.json')

    def _manifest(self, name):
        if not name:
            return None
        try:
            value = json.loads((self.installs / name / MANIFEST).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) and value.get('schema') == 1 else None

    def _server(self, name, manifest):
        return self.installs / name / manifest['server']

    def active_server(self):
        pointer = self._pointer()
        manifest = self._manifest(pointer['active'])
        return self._server(pointer['active'], manifest) if manifest else None

    def attach(self):
        """At startup: Native uses the active managed build unless the owner set NAJDILAB_NATIVE_SERVER."""
        if not os.environ.get('NAJDILAB_NATIVE_SERVER'):
            self.native.use_server(self.active_server() or default_server_path())

    # ----- verification -------------------------------------------------------
    def check(self, name, *, full=False):
        """Problems with an install; empty when every file is exactly as recorded at install time."""
        manifest = self._manifest(name)
        if manifest is None:
            return ['MANIFEST_MISSING']
        folder = self.installs / name
        try:
            current = {r['path']: r for r in file_list(folder, hashes=False)}
        except OSError:
            return ['UNREADABLE']
        problems = []
        recorded = {r['path']: r for r in manifest['files']}
        if set(current) != set(recorded):
            problems.append('FILES_ADDED_OR_REMOVED')
        for path, row in recorded.items():
            now = current.get(path)
            if now is None:
                continue
            if 'link' in row:
                if now.get('link') != row['link']:
                    problems.append(f'CHANGED:{path}')
            elif (now.get('size'), now.get('mtime_ns')) != (row['size'], row['mtime_ns']):
                problems.append(f'CHANGED:{path}')
            elif (full or path == manifest['server']) and sha256_file(folder / path) != row['sha256']:
                problems.append(f'HASH:{path}')
        return problems

    def gate(self):
        """Before every Native start: a managed build must be exactly as installed."""
        if self._job is not None:
            raise IntegrationError('RUNTIME_BUSY', 'The runtime is being installed; start the model when it is ready.', 409)
        server = Path(self.native.server_path)
        try:
            server.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return  # the owner's own llama-server (NAJDILAB_NATIVE_SERVER) is not managed here
        pointer = self._pointer()
        manifest = self._manifest(pointer['active'])
        if manifest is None or self._server(pointer['active'], manifest).resolve() != server.resolve():
            raise IntegrationError('RUNTIME_NOT_VERIFIED', 'This llama-server is not the active managed runtime. Open Model library → llama.cpp runtime.', 409)
        if self.check(pointer['active']):
            raise IntegrationError('RUNTIME_NOT_VERIFIED', 'The managed runtime files changed since they were verified. Repair it in Model library → llama.cpp runtime.', 409)

    def verify(self, data):
        if data != {}:
            raise IntegrationError('INVALID_PAYLOAD', 'Verify takes no options.')
        pointer = self._pointer()
        if not self._manifest(pointer['active']):
            raise IntegrationError('RUNTIME_NOT_INSTALLED', 'No managed runtime is installed.', 409)
        problems = self.check(pointer['active'], full=True)
        self.last_result = {'action': 'VERIFY', 'at': utc_now(), 'ok': not problems, 'problems': problems[:20]}
        return self.status()

    def verify_build(self, server: Path, package: dict, workdir: Path) -> dict:
        """Identity, devices and a real computation on the package's device. Raises on any failure."""
        env = self.native._child_env()
        flags = {'capture_output': True, 'timeout': 30, 'env': env, 'cwd': str(server.parent),
                 'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        try:
            out = subprocess.run([str(server), '--version'], **flags)
        except (OSError, subprocess.SubprocessError):
            raise IntegrationError('RUNTIME_WONT_RUN', 'The installed llama-server could not be run on this computer.', 409) from None
        text = (out.stdout + out.stderr)[:16384].decode('utf-8', 'replace')
        match = re.search(r'build (\d+), commit ([0-9a-f]{7,40})', text)
        if not match or int(match[1]) != catalog.BUILD['build'] or not catalog.BUILD['commit'].startswith(match[2]):
            raise IntegrationError('RUNTIME_IDENTITY_MISMATCH', 'The installed program is not the pinned llama.cpp build.', 409)
        devices = list_devices(server, env)
        backend = package['backend']
        device = None
        if backend != 'CPU':
            device = next((d for d in devices if d['id'].lower().startswith(backend.lower())), None)
            if device is None:
                raise IntegrationError('RUNTIME_NO_DEVICE', f'This {backend} build does not see a {backend} device here. Choose another package.', 409)
        probe = self._probe(server, workdir, env, device)
        return {'version': {'build': int(match[1]), 'commit': match[2]}, 'devices': devices,
                'probe': probe, 'verified_at': utc_now()}

    def _probe(self, server, workdir, env, device):
        model = workdir / 'probe.gguf'
        write_gguf(model, eos=False)
        port, key = free_port(), secrets.token_urlsafe(24)
        command = [str(server), '-m', str(model), '--host', '127.0.0.1', '--port', str(port), '-c', '512', '-np', '1',
                   '--no-webui', '--offline', '--no-slots', '-ngl', 'all' if device else '0',
                   '-lv', '4']  # verbosity 4 prints the "offloaded N/N layers to GPU" evidence line
        if device:
            command += ['--device', device['id']]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   env={**env, 'LLAMA_API_KEY': key}, cwd=str(server.parent),
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
        log = bytearray()

        def drain():
            for line in iter(process.stderr.readline, b''):
                if len(log) < 512 * 1024:
                    log.extend(line)
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        connector = Connector('NajdiLab runtime probe', 'model_runtime', '', port, '/health', '/health', ('/completion',))
        headers = {'Authorization': f'Bearer {key}'}
        started = time.monotonic()
        try:
            reply = None
            while time.monotonic() - started < PROBE_TIMEOUT and process.poll() is None:
                try:
                    if request_json(connector, '/health', timeout=2, headers=headers).get('status') == 'ok':
                        reply = request_json(connector, '/completion', {'prompt': 'abc', 'n_predict': 4, 'temperature': 0},
                                             timeout=60, headers=headers)
                        break
                except IntegrationError:
                    if process.poll() is not None:
                        break
                    time.sleep(.25)
        finally:
            # Only the child started above is stopped, through its own handle.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(10)
            reader.join(5)
            model.unlink(missing_ok=True)
        output = bytes(log)
        if not isinstance(reply, dict) or not isinstance(reply.get('content'), str) or not reply.get('tokens_predicted'):
            for pattern, code, message in PROBE_FAILURES:
                if pattern.search(output):
                    raise IntegrationError(code, message, 409)
            raise IntegrationError('RUNTIME_PROBE_FAILED', 'The test computation with a tiny generated model did not succeed.', 409)
        offloaded = OFFLOADED.search(output)
        layers = f'{int(offloaded[1])}/{int(offloaded[2])}' if offloaded else None
        if device and (not offloaded or offloaded[1] != offloaded[2] or offloaded[1] == b'0'):
            raise IntegrationError('RUNTIME_GPU_NOT_USED', 'The test model did not run fully on the GPU, so this GPU build is not verified.', 409)
        return {'device': device['id'] if device else 'CPU', 'device_name': device['name'] if device else None,
                'layers_on_gpu': layers, 'tokens': reply['tokens_predicted'],
                'seconds': round(time.monotonic() - started, 2), 'model': 'synthetic random-weight GGUF (generated locally)'}

    # ----- status -----------------------------------------------------------
    def _summary(self, name):
        manifest = self._manifest(name)
        if not manifest:
            return None
        return {'id': name, 'package': manifest['package']['id'], 'label': manifest['package']['label'],
                'backend': manifest['package']['backend'], 'build': manifest['build']['tag'],
                'commit': manifest['build']['commit'], 'installed_at': manifest['installed_at'],
                'path': str(self.installs / name), 'server': str(self._server(name, manifest)),
                'files': len(manifest['files']), 'size_bytes': sum(r.get('size', 0) for r in manifest['files']),
                'verification': manifest['verification'], 'notices': f'{self.installs / name}/NOTICES'}

    def preflight(self, package, archive_bytes=None):
        volume = volume_of(self.root)
        usage = self.disk_usage(volume['measured_at'])
        reserve = max(self.reserve, self.system_reserve) if volume['system_volume'] else self.reserve
        download = sum(a['size'] for a in package['assets'] if not self._offline(a))
        unpack = archive_bytes if archive_bytes is not None else EXPANSION * sum(a['size'] for a in package['assets'])
        required = download + unpack + reserve
        reasons = []
        if usage.free < required:
            reasons.append({'code': 'INSUFFICIENT_SPACE', 'message': 'Not enough free space on this drive for the download, the unpacked files and the safety reserve.'})
        return {'decision': 'BLOCKED' if reasons else 'ALLOWED', 'reasons': reasons, 'destination': str(self.root),
                'volume': volume['label'], 'system_volume': volume['system_volume'], 'free_bytes': usage.free,
                'download_bytes': download, 'unpacked_bytes': unpack, 'unpacked_kind': 'exact' if archive_bytes is not None else 'upper bound',
                'reserve_bytes': reserve, 'required_bytes': required, 'free_after_bytes': usage.free - download - unpack}

    def _offline(self, asset):
        path = self.archives / asset['name']
        return path.is_file() and path.stat().st_size == asset['size']

    def _candidates(self):
        if self.host is None:
            return None
        rows = []
        for row in catalog.candidates(self.host):
            package = next((p for p in self.packages if p['id'] == row['package']['id']), None)
            if package is None:
                continue
            rows.append({'id': package['id'], 'label': package['label'], 'backend': package['backend'],
                         'eligible': not row['reasons'], 'reasons': row['reasons'],
                         'tested_on_real_hardware': package['id'] in catalog.TESTED,
                         'assets': [{**a, 'offline_copy': self._offline(a)} for a in package['assets']],
                         'download_bytes': sum(a['size'] for a in package['assets'] if not self._offline(a)),
                         'preflight': self.preflight(package)})
        recommended = next((r['id'] for r in rows if r['eligible']), None)
        for row in rows:
            row['recommended'] = row['id'] == recommended
        return rows

    def status(self):
        with self._lock:
            job = self._job.public() if self._job else None
        pointer = self._pointer()
        active, previous = self._summary(pointer['active']), self._summary(pointer['previous'])
        external = bool(os.environ.get('NAJDILAB_NATIVE_SERVER'))
        problems = self.check(pointer['active']) if active else []
        native_state, native_error, running_model, native_revision = self.native.brief()
        if job:
            state = 'INSTALLING'
        elif not catalog.supported(self.system, self.machine):
            state = 'BLOCKED'
        elif not active:
            state = 'ERROR' if self.last_error else 'NOT_INSTALLED'
        elif problems:
            state = 'UNVERIFIED'
        elif native_state in ('RUNNING', 'STARTING', 'STOPPING'):
            state = native_state
        elif native_state == 'FAILED':
            state = 'ERROR'
        elif native_revision:
            state = 'STOPPED'
        else:
            state = 'READY'
        return {'state': state, 'mode': 'EXTERNAL' if external else 'MANAGED',
                'native_server_path': str(self.native.server_path), 'native_state': native_state, 'native_error': native_error,
                'running_model': running_model, 'active': active, 'previous': previous, 'problems': problems[:20],
                'update_available': bool(active and active['build'] != catalog.BUILD['tag']),
                'job': job, 'last_error': self.last_error, 'last_result': self.last_result,
                'platform': {'system': self.system, 'machine': self.machine,
                             'supported': catalog.supported(self.system, self.machine)},
                'host': self.host, 'candidates': self._candidates(), 'build': catalog.BUILD,
                'listen': '127.0.0.1 only'}

    def detect(self, data):
        if data != {'approved': True}:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve reading this computer\'s GPU and driver details (read-only, stays on this computer).', 403)
        self.host = self.detect_host()
        return self.status()

    # ----- install --------------------------------------------------------------
    def _refuse_while_busy(self):
        if self._job is not None:
            raise IntegrationError('RUNTIME_BUSY', 'A runtime installation is already in progress.', 409)
        if self.native.busy():
            raise IntegrationError('RUNTIME_IN_USE', 'Stop the running model in NajdiLab Native first.', 409)

    def _package_for_install(self, data):
        if (not isinstance(data, dict) or set(data) != {'approved', 'package', 'license_acknowledged'}
                or data['approved'] is not True or data['license_acknowledged'] is not True):
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve the download and installation, and acknowledge the licenses.', 403)
        if self.host is None:
            raise IntegrationError('RUNTIME_HOST_NOT_CHECKED', 'Check this computer first, so the right package can be chosen.', 409)
        row = next((r for r in self._candidates() if r['id'] == data['package']), None)
        if row is None:
            raise IntegrationError('RUNTIME_PACKAGE_UNKNOWN', 'That package is not available for this computer.', 404)
        if not row['eligible']:
            raise IntegrationError(row['reasons'][0]['code'], row['reasons'][0]['message'], 409)
        if row['preflight']['decision'] != 'ALLOWED':
            raise IntegrationError('INSUFFICIENT_SPACE', row['preflight']['reasons'][0]['message'], 409)
        return next(p for p in self.packages if p['id'] == data['package'])

    def install(self, data, *, wait=False, progress=None):
        package = self._package_for_install(data)
        pointer = self._pointer()
        current = self._manifest(pointer['active'])
        reason = ('REPAIR' if current and current['package']['id'] == package['id'] and current['build']['tag'] == catalog.BUILD['tag']
                  else 'UPDATE' if current else 'INSTALL')
        with self._lock:
            self._refuse_while_busy()
            job = self._job = _Job(package, reason)
            self.last_error = None
        if wait:
            self._run(job, progress)
            if self.last_error:
                raise IntegrationError(self.last_error['code'], self.last_error['message'], 409)
        else:
            threading.Thread(target=self._run, args=(job, progress), daemon=True).start()
        return self.status()

    def cancel(self, data):
        if data != {}:
            raise IntegrationError('INVALID_PAYLOAD', 'Cancel takes no options.')
        with self._lock:
            if self._job is None:
                raise IntegrationError('RUNTIME_IDLE', 'No runtime installation is in progress.', 409)
            self._job.cancel.set()
        return self.status()

    def _run(self, job, progress=None):
        staging = self.installs / f'.staging-{secrets.token_hex(6)}'
        downloaded = []
        try:
            self.archives.mkdir(parents=True, exist_ok=True)
            archives = []
            for asset in job.package['assets']:
                path, fetched = self._fetch(asset, job, progress)
                archives.append(path)
                if fetched:
                    downloaded.append(path)
            job.phase = 'EXTRACTING'
            staging.mkdir(parents=True)
            self._extract_all(archives, staging, job)
            notices = staging / 'NOTICES'
            notices.mkdir(exist_ok=True)
            for name, text in catalog.notices(job.package).items():
                (notices / name).write_text(text, encoding='utf-8', newline='\n')
            server = staging / catalog.server_name(job.package['system'])
            if not server.is_file() or server.is_symlink():
                raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive did not contain llama-server; nothing was installed.', 409)
            if os.name != 'nt':
                server.chmod(0o755)
            job.phase = 'VERIFYING'
            if progress:
                progress('Verifying the build on this computer (identity, devices, a tiny test model)...')
            work = self.root / f'.probe-{secrets.token_hex(4)}'
            work.mkdir()
            try:
                evidence = self.verifier(server, job.package, work)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            name = f"{job.package['id']}-{catalog.BUILD['tag']}-{secrets.token_hex(3)}"
            # Hashed here, outside the lock; renaming the folder keeps sizes and modification times.
            files = file_list(staging, hashes=True)
            manifest = {'schema': 1, 'package': {k: job.package[k] for k in ('id', 'label', 'backend', 'system')},
                        'build': catalog.BUILD, 'assets': [dict(a) for a in job.package['assets']],
                        'server': server.name, 'installed_at': utc_now(), 'installed_by': f'NajdiLab {APP_VERSION}',
                        'reason': job.reason, 'verification': evidence, 'files': files}
            with self._lock:
                if job.cancel.is_set():
                    raise IntegrationError('RUNTIME_CANCELLED', 'Installation cancelled; nothing was changed.', 409)
                if self.native.busy():
                    raise IntegrationError('RUNTIME_IN_USE', 'NajdiLab Native started during the installation; nothing was changed.', 409)
                final = self.installs / name
                os.replace(staging, final)
                (final / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding='utf-8')
                pointer = self._pointer()
                self._write_pointer(name, pointer['active'] if pointer['active'] != name else pointer['previous'])
                self._prune()
                self.attach()
                self.last_result = {'action': job.reason, 'at': utc_now(), 'ok': True, 'install': name}
        except IntegrationError as error:
            self.last_error = {'code': error.code, 'message': str(error), 'package': job.package['id'], 'at': utc_now()}
        except OSError as error:
            code = 'DISK_FULL' if getattr(error, 'errno', None) == 28 or getattr(error, 'winerror', None) in (39, 112) else 'RUNTIME_INSTALL_FAILED'
            self.last_error = {'code': code, 'message': 'The installation could not write its files; nothing was changed.',
                               'package': job.package['id'], 'at': utc_now()}
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            for path in downloaded:
                path.unlink(missing_ok=True)  # only what this run downloaded; owner-supplied archives stay
            with self._lock:
                self._job = None

    def _fetch(self, asset, job, progress):
        """Return (path, downloaded_now). An owner-supplied copy in archives/ is used when it matches the pin."""
        final = self.archives / asset['name']
        job.asset = asset['name']
        if final.is_file():
            job.phase = 'CHECKING_OFFLINE_COPY'
            if final.stat().st_size != asset['size'] or sha256_file(final) != asset['sha256']:
                raise IntegrationError('RUNTIME_ARCHIVE_MISMATCH', f"{asset['name']} in the archives folder does not match the pinned SHA-256. Remove it; NajdiLab does not delete your files.", 409)
            job.done += asset['size']
            return final, False
        job.phase = 'DOWNLOADING'
        if progress:
            progress(f"Downloading {asset['name']} ({asset['size'] / 1024 ** 2:.1f} MiB)...")
        part = self.archives / (asset['name'] + '.part')
        # A network interruption keeps the verified-so-far `.part` file; later attempts (automatic, or the
        # next install) continue it with an HTTP Range request. The whole file is still hashed at the end.
        for attempt in range(DOWNLOAD_ATTEMPTS):
            try:
                return self._download(asset, job, part, final), True
            except IntegrationError as error:
                if error.code != 'RUNTIME_DOWNLOAD_UNREACHABLE' or job.cancel.is_set() or attempt == DOWNLOAD_ATTEMPTS - 1:
                    raise
                job.phase = 'RETRYING'
                if progress:
                    progress(f"Connection lost; resuming {asset['name']} (attempt {attempt + 2} of {DOWNLOAD_ATTEMPTS})...")
                time.sleep(self.retry_delay * (attempt + 1))
                job.phase = 'DOWNLOADING'

    def _download(self, asset, job, part, final):
        offset = part.stat().st_size if part.is_file() else 0
        if offset >= asset['size']:
            part.unlink(missing_ok=True)
            offset = 0
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/octet-stream', **({'Range': f'bytes={offset}-'} if offset else {})}
        url, response, keep = asset['url'], None, False
        try:
            for _ in range(MAX_REDIRECTS + 1):
                response = self.transport(url, headers, 30)
                if response.status in (301, 302, 303, 307, 308) and response.headers.get('location'):
                    response.close()
                    url, response = urljoin(url, response.headers['location']), None
                    continue
                break
            if response is None:
                raise IntegrationError('RUNTIME_DOWNLOAD_FAILED', 'Too many redirects; nothing was installed.', 502)
            if offset and response.status == 206:
                expected = f"bytes {offset}-{asset['size'] - 1}/{asset['size']}"
                if response.headers.get('content-range') != expected:
                    raise IntegrationError('RUNTIME_DIGEST_MISMATCH', 'The resumed download does not continue the pinned file; nothing was installed.', 409)
                remaining = asset['size'] - offset
            elif response.status == 200:
                offset, remaining = 0, asset['size']  # the server ignored the range: start over
            else:
                raise IntegrationError('RUNTIME_DOWNLOAD_FAILED', f'GitHub answered HTTP {response.status}; nothing was installed.', 502)
            length = response.headers.get('content-length')
            if length is not None and length != str(remaining):
                raise IntegrationError('RUNTIME_DIGEST_MISMATCH', 'The download size differs from the pinned size; nothing was installed.', 409)
            digest, count, since = hashlib.sha256(), offset, 0
            if offset:
                with part.open('rb') as done:
                    for block in iter(lambda: done.read(self.chunk), b''):
                        digest.update(block)
            job.done += offset
            volume = volume_of(self.root)
            reserve = max(self.reserve, self.system_reserve) if volume['system_volume'] else self.reserve
            with part.open('ab' if offset else 'wb') as target:
                while True:
                    if job.cancel.is_set():
                        raise IntegrationError('RUNTIME_CANCELLED', 'Installation cancelled; nothing was changed.', 409)
                    try:
                        block = response.body.read(self.chunk)
                    except (OSError, http.client.HTTPException):
                        keep = True
                        raise IntegrationError('RUNTIME_DOWNLOAD_UNREACHABLE', 'The download was interrupted; nothing was installed. Try again to resume it.', 502) from None
                    if not block:
                        break
                    count += len(block)
                    if count > asset['size']:
                        raise IntegrationError('RUNTIME_DIGEST_MISMATCH', 'The download is larger than the pinned size; nothing was installed.', 409)
                    digest.update(block)
                    target.write(block)
                    job.done += len(block)
                    since += len(block)
                    if since >= self.check_every:
                        since = 0
                        if self.disk_usage(volume['measured_at']).free < reserve + (asset['size'] - count):
                            raise IntegrationError('DISK_FULL', 'Free space fell below the safety reserve; the download stopped and nothing was installed.', 507)
            if count != asset['size'] or digest.hexdigest() != asset['sha256']:
                raise IntegrationError('RUNTIME_DIGEST_MISMATCH', f"{asset['name']} does not match the pinned SHA-256; nothing was installed.", 409)
            os.replace(part, final)
            return final
        except IntegrationError as error:
            if error.code == 'RUNTIME_DOWNLOAD_UNREACHABLE' and keep:
                job.done -= count  # counted again when the next attempt re-reads the partial file
            raise
        finally:
            if response is not None:
                response.close()
            if not keep:
                part.unlink(missing_ok=True)

    def _extract_all(self, archives, staging, job):
        plans = [self._plan(path) for path in archives]
        total = sum(size for plan in plans for _, _, size, _ in plan[1])
        if total > MAX_UNPACKED:
            raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archives unpack to more than the allowed size; nothing was installed.', 409)
        if self.preflight(job.package, total)['decision'] != 'ALLOWED':
            raise IntegrationError('INSUFFICIENT_SPACE', 'Not enough free space to unpack the runtime with the safety reserve; nothing was installed.', 409)
        links = []
        for (kind, members), path in zip(plans, archives):
            with (zipfile.ZipFile(path) if kind == 'zip' else tarfile.open(path, 'r:gz')) as archive:
                for member, rel, size, link in members:
                    if job.cancel.is_set():
                        raise IntegrationError('RUNTIME_CANCELLED', 'Installation cancelled; nothing was changed.', 409)
                    target = staging.joinpath(*rel.parts)
                    if link is not None:
                        links.append((target, link))
                        continue
                    if size is None:
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.open(member) if kind == 'zip' else archive.extractfile(member)
                    with source, target.open('xb') as out:
                        left = size
                        while block := source.read(min(CHUNK, left + 1)):
                            left -= len(block)
                            if left < 0:
                                raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'An archive member is larger than declared; nothing was installed.', 409)
                            out.write(block)
                    if left:
                        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'An archive member is truncated; nothing was installed.', 409)
                    if kind == 'tar' and os.name != 'nt':
                        target.chmod(0o755 if member.mode & 0o111 else 0o644)
        for target, link in links:
            # Linux library chains only: a sibling name that exists in the same folder.
            if not (target.parent / link).exists():
                raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'An archive link points outside its folder; nothing was installed.', 409)
            os.symlink(link, target)

    def _plan(self, path):
        """Validated member list (member, relative path, size or None for folders, link target) before writing."""
        rows = []
        if path.name.endswith('.zip'):
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_MEMBERS:
                    raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive has too many files; nothing was installed.', 409)
                strip = _top_folder([i.filename for i in infos])
                for info in infos:
                    file_type = stat.S_IFMT(info.external_attr >> 16)  # 0 when the archive was made on Windows
                    if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive contains links or special files; nothing was installed.', 409)
                    rel = member_path(info.filename, strip)
                    if rel is not None:
                        rows.append((info, rel, None if info.is_dir() else info.file_size, None))
            kind = 'zip'
        elif path.name.endswith('.tar.gz'):
            with tarfile.open(path, 'r:gz') as archive:
                members = []
                for member in archive:
                    members.append(member)
                    if len(members) > MAX_MEMBERS:
                        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive has too many files; nothing was installed.', 409)
                strip = _top_folder([m.name for m in members])
                for member in members:
                    rel = member_path(member.name, strip)
                    if rel is None:
                        continue
                    if member.isreg():
                        rows.append((member, rel, member.size, None))
                    elif member.isdir():
                        rows.append((member, rel, None, None))
                    elif member.issym() and PART.match(member.linkname) and member.linkname not in ('.', '..') and os.name != 'nt':
                        rows.append((member, rel, 0, member.linkname))
                    else:
                        raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive contains links or special files; nothing was installed.', 409)
            kind = 'tar'
        else:
            raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'Unknown archive type; nothing was installed.', 409)
        names = [r[1] for r in rows]
        if len(set(names)) != len(names):
            raise IntegrationError('RUNTIME_ARCHIVE_UNSAFE', 'The archive lists a file twice; nothing was installed.', 409)
        return kind, rows

    def _prune(self):
        """Keep only the active and previous installs (and never touch anything else in the root)."""
        pointer = self._pointer()
        keep = {pointer['active'], pointer['previous']}
        for folder in self.installs.iterdir() if self.installs.is_dir() else ():
            if folder.name not in keep and (folder / MANIFEST).is_file() and not folder.is_symlink():
                shutil.rmtree(folder, ignore_errors=True)

    # ----- rollback / uninstall ------------------------------------------------
    def rollback(self, data):
        if data != {'approved': True}:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve switching back to the previous runtime.', 403)
        with self._lock:
            self._refuse_while_busy()
            pointer = self._pointer()
            if not self._manifest(pointer['previous']):
                raise IntegrationError('RUNTIME_NO_PREVIOUS', 'There is no previous runtime to switch back to.', 409)
            if self.check(pointer['previous']):
                raise IntegrationError('RUNTIME_NOT_VERIFIED', 'The previous runtime\'s files changed since they were verified; it cannot be used.', 409)
            self._write_pointer(pointer['previous'], pointer['active'])
            self.attach()
            self.last_result = {'action': 'ROLLBACK', 'at': utc_now(), 'ok': True, 'install': pointer['previous']}
        return self.status()

    def uninstall(self, data):
        if data != {'approved': True, 'confirm': 'UNINSTALL'}:
            raise IntegrationError('APPROVAL_REQUIRED', 'Type UNINSTALL to confirm removing the managed runtime.', 403)
        with self._lock:
            self._refuse_while_busy()
            pointer = self._pointer()
            (self.root / 'active.json').unlink(missing_ok=True)
            removed = []
            for folder in self.installs.iterdir() if self.installs.is_dir() else ():
                if not folder.is_symlink() and ((folder / MANIFEST).is_file() or folder.name.startswith('.staging-')):
                    shutil.rmtree(folder)
                    removed.append(folder.name)
            self.attach()
            kept = sorted(p.name for p in self.archives.iterdir()) if self.archives.is_dir() else []
            self.last_result = {'action': 'UNINSTALL', 'at': utc_now(), 'ok': True, 'removed': removed,
                                'kept_archives': kept, 'was_active': pointer['active']}
        return self.status()

    def shutdown(self):
        with self._lock:
            if self._job is not None:
                self._job.cancel.set()

    def handle(self, action, data):
        handlers = {'detect': self.detect, 'install': self.install, 'cancel': self.cancel, 'verify': self.verify,
                    'rollback': self.rollback, 'uninstall': self.uninstall}
        if action not in handlers:
            raise IntegrationError('NOT_FOUND', 'Unknown runtime action.', 404)
        return handlers[action](data)
