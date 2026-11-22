"""Training model manager (V2.2.0): Safetensors checkpoints for external training. Fake hub; no network."""
from __future__ import annotations

import hashlib
import io
import json

import pytest

from app.hf_hub import HubError, Response, TRAINING_NAME
from app.integrations import IntegrationError
from app.training_models import MANIFEST, TrainingModels, git_blob_sha1, plan

REV = 'a' * 40
CONFIG = b'{"model_type": "qwen2"}'
TOKENIZER = b'{"version": "1.0"}'
WEIGHTS = bytes(range(256)) * 40


def lfs(name, data):
    return {'name': name, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'git_blob': None}


def small(name, data):
    return {'name': name, 'size_bytes': len(data), 'sha256': None, 'git_blob': git_blob_sha1(data)}


class FakeHub:
    def __init__(self, blobs, *, access='OPEN', tags=()):
        self.blobs, self.access, self.tags = dict(blobs), access, list(tags)
        self.served, self.starts, self.drop_once, self.corrupt = {}, [], None, set()

    def files(self, repo_id, revision=None):
        if revision and revision != REV:
            raise HubError('REVISION_CHANGED', 'changed', 409)
        rows = [lfs(n, d) if n.endswith('.safetensors') else small(n, d) for n, d in self.blobs.items()]
        return {'id': repo_id, 'revision': REV, 'access': self.access, 'private': False, 'disabled': False,
                'license': 'apache-2.0', 'license_name': None, 'license_link': None, 'tags': self.tags, 'base_models': [], 'files': rows}

    def open_file(self, repo_id, revision, filename, *, start=0, expected_size=None, expected_sha256=None, names=None, end=None):
        assert names is TRAINING_NAME and TRAINING_NAME.fullmatch(filename)
        data = self.blobs[filename]
        if filename in self.corrupt:
            data = b'X' + data[1:]
        self.starts.append((filename, start))
        body = io.BytesIO(data[start:])
        if self.drop_once == filename:
            self.drop_once = None
            plain, served = body.read, [0]

            def dropping(n):
                if served[0] >= 1000:
                    raise OSError('reset')
                block = plain(min(n, 1000 - served[0]))
                served[0] += len(block)
                return block
            body.read = dropping
        return Response(206 if start else 200, {}, body, lambda: None)


class Disk:
    def __init__(self, free=10 ** 12):
        self.free = free

    def __call__(self, path):
        return type('U', (), {'free': self.free})()


COMPLETE = {'config.json': CONFIG, 'tokenizer.json': TOKENIZER, 'model.safetensors': WEIGHTS}


def manager(tmp_path, hub, **kw):
    return TrainingModels(hub, tmp_path / 'training-models', disk_usage=kw.pop('disk', Disk()), reserve_bytes=0,
                          cache_roots=kw.pop('cache_roots', []))


def approve(repo='unsloth/Model-Instruct'):
    return {'approved': True, 'license_acknowledged': True, 'repo_id': repo, 'revision': REV}


def test_inspect_lists_what_a_trainer_needs_and_explains_what_cannot_be_trained():
    assert plan(['config.json', 'tokenizer.json', 'model.safetensors'])['complete'] is True
    assert plan(['config.json', 'vocab.json', 'merges.txt', 'a.safetensors'])['complete'] is True
    gguf = plan(['model-Q4_K_M.gguf', 'README.md'])
    assert not gguf['complete'] and gguf['notes'][0]['code'] == 'GGUF_ONLY'
    assert plan(['config.json', 'tokenizer.json', 'pytorch_model.bin'])['notes'][0]['code'] == 'PICKLE_WEIGHTS'
    assert plan(['config.json', 'tokenizer.json', 'model-00001-of-00002.safetensors'], ['model-00001-of-00002.safetensors',
                'model-00002-of-00002.safetensors'])['missing'] == ['model-00002-of-00002.safetensors']


def test_review_shows_size_license_and_never_offers_code_or_pickles(tmp_path):
    hub = FakeHub({**COMPLETE, 'modeling_custom.py': b'import os', 'pytorch_model.bin': b'pickle', 'README.md': b'card'})
    review = manager(tmp_path, hub).inspect('unsloth/Model-Instruct')
    assert review['downloadable'] and review['revision'] == REV and review['license'] == 'apache-2.0'
    assert sorted(f['name'] for f in review['files']) == ['config.json', 'model.safetensors', 'tokenizer.json']
    assert review['total_bytes'] == len(CONFIG) + len(TOKENIZER) + len(WEIGHTS)
    gated = manager(tmp_path, FakeHub(COMPLETE, access='GATED_MANUAL')).inspect('org/gated')
    assert not gated['downloadable'] and 'does not bypass' in gated['blocked_reason']
    four = manager(tmp_path, FakeHub(COMPLETE)).inspect('unsloth/gemma-4-E4B-it-unsloth-bnb-4bit')
    assert any(n['code'] == 'PREQUANTIZED_4BIT' for n in four['notes'])


def test_an_index_that_points_outside_the_repository_is_refused(tmp_path):
    index = json.dumps({'weight_map': {'a': '../outside.safetensors'}}).encode()
    with pytest.raises(IntegrationError) as caught:
        manager(tmp_path, FakeHub({**COMPLETE, 'model.safetensors.index.json': index})).inspect('org/m')
    assert caught.value.code == 'INDEX_INVALID'


def test_download_needs_approval_and_license_then_verifies_every_file(tmp_path):
    hub = FakeHub(COMPLETE)
    m = manager(tmp_path, hub)
    for change, code in (({'license_acknowledged': False}, 'LICENSE_ACKNOWLEDGEMENT_REQUIRED'), ({'approved': False}, 'APPROVAL_REQUIRED'),
                         ({'revision': 'main'}, 'INVALID_REPOSITORY')):
        with pytest.raises(IntegrationError) as caught:
            m.start({**approve(), **change})
        assert caught.value.code == code
    assert not (tmp_path / 'training-models').exists(), 'nothing is written before approval'
    job = m.start(approve(), wait=True)
    assert job['state'] == 'READY' and job['done_bytes'] == job['total_bytes']
    folder = tmp_path / 'training-models' / 'unsloth--Model-Instruct' / REV
    assert (folder / 'model.safetensors').read_bytes() == WEIGHTS
    manifest = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    assert manifest['revision'] == REV and manifest['license'] == 'apache-2.0' and len(manifest['files']) == 3
    listed = m.library()['models']
    assert [(x['repo_id'], x['status'], x['complete']) for x in listed] == [('unsloth/Model-Instruct', 'READY', True)]
    with pytest.raises(IntegrationError) as caught:
        m.start(approve())
    assert caught.value.code == 'ALREADY_PRESENT', 'a downloaded revision is never replaced'


def test_a_corrupted_file_is_discarded_and_nothing_is_published(tmp_path):
    hub = FakeHub(COMPLETE)
    hub.corrupt = {'model.safetensors'}
    job = manager(tmp_path, hub).start(approve(), wait=True)
    assert job['state'] == 'ERROR' and job['error']['code'] == 'DIGEST_MISMATCH'
    assert not (tmp_path / 'training-models' / 'unsloth--Model-Instruct').exists()
    staging = next((tmp_path / 'training-models').glob('.staging-*'))
    assert not (staging / 'model.safetensors.part').exists() and not (staging / 'model.safetensors').exists()


def test_an_interrupted_file_resumes_where_it_stopped(tmp_path):
    hub = FakeHub(COMPLETE)
    hub.drop_once = 'model.safetensors'
    m = manager(tmp_path, hub)
    first = m.start(approve(), wait=True)
    assert first['state'] == 'ERROR' and first['error']['code'] == 'DOWNLOAD_INTERRUPTED'
    second = m.start(approve(), wait=True)
    assert second['state'] == 'READY'
    assert ('model.safetensors', 1000) in hub.starts, 'the second attempt continues from the saved bytes'
    assert sum(1 for name, _ in hub.starts if name == 'config.json') == 1, 'verified files are not fetched again'


def test_low_disk_refuses_before_anything_is_downloaded(tmp_path):
    hub = FakeHub(COMPLETE)
    with pytest.raises(IntegrationError) as caught:
        manager(tmp_path, hub, disk=Disk(10)).start(approve())
    assert caught.value.code == 'INSUFFICIENT_SPACE' and hub.starts == []


def test_hugging_face_cache_is_listed_read_only(tmp_path):
    snapshot = tmp_path / 'hub' / 'models--unsloth--Qwen2.5-0.5B-Instruct' / 'snapshots' / REV
    snapshot.mkdir(parents=True)
    for name, data in COMPLETE.items():
        (snapshot / name).write_bytes(data)
    gguf = tmp_path / 'hub' / 'models--org--Model-GGUF' / 'snapshots' / REV
    gguf.mkdir(parents=True)
    (gguf / 'model-Q4_K_M.gguf').write_bytes(b'GGUF')
    before = {p: p.read_bytes() for p in (tmp_path / 'hub').rglob('*') if p.is_file()}
    found = {c['repo_id']: c for c in manager(tmp_path, FakeHub({}), cache_roots=[tmp_path / 'hub']).cache()}
    assert found['unsloth/Qwen2.5-0.5B-Instruct']['complete'] is True
    assert found['org/Model-GGUF']['complete'] is False and found['org/Model-GGUF']['notes'][0]['code'] == 'GGUF_ONLY'
    assert {p: p.read_bytes() for p in (tmp_path / 'hub').rglob('*') if p.is_file()} == before


def _downloaded(tmp_path):
    hub = FakeHub(COMPLETE)
    m = manager(tmp_path, hub)
    assert m.start(approve(), wait=True)['state'] == 'READY'
    return m, m.library()['models'][0]


def test_deleting_a_checkpoint_shows_what_is_freed_then_removes_only_its_folder(tmp_path):
    m, entry = _downloaded(tmp_path)
    neighbour = tmp_path / 'training-models' / 'keep.txt'
    neighbour.write_text('not managed')
    plan = m.delete_plan(entry['id'])
    assert plan['action'] == 'delete_checkpoint' and plan['confirm_text'] == 'unsloth/Model-Instruct'
    assert plan['frees_bytes'] == sum(f['size_bytes'] for f in plan['files']) > len(WEIGHTS)
    with pytest.raises(IntegrationError) as caught:
        m.delete({'approved': True, 'confirm': 'wrong', 'id': entry['id']})
    assert caught.value.code == 'CONFIRMATION_REQUIRED' and (tmp_path / 'training-models' / entry['id']).exists()
    done = m.delete({'approved': True, 'confirm': 'unsloth/Model-Instruct', 'id': entry['id']})
    assert done['freed_bytes'] == plan['frees_bytes'] and m.library()['models'] == []
    assert not (tmp_path / 'training-models' / 'unsloth--Model-Instruct').exists() and neighbour.read_text() == 'not managed'


def test_an_interrupted_download_is_listed_and_removable(tmp_path):
    hub = FakeHub(COMPLETE)
    hub.drop_once = 'model.safetensors'
    m = manager(tmp_path, hub)
    assert m.start(approve(), wait=True)['state'] == 'ERROR'
    partial = next(x for x in m.library()['models'] if x['status'] == 'PARTIAL')
    plan = m.delete_plan(partial['id'])
    assert plan['action'] == 'remove_partial_download' and plan['frees_bytes'] > 0
    m.delete({'approved': True, 'confirm': partial['id'], 'id': partial['id']})
    assert m.library()['models'] == []


def test_cache_and_paths_outside_the_folder_can_never_be_deleted(tmp_path):
    m, entry = _downloaded(tmp_path)
    snapshot = tmp_path / 'hub' / 'models--unsloth--Qwen' / 'snapshots' / REV
    snapshot.mkdir(parents=True)
    (snapshot / 'config.json').write_bytes(CONFIG)
    for bad in ('../hub', str(snapshot), r'..\hub', 'unsloth--Model-Instruct', ''):
        with pytest.raises(IntegrationError):
            m.delete_plan(bad)
    assert (snapshot / 'config.json').exists()


def test_a_locked_file_keeps_the_entry_listed_for_a_retry(tmp_path, monkeypatch):
    from pathlib import Path
    m, entry = _downloaded(tmp_path)
    folder = tmp_path / 'training-models' / entry['id']
    real_unlink = Path.unlink

    def locked(self, missing_ok=False):
        if self.name == 'model.safetensors':
            raise PermissionError(13, 'in use')
        return real_unlink(self, missing_ok=missing_ok)
    monkeypatch.setattr(Path, 'unlink', locked)
    with pytest.raises(IntegrationError) as caught:
        m.delete({'approved': True, 'confirm': 'unsloth/Model-Instruct', 'id': entry['id']})
    assert caught.value.code == 'DELETE_FAILED' and (folder / MANIFEST).exists()
    assert [x['status'] for x in m.library()['models']] == ['CHANGED'], 'still listed, marked as changed'
    monkeypatch.setattr(Path, 'unlink', real_unlink)
    m.delete({'approved': True, 'confirm': 'unsloth/Model-Instruct', 'id': entry['id']})
    assert m.library()['models'] == []
