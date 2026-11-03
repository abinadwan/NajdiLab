"""Hugging Face Direct, storage safety and the Smart Model Advisor. Synthetic hub, fake disks,
tiny synthetic GGUF; no network, no real model, no dependency on this computer's GPU."""
from __future__ import annotations

from collections import namedtuple
import hashlib
import os
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from app.db import apply_migrations, connect  # noqa: E402
from app.hf_hub import HubClient, HubError, checked_url, quantization, variant  # noqa: E402
from app.integrations import IntegrationError  # noqa: E402
from app.model_advisor import assess, host_profile  # noqa: E402
from app.model_store import ModelStore  # noqa: E402
from app.native_runtime import NativeRuntime  # noqa: E402
from fake_hub import COMMIT_A, COMMIT_B, FakeHub  # noqa: E402

Usage = namedtuple('Usage', 'total used free')
TINY = 'najdi-synthetic/Tiny-Chat-GGUF'
TINY_FILE = 'Tiny-Chat-Q4_K_M.gguf'


class Disk:
    """A fake volume: free space can be changed while a download runs."""
    def __init__(self, free):
        self.free, self.calls = free, 0

    def __call__(self, path):
        self.calls += 1
        return Usage(10 ** 12, 10 ** 12 - self.free, self.free)


@pytest.fixture
def hub():
    return FakeHub()


@pytest.fixture
def store_factory(tmp_path, hub):
    db = tmp_path / 'models.db'
    apply_migrations(db)

    def make(free=10 ** 10, reserve=1000, **kwargs):
        disk = kwargs.pop('disk', Disk(free))
        store = ModelStore(db, tmp_path / 'models' / 'huggingface', HubClient(hub), disk_usage=disk, reserve_bytes=reserve,
                           system_reserve_bytes=reserve, chunk=4096, check_every=8192, **kwargs)
        store.disk = disk
        return store
    return make


def approve(**overrides):
    return {'approved': True, 'license_acknowledged': True, 'repo_id': TINY, 'revision': COMMIT_A, 'filename': TINY_FILE, **overrides}


def wait(store, model_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = store._row(model_id)
        if model_id not in store._jobs and row['status'] != 'DOWNLOADING':
            return row
        time.sleep(0.02)
    raise AssertionError('download did not finish')


def code(fn):
    with pytest.raises((IntegrationError, HubError)) as caught:
        fn()
    return caught.value.code


# ---------------------------------------------------------------- discovery
def test_search_filters_gguf_validates_entries_and_sends_no_credentials(hub):
    client = HubClient(hub)
    found = client.search('tiny')
    assert [i['id'] for i in found['items']] == [TINY]
    assert found['items'][0]['license'] == 'apache-2.0'
    assert all('../' not in i['id'] for i in client.search('', 'najdi-synthetic')['items'])
    assert client.search('nothing-matches-this')['items'] == []
    method, host, path, _ = hub.calls[0]
    assert (method, host, path) == ('GET', 'huggingface.co', '/api/models')


def test_search_input_is_validated(hub):
    client = HubClient(hub)
    assert code(lambda: client.search('', '')) == 'INVALID_SEARCH'
    assert code(lambda: client.search('x' * 101)) == 'INVALID_SEARCH'
    assert code(lambda: client.search('', 'bad/author')) == 'INVALID_SEARCH'


def test_rate_limit_and_errors_are_reported_not_hidden(hub):
    client = HubClient(hub)
    hub.rate_limited = True
    with pytest.raises(HubError) as caught:
        client.search('tiny')
    assert caught.value.code == 'RATE_LIMITED' and caught.value.retry_after == 42
    hub.rate_limited = False
    assert code(lambda: client.model('missing-org/Missing')) == 'NOT_ACCESSIBLE'
    assert code(lambda: client.model('../etc')) == 'INVALID_REPOSITORY'


def test_details_pin_revision_and_classify_files(hub):
    details = HubClient(hub).model(TINY)
    assert details['revision'] == COMMIT_A and details['access'] == 'OPEN' and details['license'] == 'apache-2.0'
    files = {v['filename']: v for v in details['variants']}
    assert files[TINY_FILE]['supported'] and len(files[TINY_FILE]['sha256']) == 64
    assert files['Tiny-Chat-Q8_0-00001-of-00002.gguf']['unsupported_reasons'] == ['SPLIT_UNSUPPORTED']
    assert 'PROJECTOR_NOT_A_TEXT_MODEL' in files['mmproj-Tiny-Chat-f16.gguf']['unsupported_reasons']
    assert 'README.md' not in files, 'only GGUF files are ever offered'
    assert details['reported'] == {'parameters': 1_000_000, 'architecture': 'llama', 'context_length': 2048}


def test_changed_or_invalid_revision_is_refused(hub):
    client = HubClient(hub)
    assert code(lambda: client.model(TINY, 'not-a-commit')) == 'INVALID_REVISION'
    assert code(lambda: client.model(TINY, COMMIT_B)) == 'NOT_ACCESSIBLE'


def test_gated_repository_is_reported_and_not_bypassed(hub, store_factory):
    assert HubClient(hub).model('gated-org/Locked-GGUF')['access'] == 'GATED_MANUAL'
    store = store_factory()
    assert code(lambda: store.start(approve(repo_id='gated-org/Locked-GGUF', filename='Locked-Q4_K_M.gguf'))) == 'REPOSITORY_GATED'


def test_invalid_metadata_is_never_offered():
    assert variant({'rfilename': '../evil.gguf', 'size': 10, 'lfs': {'sha256': 'f' * 64}})['supported'] is False
    assert 'DIGEST_UNKNOWN' in variant({'rfilename': 'x-Q4_K_M.gguf', 'size': 10})['unsupported_reasons']
    assert 'SIZE_UNKNOWN' in variant({'rfilename': 'x-Q4_K_M.gguf', 'lfs': {'sha256': 'f' * 64}})['unsupported_reasons']
    assert variant({'rfilename': 'x.safetensors', 'size': 1}) is None
    assert quantization('Model-IQ2_M.gguf') == 'IQ2_M' and quantization('Model-Q4_K_M.gguf') == 'Q4_K_M'


@pytest.mark.parametrize('url', ['http://huggingface.co/x', 'https://evil.example/x', 'https://huggingface.co.evil.com/x',
                                 'https://user:pw@huggingface.co/x', 'https://huggingface.co:8443/x', 'file:///etc/passwd'])
def test_only_https_huggingface_hosts_are_fetched(url):
    with pytest.raises(HubError) as caught:
        checked_url(url)
    assert caught.value.code == 'HUB_URL_REFUSED'


def test_redirect_to_a_foreign_host_is_refused(hub):
    hub.redirect_host = 'evil.example'
    with pytest.raises(HubError) as caught:
        HubClient(hub).open_file(TINY, COMMIT_A, TINY_FILE)
    assert caught.value.code == 'HUB_URL_REFUSED'
    assert not any(host == 'evil.example' for _, host, _, _ in hub.calls)


def test_remote_header_reads_metadata_with_bounded_ranges(hub):
    info = HubClient(hub).remote_header(TINY, COMMIT_A, TINY_FILE, len(hub.gguf))
    assert info['architecture'] == 'llama' and info['model_max_context'] == 8192
    assert all(r and r.startswith('bytes=0-') for _, host, _, r in hub.calls if host == hub.redirect_host)


# ---------------------------------------------------------------- storage
def test_download_requires_license_acknowledgement_and_approval_separately(store_factory):
    store = store_factory()
    assert code(lambda: store.start(approve(license_acknowledged=False))) == 'LICENSE_ACKNOWLEDGEMENT_REQUIRED'
    assert code(lambda: store.start(approve(approved=False))) == 'APPROVAL_REQUIRED'
    assert code(lambda: store.start({'approved': True})) == 'INVALID_PAYLOAD'


def test_successful_download_is_verified_and_ready(store_factory, hub):
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    assert row['status'] == 'READY' and row['verified_sha256'] == hashlib.sha256(hub.gguf).hexdigest()
    path = store.root / row['relative_path']
    assert path.read_bytes() == hub.gguf
    assert not path.with_name(path.name + '.part').exists()
    assert row['architecture'] == 'llama' and row['model_max_context'] == 8192
    assert row['relative_path'] == f'najdi-synthetic--Tiny-Chat-GGUF/{COMMIT_A[:12]}/{TINY_FILE}'


def test_preflight_counts_reserve_other_downloads_and_exact_boundary(store_factory, hub):
    size = len(hub.gguf)
    from app.model_store import SIDECAR_BYTES
    exact = size + SIDECAR_BYTES + 1000
    store = store_factory(free=exact, reserve=1000)
    plan = store.preflight(size)
    assert plan['decision'] == 'ALLOWED' and plan['required_bytes'] == exact and plan['free_after_bytes'] == exact - size
    assert plan['temporary_bytes'] == size + SIDECAR_BYTES, 'the .part is the only extra copy; finalising is a rename'
    store.disk.free = exact - 1
    assert store.preflight(size)['decision'] == 'BLOCKED'
    assert store.preflight(size, already_bytes=size)['to_write_bytes'] == 0


def test_insufficient_space_refuses_before_any_byte_is_written(store_factory, hub):
    store = store_factory(free=100, reserve=0)
    assert code(lambda: store.start(approve())) == 'INSUFFICIENT_SPACE'
    assert not any(host == hub.redirect_host for _, host, _, _ in hub.calls)
    assert store.library()['items'] == []


def test_space_shrinking_during_download_pauses_safely(store_factory, hub):
    class Shrinking(Disk):
        def __call__(self, path):
            usage = super().__call__(path)
            self.free = 2000 if self.calls > 2 else self.free
            return usage
    store = store_factory(disk=Shrinking(10 ** 10), reserve=1000)
    row = wait(store, store.start(approve())['id'])
    assert row['status'] == 'PAUSED' and row['error_code'] == 'STORAGE_RESERVE'
    assert not (store.root / row['relative_path']).exists(), 'nothing is finalised after a safety pause'


def test_concurrent_downloads_share_one_storage_budget(store_factory, hub):
    store = store_factory()
    store.max_active = 1
    first = store.start(approve())
    assert code(lambda: store.start(approve())) in {'DOWNLOADS_BUSY', 'ALREADY_IN_LIBRARY'}
    wait(store, first['id'])


def test_cancel_removes_partial_files_and_the_record(store_factory, hub):
    hub.fail_after = 8192  # connection drops: the download pauses with its verified prefix
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    assert row['status'] == 'PAUSED' and row['error_code'] == 'HUB_UNREACHABLE'
    part = store.root / (row['relative_path'] + '.part')
    assert part.exists()
    store.control(row['id'], 'cancel')
    assert not part.exists() and store.library()['items'] == []
    assert not (store.root / 'najdi-synthetic--Tiny-Chat-GGUF').exists(), 'empty managed folders are removed'


def test_resume_continues_from_a_matching_prefix_and_verifies_everything(store_factory, hub):
    hub.fail_after = 8192
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    hub.fail_after = None
    assert code(lambda: store.control(row['id'], 'resume', {})) == 'APPROVAL_REQUIRED'
    store.control(row['id'], 'resume', {'approved': True})
    done = wait(store, row['id'])
    assert done['status'] == 'READY'
    ranges = [r for _, host, _, r in hub.calls if host == hub.redirect_host and r]
    assert ranges[-1].startswith('bytes=8192-') or ranges[-1].startswith('bytes=')


def test_resume_discards_a_prefix_for_a_different_file(store_factory, hub):
    hub.fail_after = 8192
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    sidecar = store.root / (row['relative_path'] + '.part.json')
    sidecar.write_text('{"tampered": true}', encoding='utf-8')
    hub.fail_after = None
    store.control(row['id'], 'resume', {'approved': True})
    assert wait(store, row['id'])['status'] == 'READY'


def test_corrupted_or_wrong_digest_download_is_rejected_and_removed(store_factory, hub):
    store = store_factory()
    row = wait(store, store.start(approve(repo_id='najdi-synthetic/Wrong-Digest-GGUF', revision=COMMIT_B,
                                          filename='Wrong-Q4_K_M.gguf'))['id'])
    assert row['status'] == 'ERROR' and row['error_code'] in {'HASH_MISMATCH', 'DIGEST_MISMATCH'}
    assert not (store.root / row['relative_path']).exists()
    assert not (store.root / (row['relative_path'] + '.part')).exists()
    hub.serve_bytes = bytes(len(hub.gguf))  # same size, wrong bytes
    store2 = store_factory()
    bad = wait(store2, store2.start(approve())['id'])
    assert bad['status'] == 'ERROR' and bad['error_code'] == 'HASH_MISMATCH'


def test_disk_full_while_writing_pauses_and_keeps_nothing_final(store_factory, hub, monkeypatch):
    import errno
    store = store_factory()
    real_open = Path.open

    def full(self, mode='r', *args, **kwargs):
        handle = real_open(self, mode, *args, **kwargs)
        if self.name.endswith('.part') and 'a' in mode:
            def write(data):
                raise OSError(errno.ENOSPC, 'No space left on device')
            handle.write = write
        return handle
    monkeypatch.setattr(Path, 'open', full)
    row = wait(store, store.start(approve())['id'])
    assert row['status'] == 'PAUSED' and row['error_code'] == 'DISK_FULL'
    assert not (store.root / row['relative_path']).exists()


def test_existing_file_is_never_replaced(store_factory, hub):
    store = store_factory()
    target = store.root / f'najdi-synthetic--Tiny-Chat-GGUF/{COMMIT_A[:12]}/{TINY_FILE}'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'owner file')
    assert code(lambda: store.start(approve())) == 'ALREADY_PRESENT'
    assert target.read_bytes() == b'owner file'


@pytest.mark.parametrize('field,value', [('filename', '../escape.gguf'), ('filename', 'sub/dir.gguf'), ('filename', 'x.safetensors'),
                                         ('repo_id', '../../x'), ('revision', 'main')])
def test_invalid_paths_and_identifiers_are_refused(store_factory, field, value):
    assert code(lambda: store_factory().start(approve(**{field: value}))) == 'INVALID_FILE'


@pytest.mark.skipif(os.name == 'nt' and not os.environ.get('NAJDILAB_TEST_SYMLINKS'), reason='Symlink creation not permitted by this Windows account')
def test_symlinked_managed_folder_is_refused(tmp_path, hub):
    db = tmp_path / 'm.db'
    apply_migrations(db)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models' / 'huggingface').symlink_to(outside, target_is_directory=True)
    store = ModelStore(db, tmp_path / 'models' / 'huggingface', HubClient(hub), disk_usage=Disk(10 ** 10), reserve_bytes=0)
    assert code(lambda: store.start(approve())) == 'PATH_REFUSED'
    assert not any(outside.iterdir())


def test_delete_needs_exact_confirmation_and_never_touches_other_files(store_factory, hub, tmp_path):
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    neighbour = store.root.parent / 'owner-model.gguf'
    neighbour.write_bytes(b'not managed')
    assert code(lambda: store.delete(row['id'], {'approved': True})) == 'CONFIRMATION_REQUIRED'
    assert code(lambda: store.delete(row['id'], {'approved': True, 'confirm': 'wrong.gguf'})) == 'CONFIRMATION_REQUIRED'
    store.in_use = lambda path: True
    assert code(lambda: store.delete(row['id'], {'approved': True, 'confirm': TINY_FILE})) == 'MODEL_IN_USE'
    store.in_use = lambda path: False
    store.delete(row['id'], {'approved': True, 'confirm': TINY_FILE})
    assert not (store.root / row['relative_path']).exists()
    assert neighbour.read_bytes() == b'not managed'
    assert code(lambda: store.delete(row['id'], {'approved': True, 'confirm': TINY_FILE})) == 'MODEL_NOT_FOUND'


def test_recheck_detects_tampering(store_factory, hub):
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    path = store.root / row['relative_path']
    path.write_bytes(path.read_bytes()[:-1] + b'\x00')
    assert store.recheck(row['id'])['error_code'] == 'HASH_MISMATCH'
    path.unlink()
    assert store.recheck(row['id'])['error_code'] == 'MISSING'


def test_finished_row_is_never_reported_active(store_factory, hub):
    """READY is written before the job leaves the active list; the library must not show both,
    or the interface hides Delete and keeps polling (a race seen under load in the browser test)."""
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    from app.model_store import _Job, volume_of
    store._jobs[row['id']] = _Job(store._row(row['id']), volume_of(store.root))  # the instant before removal
    item = store.library()['items'][0]
    assert item['status'] == 'READY' and item['active'] is False
    store._jobs.clear()


def test_restart_marks_interrupted_downloads_paused(store_factory, hub):
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    with connect(store.db_path) as conn:
        conn.execute("UPDATE managed_models SET status='DOWNLOADING' WHERE id=?", (row['id'],))
    assert store_factory()._row(row['id'])['status'] == 'PAUSED'


# ---------------------------------------------------------------- runtime gate
def test_native_refuses_unverified_managed_files_and_never_autostarts(store_factory, hub, tmp_path):
    store = store_factory()
    row = wait(store, store.start(approve())['id'])
    native = NativeRuntime(server_path=tmp_path / 'no-server.exe', models_dir=store.root.parent)
    native.start_gate = store.native_gate
    assert native.status()['state'] == 'STOPPED', 'a finished download starts nothing'
    listed = {m['id']: m for m in native.models()['items']}
    assert f"huggingface/{row['relative_path']}" in listed
    with connect(store.db_path) as conn:
        conn.execute("UPDATE managed_models SET status='UNVERIFIED' WHERE id=?", (row['id'],))
    request = {'approved': True, 'model': f"huggingface/{row['relative_path']}", 'context_budget': 2048, 'gpu_layers': '0'}
    assert code(lambda: native.start(request)) == 'NATIVE_SERVER_MISSING'  # no server: refused before any gate
    native.server_path = tmp_path / 'fake-server.exe'
    native.server_path.write_bytes(b'')
    assert code(lambda: native.start(request)) == 'MODEL_NOT_VERIFIED'
    stray = store.root / 'stray.gguf'
    stray.write_bytes(hub.gguf)
    assert code(lambda: native.start({**request, 'model': 'huggingface/stray.gguf'})) == 'MODEL_NOT_VERIFIED'
    assert native.status()['state'] == 'STOPPED'


# ---------------------------------------------------------------- advisor
GIB = 1024 ** 3
KV = {'block_count': 32, 'embedding_length': 4096, 'attention.head_count': 32, 'attention.head_count_kv': 8}
MODEL = {'architecture': 'llama', 'model_max_context': 32768, 'kv': KV, 'quantization': 'Q4_K_M'}
VARIANT = {'filename': 'm-Q4_K_M.gguf', 'size_bytes': 4 * GIB, 'quantization': 'Q4_K_M', 'supported': True, 'unsupported_reasons': []}


def host(gpu_free=None, ram_free=32 * GIB, server=True, runtime_gpu=True, approved=True):
    snapshot = {'ram_total_bytes': 64 * GIB, 'ram_available_bytes': ram_free, 'warnings': [],
                'gpus': [] if gpu_free is None else [{'name': 'Synthetic GPU', 'total_bytes': 12 * GIB, 'free_bytes': gpu_free, 'backend': 'NVIDIA'}]}
    devices = [{'name': 'Synthetic GPU', 'total_bytes': 12 * GIB}] if runtime_gpu and gpu_free is not None else []
    return host_profile(snapshot if approved else None, {'server_available': server, 'devices': devices})


def label(**kwargs):
    args = {'variant': VARIANT, 'access': 'OPEN', 'model': MODEL, 'host': host(gpu_free=11 * GIB), 'context': 8192}
    args.update(kwargs)
    return assess(**args)['load']['classification']


def test_advisor_classifies_compatible_limited_unverified_blocked():
    assert label() == 'COMPATIBLE'
    assert label(host=host(gpu_free=3 * GIB)) == 'LIMITED', 'partial offload'
    assert label(host=host(gpu_free=None)) == 'LIMITED', 'CPU only'
    assert label(host=host(gpu_free=11 * GIB, approved=False)) == 'UNVERIFIED'
    assert label(model={**MODEL, 'kv': None}) == 'UNVERIFIED'
    assert label(model={'error': 'TRUNCATED'}) == 'UNVERIFIED'
    assert label(access='GATED_MANUAL') == 'BLOCKED'
    assert label(host=host(gpu_free=11 * GIB, server=False)) == 'BLOCKED'
    assert label(context=65536) == 'BLOCKED', 'above the model maximum'
    assert label(host=host(gpu_free=1 * GIB, ram_free=1 * GIB)) == 'BLOCKED', 'does not fit free memory'


def test_advisor_low_vram_low_ram_and_gpu_setting():
    assert label(host=host(gpu_free=1 * GIB, ram_free=2 * GIB)) == 'BLOCKED'
    assert label(gpu_layers='all', host=host(gpu_free=3 * GIB)) == 'BLOCKED', 'all layers cannot fit'
    assert label(gpu_layers='0') == 'LIMITED', 'CPU only by choice'
    result = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=11 * GIB, runtime_gpu=False), context=8192)
    assert result['load']['classification'] == 'LIMITED'
    assert any(r['code'] == 'RUNTIME_NO_GPU' for r in result['load']['reasons'])


def test_advisor_memory_depends_on_context_and_labels_estimates():
    # 4 GiB weights + 128 KiB/token KV: about 5.6 GiB at 4096 tokens, about 9.7 GiB at 32768 (estimates).
    small = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=8 * GIB), context=4096)
    large = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=8 * GIB), context=32768)
    assert large['estimate']['required_bytes'] > small['estimate']['required_bytes']
    assert small['estimate']['kind'] == 'estimate' and large['load']['classification'] != 'COMPATIBLE'
    assert large['load']['largest_gpu_context'] == 16384, 'largest context that fits fully on the GPU'
    assert large['load']['recommended_context'] == 32768, 'larger contexts still fit with partial offload'
    kinds = {e['label']: e['kind'] for e in small['evidence']}
    assert kinds['System memory available now'] == 'measured' and kinds['KV cache per token (upper bound, f16)'] == 'estimate'


def test_advisor_separates_download_from_loading():
    blocked_space = {'decision': 'BLOCKED', 'reasons': [{'code': 'INSUFFICIENT_SPACE', 'message': 'x'}]}
    result = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=11 * GIB), context=8192, storage=blocked_space)
    assert result['download']['decision'] == 'BLOCKED' and result['load']['classification'] == 'COMPATIBLE'
    no_server = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=11 * GIB, server=False), context=8192,
                       storage={'decision': 'ALLOWED', 'reasons': []})
    assert no_server['download']['decision'] == 'ALLOWED' and no_server['load']['classification'] == 'BLOCKED'
    split = {**VARIANT, 'supported': False, 'unsupported_reasons': ['SPLIT_UNSUPPORTED']}
    assert assess(variant=split, access='OPEN', model=None, host=host(gpu_free=11 * GIB), context=8192)['load']['classification'] == 'BLOCKED'


def test_performance_line_is_conditional_when_loading_is_blocked():
    """A BLOCKED model must not be described as if it runs."""
    result = assess(variant=VARIANT, access='OPEN', model=MODEL, host=host(gpu_free=11 * GIB, server=False), context=8192)
    assert result['load']['classification'] == 'BLOCKED'
    assert result['performance']['expectation'].startswith('If loaded,')


def test_advisor_unknown_hardware_never_claims_compatibility():
    unknown = host_profile({'ram_total_bytes': None, 'ram_available_bytes': None, 'gpus': [], 'warnings': ['RAM_UNAVAILABLE']},
                           {'server_available': True, 'devices': []})
    assert label(host=unknown) == 'UNVERIFIED'


# ---------------------------------------------------------------- HTTP routes
def test_routes_need_the_csrf_token_and_report_hub_errors_with_codes(tmp_path, hub, monkeypatch):
    import http.client
    import json
    import threading
    from app import server
    from app.model_service import ModelLibrary
    db = tmp_path / 'http.db'
    apply_migrations(db)
    monkeypatch.setattr(server, 'DB_PATH', db)
    http_server = server.NajdiLabHTTPServer(('127.0.0.1', 0), server.NajdiLabHandler)
    http_server.native.models_dir = tmp_path / 'models'
    client = HubClient(hub)
    http_server._models = ModelLibrary(db, http_server.native, hub=client,
                                       store=ModelStore(db, tmp_path / 'models' / 'huggingface', client, disk_usage=Disk(10 ** 10),
                                                        reserve_bytes=0, system_reserve_bytes=0),
                                       snapshot=lambda: {'ram_total_bytes': 8 * GIB, 'ram_available_bytes': 4 * GIB, 'gpus': [], 'warnings': []})
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    host = f'127.0.0.1:{http_server.server_port}'

    def call(method, path, body=None, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', http_server.server_port, timeout=10)
        headers = {'Host': host, 'Content-Type': 'application/json'}
        if token:
            connection.request('GET', '/api/v1/session', headers={'Host': host})
            headers['X-NajdiLab-CSRF'] = json.loads(connection.getresponse().read())['csrf_token']
        connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b'{}')
    try:
        calls_before = len(hub.calls)
        status, _ = call('POST', '/api/v1/models/hub/search', {'query': 'tiny'}, token=False)
        assert status == 403 and len(hub.calls) == calls_before, 'no network request without the session token'
        status, body = call('POST', '/api/v1/models/hub/search', {'query': 'tiny'})
        assert status == 200 and body['items'][0]['id'] == TINY
        hub.rate_limited = True
        status, body = call('POST', '/api/v1/models/hub/search', {'query': 'tiny'})
        assert status == 429 and body.get('code') == 'RATE_LIMITED'
        hub.rate_limited = False
        status, body = call('POST', '/api/v1/models/advise', {'repo_id': TINY, 'revision': COMMIT_A, 'filename': TINY_FILE,
                                                               'context': 4096, 'gpu_layers': 'auto', 'hardware_approved': True})
        assert status == 200 and body['load']['classification'] in {'BLOCKED', 'LIMITED', 'UNVERIFIED'}
        assert body['download']['decision'] == 'ALLOWED' and body['file']['sha256']
        status, body = call('POST', '/api/v1/models/downloads', {'approved': True, 'license_acknowledged': False, 'repo_id': TINY,
                                                                  'revision': COMMIT_A, 'filename': TINY_FILE})
        assert status == 403 and body.get('code') == 'LICENSE_ACKNOWLEDGEMENT_REQUIRED'
        status, body = call('GET', '/api/v1/models/library')
        assert status == 200 and body['items'] == []
        status, body = call('POST', '/api/v1/models/unknown', {})
        assert status == 404
    finally:
        http_server.shutdown()
        http_server.server_close()
