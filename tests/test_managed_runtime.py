"""Managed llama.cpp runtime: catalog, selection, verified download, safe extraction, switch, rollback,
uninstall and the Native start gate. Synthetic archives and a fake GitHub; no network, no real binary.
The opt-in test at the end runs the real verification against a llama.cpp b12059 llama-server."""
from __future__ import annotations

from collections import namedtuple
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from app import managed_runtime, runtime_catalog as catalog  # noqa: E402
from app.integrations import IntegrationError  # noqa: E402
from app.managed_runtime import MANIFEST, ManagedRuntime, member_path  # noqa: E402
from app.native_runtime import NativeRuntime  # noqa: E402
from fake_github import SERVER_ZIP, FakeGitHub, make_zip, package  # noqa: E402

Usage = namedtuple('Usage', 'total used free')
WINDOWS = {'system': 'Windows', 'machine': 'AMD64', 'nvidia': [], 'driver_version': None, 'driver_cuda': None,
           'vulkan_loader': False, 'warnings': []}
EVIDENCE = {'version': {'build': 12059, 'commit': '1b6935b22'}, 'devices': [], 'probe': {'device': 'CPU', 'tokens': 4}}


def code(call):
    with pytest.raises(IntegrationError) as caught:
        call()
    return caught.value.code


def nvidia(cc, driver_cuda, **extra):
    return {**WINDOWS, 'nvidia': [{'name': 'NVIDIA GeForce Test', 'compute_capability': cc, 'total_bytes': 12 * 1024 ** 3}],
            'driver_version': '600.00', 'driver_cuda': driver_cuda, 'vulkan_loader': True, **extra}


def recommended(host):
    return next(row['package']['id'] for row in catalog.candidates(host) if not row['reasons'])


def make_tar(members: dict) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif isinstance(data, tuple):
                info.type, info.linkname = tarfile.SYMTYPE, data[1]
                archive.addfile(info)
            else:
                info.size, info.mode = len(data), 0o755
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Disk:
    def __init__(self, free):
        self.free = free

    def __call__(self, path):
        return Usage(10 ** 12, 10 ** 12 - self.free, self.free)


class Verifier:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(self, server, pkg, workdir):
        self.calls.append((server, pkg['id']))
        assert server.is_file() and workdir.is_dir()
        if self.error:
            raise IntegrationError(*self.error)
        return EVIDENCE


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.delenv('NAJDILAB_NATIVE_SERVER', raising=False)
    return NativeRuntime(server_path=tmp_path / 'none' / 'llama-server.exe', models_dir=tmp_path / 'models')


def runtime(tmp_path, native, blobs=None, *, pkg=None, verifier=None, disk=None, host=WINDOWS, **extra):
    blobs = blobs or {'llama-b12059-bin-win-cpu-x64.zip': make_zip(SERVER_ZIP)}
    pkg = pkg or package(blobs)
    hub = FakeGitHub(blobs)
    managed = ManagedRuntime(native, tmp_path / 'runtime', transport=hub, disk_usage=disk or Disk(10 ** 11),
                             reserve_bytes=0, system_reserve_bytes=0, detect=lambda: dict(host), packages=[pkg],
                             verifier=verifier or Verifier(), system=host['system'], machine=host['machine'], **extra)
    return managed, hub, pkg


def approve(pkg):
    return {'approved': True, 'package': pkg['id'], 'license_acknowledged': True}


def installed(managed, pkg, **kwargs):
    managed.detect({'approved': True})
    managed.install(approve(pkg), wait=True, **kwargs)
    return managed.status()


# ----- catalog and selection ----------------------------------------------------
def test_catalog_is_pinned_to_one_official_build_with_a_digest_for_every_archive():
    assert re.fullmatch(r'[0-9a-f]{40}', catalog.BUILD['commit']) and catalog.BUILD['tag'] == f"b{catalog.BUILD['build']}"
    assert catalog.RELEASE_URL == f"https://github.com/ggml-org/llama.cpp/releases/download/{catalog.BUILD['tag']}/"
    ids = [p['id'] for p in catalog.PACKAGES]
    assert len(ids) == len(set(ids))
    for pkg in catalog.PACKAGES:
        for asset in pkg['assets']:
            assert asset['url'] == catalog.RELEASE_URL + asset['name'] and asset['size'] > 1024 * 1024
            assert re.fullmatch(r'[0-9a-f]{64}', asset['sha256'])
            assert catalog.BUILD['tag'] in asset['name'] or asset['name'].startswith('cudart-llama-bin-win-')
            assert asset['name'].endswith('.zip' if pkg['system'] == 'Windows' else '.tar.gz')
        if pkg['backend'] == 'CUDA':
            assert any(a['name'].startswith('cudart-') for a in pkg['assets']), 'CUDA packages carry their runtime libraries'
    assert catalog.TESTED <= set(ids)
    notes = catalog.notices(catalog.PACKAGES[0])
    assert 'MIT License' in notes['LICENSE-llama.cpp.txt'] and 'Niels Lohmann' in notes['LICENSE-jsonhpp.txt']
    assert 'NVIDIA CUDA Toolkit End User License Agreement' in notes['README.txt']


def test_blackwell_gets_cuda_13_and_never_a_toolkit_that_predates_it():
    host = nvidia((12, 0), (13, 5))
    assert recommended(host) == 'windows-x64-cuda-13.4'
    rows = {r['package']['id']: r['reasons'] for r in catalog.candidates(host)}
    assert [r['code'] for r in rows['windows-x64-cuda-12.4']] == ['GPU_ARCHITECTURE_UNSUPPORTED']
    assert rows['windows-x64-vulkan'] == [] and rows['windows-x64-cpu'] == []
    assert recommended({**host, 'system': 'Linux'}) == 'linux-x64-cuda-13.4'
    assert recommended({**nvidia((12, 0), (12, 9)), 'system': 'Linux'}) == 'linux-x64-cuda-12.8'


def test_old_driver_or_unknown_facts_fall_back_instead_of_guessing():
    old_driver = nvidia((12, 0), (12, 6))
    rows = {r['package']['id']: [x['code'] for x in r['reasons']] for r in catalog.candidates(old_driver)}
    assert rows['windows-x64-cuda-13.4'] == ['DRIVER_TOO_OLD']
    assert recommended(old_driver) == 'windows-x64-vulkan'
    assert recommended(nvidia((8, 6), (12, 4))) == 'windows-x64-cuda-12.4'
    unknown = nvidia(None, None)
    codes = {c for r in catalog.candidates(unknown) for c in (x['code'] for x in r['reasons'])}
    assert {'COMPUTE_CAPABILITY_UNKNOWN', 'DRIVER_CUDA_UNKNOWN'} <= codes
    assert recommended(unknown) == 'windows-x64-vulkan'
    assert recommended({**unknown, 'vulkan_loader': False}) == 'windows-x64-cpu'
    future = nvidia((13, 0), (14, 0))
    assert recommended(future) == 'windows-x64-vulkan', 'a GPU newer than the toolkit is not assumed to work'
    assert recommended(WINDOWS) == 'windows-x64-cpu'


def test_unsupported_systems_are_blocked_with_no_package():
    assert not catalog.supported('Darwin', 'arm64') and not catalog.supported('Windows', 'ARM64')
    assert catalog.supported('Windows', 'AMD64') and catalog.supported('Linux', 'x86_64')
    assert catalog.candidates({**WINDOWS, 'system': 'Darwin'}) == []
    assert all(r['reasons'][0]['code'] == 'UNSUPPORTED_PLATFORM' for r in catalog.candidates({**WINDOWS, 'machine': 'ARM64'}))


def test_detection_reads_capability_driver_and_cuda_version_only(monkeypatch, tmp_path):
    tool = tmp_path / 'nvidia-smi'
    tool.write_text('')
    monkeypatch.setattr(catalog, '_nvidia_smi', lambda: tool)
    calls = []

    def run(command, **kwargs):
        calls.append(command[1:])
        if len(command) > 1:
            return subprocess.CompletedProcess(command, 0, 'NVIDIA GeForce RTX 5070, 12.0, 621.01, 12227\n', '')
        return subprocess.CompletedProcess(command, 0, '| NVIDIA-SMI 621.01   KMD Version: 621.01   CUDA UMD Version: 13.5 |\n| 1234 C other.exe |', '')
    host = catalog.detect_host(run)
    assert host['nvidia'] == [{'name': 'NVIDIA GeForce RTX 5070', 'compute_capability': (12, 0), 'total_bytes': 12227 * 1024 ** 2}]
    assert host['driver_version'] == '621.01' and host['driver_cuda'] == (13, 5)
    assert 'other.exe' not in repr(host), 'other GPU programs are never recorded'
    assert calls[0] == ['--query-gpu=name,compute_cap,driver_version,memory.total', '--format=csv,noheader,nounits']
    linux = catalog.detect_host(lambda c, **k: subprocess.CompletedProcess(c, 0, 'A, 8.6, 550.1, 8000\n' if len(c) > 1 else 'CUDA Version: 12.4', ''))
    assert linux['driver_cuda'] == (12, 4) and linux['nvidia'][0]['compute_capability'] == (8, 6)
    broken = catalog.detect_host(lambda c, **k: subprocess.CompletedProcess(c, 0, 'garbage', ''))
    assert broken['warnings'] == ['NVIDIA_QUERY_FAILED']


# ----- install ------------------------------------------------------------------
def test_install_needs_hardware_check_approval_and_license_acknowledgement(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native)
    assert managed.status()['state'] == 'NOT_INSTALLED' and managed.status()['candidates'] is None
    assert code(lambda: managed.detect({})) == 'APPROVAL_REQUIRED'
    assert code(lambda: managed.install(approve(pkg))) == 'RUNTIME_HOST_NOT_CHECKED'
    managed.detect({'approved': True})
    for bad in ({**approve(pkg), 'license_acknowledged': False}, {'approved': True, 'package': pkg['id']},
                {**approve(pkg), 'approved': 'yes'}, {**approve(pkg), 'url': 'https://example.com'}):
        assert code(lambda: managed.install(bad)) == 'APPROVAL_REQUIRED'
    assert code(lambda: managed.install({**approve(pkg), 'package': 'windows-x64-cuda-13.4'})) == 'RUNTIME_PACKAGE_UNKNOWN'
    assert hub.calls == [], 'nothing is downloaded before approval'


def test_install_downloads_verifies_extracts_and_activates(tmp_path, native):
    verifier = Verifier()
    managed, hub, pkg = runtime(tmp_path, native, verifier=verifier)
    status = installed(managed, pkg)
    assert status['state'] == 'READY' and status['last_error'] is None and status['problems'] == []
    assert hub.calls[0] == pkg['assets'][0]['url'] and hub.calls[1].startswith('https://release-assets.githubusercontent.com/')
    active = status['active']
    folder = Path(active['path'])
    assert active['package'] == 'windows-x64-cpu' and active['build'] == catalog.BUILD['tag']
    assert (folder / 'llama-server.exe').read_bytes() == SERVER_ZIP['llama-server.exe']
    assert {p.name for p in (folder / 'NOTICES').iterdir()} == {'README.txt', 'LICENSE-llama.cpp.txt', 'LICENSE-jsonhpp.txt'}
    manifest = (folder / MANIFEST).read_text(encoding='utf-8')
    assert pkg['assets'][0]['sha256'] in manifest and hashlib.sha256(SERVER_ZIP['ggml-base.dll']).hexdigest() in manifest
    assert native.server_path == folder / 'llama-server.exe', 'Native uses the managed build'
    assert verifier.calls and verifier.calls[0][1] == 'windows-x64-cpu'
    assert list((tmp_path / 'runtime' / 'archives').iterdir()) == [], 'downloaded archives are removed after install'
    assert not any(p.name.startswith('.') for p in (tmp_path / 'runtime' / 'installs').iterdir())
    managed.gate()
    restarted = ManagedRuntime(NativeRuntime(server_path=tmp_path / 'x', models_dir=tmp_path), tmp_path / 'runtime')
    restarted.attach()
    assert restarted.native.server_path == folder / 'llama-server.exe', 'the active build survives a restart'


def test_a_changed_digest_size_or_redirect_installs_nothing(tmp_path, native):
    blobs = {'llama-b12059-bin-win-cpu-x64.zip': make_zip(SERVER_ZIP)}
    pkg = package(blobs)
    pkg['assets'][0]['sha256'] = '0' * 64
    managed, hub, _ = runtime(tmp_path, native, blobs, pkg=pkg)
    managed.detect({'approved': True})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_DIGEST_MISMATCH'
    status = managed.status()
    assert status['state'] == 'ERROR' and status['active'] is None and status['job'] is None
    assert list((tmp_path / 'runtime' / 'archives').iterdir()) == []
    assert not (tmp_path / 'runtime' / 'installs').exists() or list((tmp_path / 'runtime' / 'installs').iterdir()) == []

    managed, hub, pkg = runtime(tmp_path / 'b', native)
    hub.redirect_host = 'evil.example.com'
    managed.detect({'approved': True})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_URL_REFUSED'
    managed, hub, pkg = runtime(tmp_path / 'c', native)
    hub.blobs[pkg['assets'][0]['name']] += b'extra'
    managed.detect({'approved': True})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_DIGEST_MISMATCH'
    for url in ('http://github.com/x', 'https://github.com:8443/x', 'https://user:pw@github.com/x', 'https://example.com/x'):
        assert code(lambda: managed_runtime.checked_url(url)) == 'RUNTIME_URL_REFUSED'


@pytest.mark.parametrize('name', ['../evil.dll', '/abs/llama-server.exe', 'C:/x.dll', 'dir\\x.dll', 'a/../../x', 'bad name.dll', 'con:x'])
def test_member_names_that_could_escape_are_refused(name):
    assert code(lambda: member_path(name, None)) == 'RUNTIME_ARCHIVE_UNSAFE'


def test_unsafe_or_incomplete_archives_install_nothing(tmp_path, native):
    link = zipfile.ZipInfo('ggml-cuda.dll')
    link.external_attr = (0o120777 << 16)
    for index, members in enumerate(({**SERVER_ZIP, '../escape.dll': b'x'}, {**SERVER_ZIP, 'link.dll': link},
                                     {'ggml-base.dll': b'no server here'})):
        blobs = {'llama-b12059-bin-win-cpu-x64.zip': make_zip(members)}
        managed, _, pkg = runtime(tmp_path / str(index), native, blobs)
        managed.detect({'approved': True})
        assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_ARCHIVE_UNSAFE'
        assert managed.status()['active'] is None
        assert not (tmp_path / str(index) / 'escape.dll').exists()


def test_linux_archives_strip_their_top_folder(tmp_path, native):
    members = {'llama-b12059': None, 'llama-b12059/llama-server': b'\x7fELF synthetic', 'llama-b12059/libggml.so.0.28.0': b'lib',
               'llama-b12059/LICENSE': b'MIT'}
    if os.name != 'nt':
        members['llama-b12059/libggml.so.0'] = ('link', 'libggml.so.0.28.0')
    blobs = {'llama-b12059-bin-ubuntu-x64.tar.gz': make_tar(members)}
    host = {**WINDOWS, 'system': 'Linux', 'machine': 'x86_64'}
    managed, _, pkg = runtime(tmp_path, native, blobs, pkg=package(blobs, 'linux-x64-cpu', 'Linux'), host=host)
    status = installed(managed, pkg)
    folder = Path(status['active']['path'])
    assert (folder / 'llama-server').read_bytes() == b'\x7fELF synthetic' and (folder / 'LICENSE').is_file()
    if os.name != 'nt':
        assert os.readlink(folder / 'libggml.so.0') == 'libggml.so.0.28.0' and os.access(folder / 'llama-server', os.X_OK)
    escaping = {'llama-b12059/llama-server': b'x', 'llama-b12059/evil.so': ('link', '../../etc/passwd')}
    blobs = {'llama-b12059-bin-ubuntu-x64.tar.gz': make_tar(escaping)}
    managed, _, pkg = runtime(tmp_path / 'evil', native, blobs, pkg=package(blobs, 'linux-x64-cpu', 'Linux'), host=host)
    managed.detect({'approved': True})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_ARCHIVE_UNSAFE'


def test_low_disk_blocks_before_download_and_stops_during_it(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native, disk=Disk(1000))
    managed.detect({'approved': True})
    row = managed.status()['candidates'][0]
    assert row['preflight']['decision'] == 'BLOCKED' and row['preflight']['unpacked_kind'] == 'upper bound'
    assert code(lambda: managed.install(approve(pkg))) == 'INSUFFICIENT_SPACE' and hub.calls == []
    disk = Disk(10 ** 9)
    big = {'llama-b12059-bin-win-cpu-x64.zip': make_zip({**SERVER_ZIP, 'big.dll': os.urandom(300_000)})}
    managed, hub, pkg = runtime(tmp_path / 'b', native, big, disk=disk, chunk=4096, check_every=4096)
    managed.reserve = managed.system_reserve = 500_000_000
    managed.detect({'approved': True})
    hub.on_read = lambda: setattr(disk, 'free', 1000)
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'DISK_FULL'
    assert list((tmp_path / 'b' / 'runtime' / 'archives').iterdir()) == []


def test_cancel_stops_the_download_and_keeps_the_previous_build(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native, chunk=64)
    first = installed(managed, pkg)['active']['id']
    hub.on_read = lambda: managed.cancel({})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_CANCELLED'
    status = managed.status()
    assert status['active']['id'] == first and status['state'] == 'READY' and status['last_error']['code'] == 'RUNTIME_CANCELLED'
    assert code(lambda: managed.cancel({})) == 'RUNTIME_IDLE'


def test_failed_verification_never_replaces_a_working_build(tmp_path, native):
    verifier = Verifier()
    managed, _, pkg = runtime(tmp_path, native, verifier=verifier)
    first = installed(managed, pkg)['active']
    verifier.error = ('RUNTIME_GPU_ARCHITECTURE_UNSUPPORTED', 'no kernel image', 409)
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_GPU_ARCHITECTURE_UNSUPPORTED'
    status = managed.status()
    assert status['active']['id'] == first['id'] and status['previous'] is None
    assert native.server_path == Path(first['server'])
    assert len(list((tmp_path / 'runtime' / 'installs').iterdir())) == 1


def test_repair_update_rollback_and_pruning(tmp_path, native):
    managed, _, pkg = runtime(tmp_path, native)
    first = installed(managed, pkg)['active']['id']
    assert managed.last_result['action'] == 'INSTALL'
    managed.install(approve(pkg), wait=True)
    assert managed.last_result['action'] == 'REPAIR'
    status = managed.status()
    second = status['active']['id']
    assert status['previous']['id'] == first and second != first
    status = managed.rollback({'approved': True})
    assert status['active']['id'] == first and status['previous']['id'] == second
    assert native.server_path == Path(status['active']['server'])
    assert code(lambda: managed.rollback({})) == 'APPROVAL_REQUIRED'
    managed.install(approve(pkg), wait=True)
    folders = {p.name for p in (tmp_path / 'runtime' / 'installs').iterdir()}
    assert len(folders) == 2 and second not in folders, 'only the active and previous installs are kept'
    managed.install(approve(pkg), wait=True)
    manifest = Path(managed.status()['active']['path']) / MANIFEST
    manifest.write_text(manifest.read_text(encoding='utf-8').replace(catalog.BUILD['tag'], 'b1'), encoding='utf-8')
    assert managed.status()['update_available'] is True


def test_changed_files_block_native_start_until_repaired(tmp_path, native):
    managed, _, pkg = runtime(tmp_path, native)
    folder = Path(installed(managed, pkg)['active']['path'])
    (folder / 'ggml-planted.dll').write_bytes(b'x')
    assert managed.status()['state'] == 'UNVERIFIED' and 'FILES_ADDED_OR_REMOVED' in managed.status()['problems']
    assert code(managed.gate) == 'RUNTIME_NOT_VERIFIED'
    (folder / 'ggml-planted.dll').unlink()
    managed.gate()
    library = folder / 'ggml-base.dll'
    before = library.stat()
    library.write_bytes(b'S' + library.read_bytes()[1:])
    os.utime(library, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert managed.status()['state'] == 'READY', 'the quick check uses size and time (and the server hash)'
    assert managed.verify({})['last_result'] == {'action': 'VERIFY', 'at': managed.last_result['at'], 'ok': False,
                                                 'problems': ['HASH:ggml-base.dll']}
    server = folder / 'llama-server.exe'
    stat = server.stat()
    server.write_bytes(b'X' + server.read_bytes()[1:])
    os.utime(server, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert code(managed.gate) == 'RUNTIME_NOT_VERIFIED', 'the server executable is hashed before every start'
    managed.install(approve(pkg), wait=True)  # Repair
    managed.gate()


def test_nothing_changes_while_native_runs_or_an_install_is_running(tmp_path, native, monkeypatch):
    managed, _, pkg = runtime(tmp_path, native)
    installed(managed, pkg)
    managed.install(approve(pkg), wait=True)
    monkeypatch.setattr(native, 'busy', lambda: True)
    assert code(lambda: managed.install(approve(pkg))) == 'RUNTIME_IN_USE'
    assert code(lambda: managed.rollback({'approved': True})) == 'RUNTIME_IN_USE'
    assert code(lambda: managed.uninstall({'approved': True, 'confirm': 'UNINSTALL'})) == 'RUNTIME_IN_USE'
    monkeypatch.setattr(native, 'busy', lambda: False)
    managed._job = object()
    assert code(managed.gate) == 'RUNTIME_BUSY'
    managed._job = None


def test_offline_archives_are_used_verified_and_kept(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native)
    archives = tmp_path / 'runtime' / 'archives'
    archives.mkdir(parents=True)
    name = pkg['assets'][0]['name']
    (archives / name).write_bytes(hub.blobs[name])
    managed.detect({'approved': True})
    assert managed.status()['candidates'][0]['download_bytes'] == 0
    managed.install(approve(pkg), wait=True)
    assert hub.calls == [] and managed.status()['state'] == 'READY' and (archives / name).is_file()
    (archives / name).write_bytes(b'tampered' + hub.blobs[name][8:])
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_ARCHIVE_MISMATCH'
    assert (archives / name).is_file(), 'the owner\'s file is never deleted'


def test_uninstall_needs_typed_confirmation_and_removes_only_managed_installs(tmp_path, native):
    managed, _, pkg = runtime(tmp_path, native)
    installed(managed, pkg)
    archives = tmp_path / 'runtime' / 'archives'
    (archives / 'owner-note.txt').write_text('mine')
    other = tmp_path / 'runtime' / 'installs' / 'not-ours'
    other.mkdir()
    for bad in ({'approved': True}, {'approved': True, 'confirm': 'uninstall'}, {}):
        assert code(lambda: managed.uninstall(bad)) == 'APPROVAL_REQUIRED'
    status = managed.uninstall({'approved': True, 'confirm': 'UNINSTALL'})
    assert status['state'] == 'NOT_INSTALLED' and status['active'] is None
    assert status['last_result']['kept_archives'] == ['owner-note.txt'] and other.is_dir()
    assert not (tmp_path / 'runtime' / 'active.json').exists()
    assert native.server_path != Path(status['last_result']['was_active'])


def test_owner_supplied_server_wins_and_is_never_gated_or_replaced(tmp_path, native, monkeypatch):
    managed, _, pkg = runtime(tmp_path, native)
    installed(managed, pkg)
    own = tmp_path / 'own' / 'llama-server.exe'
    monkeypatch.setenv('NAJDILAB_NATIVE_SERVER', str(own))
    native.use_server(own)
    managed.attach()
    assert native.server_path == own and managed.status()['mode'] == 'EXTERNAL'
    managed.gate()


def test_unsupported_platform_is_blocked(tmp_path, native):
    host = {**WINDOWS, 'system': 'Darwin', 'machine': 'arm64'}
    managed, _, _ = runtime(tmp_path, native, host=host)
    assert managed.status()['state'] == 'BLOCKED' and managed.status()['platform']['supported'] is False
    assert managed.detect({'approved': True})['candidates'] == []


def test_build_identity_and_device_are_required(tmp_path, native, monkeypatch):
    managed, _, _ = runtime(tmp_path, native)
    server = tmp_path / 'llama-server.exe'
    server.write_bytes(b'x')
    outputs = {'version': b'version: 0.8.0-dev (build 12000, commit deadbee)\n'}
    monkeypatch.setattr(managed_runtime.subprocess, 'run', lambda c, **k: subprocess.CompletedProcess(c, 0, outputs['version'], b''))
    monkeypatch.setattr(managed_runtime, 'list_devices', lambda s, e: [])
    monkeypatch.setattr(managed, '_probe', lambda *a: {'device': 'probe'})
    cuda = {'id': 'windows-x64-cuda-13.4', 'backend': 'CUDA'}
    assert code(lambda: managed.verify_build(server, cuda, tmp_path)) == 'RUNTIME_IDENTITY_MISMATCH'
    outputs['version'] = b'version: 0.8.0-dev (build 12059, commit 1b6935b22)\nbuilt with Clang\n'
    assert code(lambda: managed.verify_build(server, cuda, tmp_path)) == 'RUNTIME_NO_DEVICE'
    monkeypatch.setattr(managed_runtime, 'list_devices', lambda s, e: [{'id': 'CUDA0', 'name': 'GPU', 'total_bytes': 1, 'free_bytes': 1}])
    evidence = managed.verify_build(server, cuda, tmp_path)
    assert evidence['version'] == {'build': 12059, 'commit': '1b6935b22'} and evidence['probe'] == {'device': 'probe'}
    assert managed.verify_build(server, {'id': 'windows-x64-cpu', 'backend': 'CPU'}, tmp_path)['probe'] == {'device': 'probe'}


@pytest.mark.skipif(not os.environ.get('NAJDILAB_RUNTIME_TEST_SERVER'), reason='set NAJDILAB_RUNTIME_TEST_SERVER to a llama.cpp b12059 llama-server')
def test_real_build_proves_identity_and_computes(tmp_path, native):
    server = Path(os.environ['NAJDILAB_RUNTIME_TEST_SERVER'])
    managed = ManagedRuntime(native, tmp_path / 'runtime')
    evidence = managed.verify_build(server, {'id': 'cpu', 'backend': 'CPU'}, tmp_path)
    assert evidence['version']['build'] == 12059 and evidence['probe']['tokens'] >= 1
    gpu = next((d for d in evidence['devices'] if d['id'].startswith('CUDA')), None)
    if gpu:
        evidence = managed.verify_build(server, {'id': 'cuda', 'backend': 'CUDA'}, tmp_path)
        layers = evidence['probe']['layers_on_gpu'].split('/')
        assert layers[0] == layers[1] != '0'


# ----- installer --------------------------------------------------------------
class FakeManaged:
    instances = []

    def __init__(self, native):
        self.calls = []
        FakeManaged.instances.append(self)
        row = {'id': 'windows-x64-cpu', 'label': 'CPU only', 'recommended': True, 'eligible': True, 'reasons': [],
               'assets': [{**a, 'offline_copy': False} for a in catalog.PACKAGES[3]['assets']],
               'preflight': {'decision': 'ALLOWED', 'destination': 'data', 'free_bytes': 10 ** 11, 'required_bytes': 10 ** 9}}
        self.base = {'platform': {'supported': True, 'system': 'Windows', 'machine': 'AMD64'}, 'active': None, 'problems': [],
                     'update_available': False, 'build': catalog.BUILD, 'candidates': [row]}

    def status(self):
        return self.base

    def detect(self, data):
        self.calls.append(('detect', data))
        return self.base

    def install(self, data, **kwargs):
        self.calls.append(('install', data))
        return {**self.base, 'active': {'package': data['package'], 'build': 'b12059',
                                        'verification': {'probe': {'device_name': None, 'layers_on_gpu': None}}}}


@pytest.mark.parametrize('answers,expected', [([], []), (['n'], []), (['y', 'n'], ['detect']), (['y', 'y'], ['detect', 'install'])])
def test_installer_downloads_only_after_two_explicit_yes_answers(monkeypatch, capsys, answers, expected):
    import builtins
    import importlib.util
    spec = importlib.util.spec_from_file_location('najdilab_runtime_setup', ROOT / 'scripts' / 'runtime_setup.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    monkeypatch.delenv('NAJDILAB_NATIVE_SERVER', raising=False)
    monkeypatch.setattr(installer, 'ManagedRuntime', FakeManaged)
    replies = iter(answers)

    def reply(prompt):
        assert prompt.endswith('[y/N] ')
        try:
            return next(replies)
        except StopIteration:
            raise EOFError from None
    monkeypatch.setattr(builtins, 'input', reply)
    FakeManaged.instances.clear()
    installer.offer_runtime(interactive=True)
    calls = FakeManaged.instances[0].calls
    assert [c[0] for c in calls] == expected
    if 'install' in expected:
        assert calls[1][1] == {'approved': True, 'package': 'windows-x64-cpu', 'license_acknowledged': True}
    out = capsys.readouterr().out
    assert 'nvidia-smi' in out and 'Nothing is sent anywhere' in out
    if 'detect' in expected:
        assert catalog.PACKAGES[3]['assets'][0]['sha256'] in out and 'MIT' in out
    FakeManaged.instances.clear()
    installer.offer_runtime(interactive=False)
    assert FakeManaged.instances == [], 'a non-interactive setup never inspects or downloads anything'


def test_install_runs_the_runtime_step_only_where_it_exists(tmp_path):
    source = (ROOT / 'scripts' / 'install.py').read_text(encoding='utf-8')
    assert 'from app' not in source and 'import app' not in source, 'the public Core candidate ships install.py without NajdiLab Native'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'install.py'), '--runtime'], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, timeout=60, env={k: v for k, v in os.environ.items() if k != 'NAJDILAB_NATIVE_SERVER'})
    assert result.returncode == 0, result.stderr
    assert 'not installed by a non-interactive setup' in result.stdout


def _archive_part(tmp_path, pkg):
    return tmp_path / 'runtime' / 'archives' / (pkg['assets'][0]['name'] + '.part')


def test_a_dropped_connection_resumes_from_the_exact_byte_and_still_checks_the_whole_file(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native, chunk=64)
    managed.retry_delay = 0
    hub.drop_after = 100
    status = installed(managed, pkg)
    assert status['state'] == 'READY' and status['active']['package'] == pkg['id']
    assert hub.ranges == [0, 100], 'the second request continues where the first stopped'
    assert not _archive_part(tmp_path, pkg).exists()


def test_a_download_that_keeps_failing_is_kept_and_continued_by_the_next_install(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native, chunk=64)
    managed.retry_delay = 0
    original = hub.__call__

    class Flaky:
        """Every response drops after 50 more bytes, three times in a row."""
        drops = 3

    def flaky(url, headers, timeout):
        if Flaky.drops and not url.startswith(catalog.RELEASE_URL):
            Flaky.drops -= 1
            hub.drop_after = 50
        return original(url, headers, timeout)
    managed.transport = flaky
    managed.detect({'approved': True})
    assert code(lambda: managed.install(approve(pkg), wait=True)) == 'RUNTIME_DOWNLOAD_UNREACHABLE'
    assert _archive_part(tmp_path, pkg).stat().st_size == 150 and managed.status()['active'] is None
    managed.install(approve(pkg), wait=True)
    assert managed.status()['state'] == 'READY' and hub.ranges[-1] == 150
    assert not _archive_part(tmp_path, pkg).exists()


def test_a_server_that_ignores_the_range_restarts_the_file_cleanly(tmp_path, native):
    managed, hub, pkg = runtime(tmp_path, native, chunk=64)
    managed.retry_delay = 0
    hub.drop_after, hub.honour_range = 100, False
    status = installed(managed, pkg)
    assert status['state'] == 'READY' and hub.ranges == [0, 100]
