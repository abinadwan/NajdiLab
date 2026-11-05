"""Training models: Safetensors checkpoints for external fine-tuning.

An inference model (GGUF, run by llama.cpp in NajdiLab Native) and a training model (a Hugging Face
checkpoint: config, tokenizer and Safetensors weights, used by Unsloth/TRL outside NajdiLab) are different
artifacts, and a GGUF file is not a training checkpoint. This module:

- inspects a repository at one immutable revision: license, access, the files a trainer needs, total size,
  completeness and compatibility notes (GGUF-only, PyTorch `.bin`, pre-quantized 4-bit);
- downloads a complete checkpoint only after approval and license acknowledgement, one file at a time
  into a staging folder, verifying each file (LFS SHA-256, or the git blob id for small files), resuming
  interrupted files with a Range request, and publishing the folder only when every file is verified;
- lists NajdiLab's own training models and, read-only, complete checkpoints already in the Hugging Face
  cache. It never runs model code, never loads weights, never deletes or changes cached files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading

from .db import DATA_DIR, utc_now
from .hf_hub import COMMIT, REPO_ID, TRAINING_NAME, HubError
from .integrations import IntegrationError

MANIFEST = 'najdilab-training-model.json'
TOKENIZER_SETS = (('tokenizer.json',), ('tokenizer.model',), ('vocab.json', 'merges.txt'))
USEFUL = {'config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer.model', 'tokenizer_config.json',
          'special_tokens_map.json', 'added_tokens.json', 'vocab.json', 'merges.txt', 'chat_template.jinja',
          'chat_template.json', 'model.safetensors.index.json', 'preprocessor_config.json'}
CHUNK = 1024 * 1024
GIB = 1024 ** 3


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def plan(names, shards_from_index=None) -> dict:
    """What a trainer needs from a file list: config, a tokenizer, and every Safetensors shard."""
    names = set(names)
    weights = sorted(n for n in names if n.endswith('.safetensors'))
    shards = sorted(set(shards_from_index or []))
    missing = [] if 'config.json' in names else ['config.json']
    if not any(all(part in names for part in group) for group in TOKENIZER_SETS):
        missing.append('tokenizer.json (or tokenizer.model)')
    if not weights:
        missing.append('*.safetensors weights')
    missing += [shard for shard in shards if shard not in names]
    notes = []
    if not weights and any(n.endswith('.gguf') for n in names):
        notes.append({'code': 'GGUF_ONLY', 'message': 'This repository holds GGUF files: they run in llama.cpp for inference, '
                      'but they are not a training checkpoint. Use the matching Safetensors repository for training.'})
    if not weights and any(n.endswith(('.bin', '.pt', '.pth')) for n in names):
        notes.append({'code': 'PICKLE_WEIGHTS', 'message': 'Only PyTorch pickle weights (.bin/.pt) are published; loading them can run code, '
                      'so NajdiLab does not download them. Choose a Safetensors repository.'})
    return {'complete': not missing, 'missing': missing, 'weights': weights, 'notes': notes}


def _safe_dir_name(repo_id: str, revision: str) -> tuple[str, str]:
    return repo_id.replace('/', '--'), revision


class TrainingModels:
    def __init__(self, hub, root=None, *, disk_usage=shutil.disk_usage, reserve_bytes=None, cache_roots=None):
        self.hub = hub
        self.root = Path(root) if root else DATA_DIR / 'training-models'
        self.disk_usage = disk_usage
        self.reserve = int(float(os.environ.get('NAJDILAB_DOWNLOAD_RESERVE_GIB', '2')) * GIB) if reserve_bytes is None else reserve_bytes
        self.cache_roots = cache_roots
        self._lock = threading.Lock()
        self.job = None

    # ----- inspect ---------------------------------------------------------------
    def inspect(self, repo_id, revision=None):
        try:
            info = self.hub.files(repo_id, revision)
            index = self._index(info)
        except HubError as error:
            raise IntegrationError(error.code, str(error), error.status) from None
        names = [f['name'] for f in info['files']]
        layout = plan(names, index)
        wanted = [f for f in info['files'] if f['name'] in USEFUL or f['name'].endswith('.safetensors')
                  or (f['name'].upper().startswith(('LICENSE', 'NOTICE')) and TRAINING_NAME.fullmatch(f['name']))]
        unverifiable = [f['name'] for f in wanted if not f['sha256'] and not f['git_blob']]
        notes = list(layout['notes'])
        lowered = repo_id.lower()
        if 'bnb-4bit' in lowered or '4bit' in lowered:
            notes.append({'code': 'PREQUANTIZED_4BIT', 'message': 'A pre-quantized 4-bit (bitsandbytes) checkpoint: meant for QLoRA in Unsloth on an NVIDIA GPU.'})
        blocked = None
        if info['access'] != 'OPEN' or info['private'] or info['disabled']:
            blocked = 'This repository needs an account and license approval on Hugging Face. NajdiLab does not bypass that.'
        elif not layout['complete']:
            blocked = 'This revision does not contain a complete training checkpoint: ' + ', '.join(layout['missing']) + '.'
        elif unverifiable:
            blocked = 'Hugging Face publishes no hash for: ' + ', '.join(unverifiable[:5]) + '.'
        return {'repo_id': repo_id, 'revision': info['revision'], 'license': info['license'], 'license_name': info['license_name'],
                'license_link': info['license_link'], 'access': info['access'], 'base_models': info['base_models'],
                'files': [{k: f[k] for k in ('name', 'size_bytes')} for f in wanted],
                'total_bytes': sum(f['size_bytes'] or 0 for f in wanted), 'weights': layout['weights'],
                'complete': layout['complete'], 'missing': layout['missing'], 'notes': notes,
                'downloadable': blocked is None, 'blocked_reason': blocked,
                'already_present': (self.root.joinpath(*_safe_dir_name(repo_id, info['revision'])) / MANIFEST).is_file()}

    def _index(self, info):
        if not any(f['name'] == 'model.safetensors.index.json' for f in info['files']):
            return None
        response = self.hub.open_file(info['id'], info['revision'], 'model.safetensors.index.json', names=TRAINING_NAME)
        try:
            raw = response.body.read(4 * 1024 * 1024 + 1)
        finally:
            response.close()
        if len(raw) > 4 * 1024 * 1024:
            raise HubError('INDEX_TOO_LARGE', 'The weight index is unexpectedly large; nothing was downloaded.', 409)
        try:
            weight_map = json.loads(raw)['weight_map']
        except (ValueError, KeyError, TypeError):
            raise HubError('INDEX_INVALID', 'The weight index is not valid JSON; nothing was downloaded.', 409) from None
        shards = {v for v in weight_map.values() if isinstance(v, str)}
        if not all(TRAINING_NAME.fullmatch(s) and s.endswith('.safetensors') for s in shards):
            raise HubError('INDEX_INVALID', 'The weight index names files outside the repository folder; nothing was downloaded.', 409)
        return sorted(shards)

    # ----- download --------------------------------------------------------------
    def start(self, data, *, wait=False):
        if not isinstance(data, dict) or set(data) != {'approved', 'license_acknowledged', 'repo_id', 'revision'}:
            raise IntegrationError('INVALID_PAYLOAD', 'Choose a repository and its reviewed revision.')
        if data['license_acknowledged'] is not True:
            raise IntegrationError('LICENSE_ACKNOWLEDGEMENT_REQUIRED', "Review this model's license and confirm it before downloading.", 403)
        if data['approved'] is not True:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve this download first.', 403)
        repo_id, revision = data['repo_id'], data['revision']
        if not (isinstance(repo_id, str) and REPO_ID.fullmatch(repo_id) and isinstance(revision, str) and COMMIT.fullmatch(revision)):
            raise IntegrationError('INVALID_REPOSITORY', 'Choose a repository and a full 40-character revision.')
        review = self.inspect(repo_id, revision)
        if not review['downloadable']:
            raise IntegrationError('NOT_DOWNLOADABLE', review['blocked_reason'], 409)
        final = self.root.joinpath(*_safe_dir_name(repo_id, revision))
        if final.exists():
            raise IntegrationError('ALREADY_PRESENT', 'This training model revision is already downloaded; NajdiLab never replaces it.', 409)
        files = [f for f in self.hub.files(repo_id, revision)['files'] if f['name'] in {x['name'] for x in review['files']}]
        staging = self.root / f'.staging-{_safe_dir_name(repo_id, revision)[0]}-{revision[:12]}'
        done = sum((staging / f['name']).stat().st_size for f in files if (staging / f['name']).is_file())
        if self.disk_usage(self._existing()).free < self.reserve + review['total_bytes'] - done:
            raise IntegrationError('INSUFFICIENT_SPACE', 'Not enough free space for this checkpoint plus the safety reserve; nothing was downloaded.', 409)
        with self._lock:
            if self.job and self.job['state'] == 'DOWNLOADING':
                raise IntegrationError('DOWNLOADS_BUSY', 'A training model is already downloading. Wait for it or cancel it.', 409)
            self.job = {'repo_id': repo_id, 'revision': revision, 'state': 'DOWNLOADING', 'file': None, 'done_bytes': done,
                        'total_bytes': review['total_bytes'], 'error': None, 'started_at': utc_now(), 'cancel': threading.Event()}
            job = self.job
        thread = threading.Thread(target=self._run, args=(job, review, files, staging, final), daemon=True)
        thread.start()
        if wait:
            thread.join()
        return self.public_job()

    def _existing(self):
        path = self.root
        while not path.exists():
            path = path.parent
        return path

    def cancel(self):
        if not self.job or self.job['state'] != 'DOWNLOADING':
            raise IntegrationError('NOTHING_TO_CANCEL', 'No training model is downloading.', 409)
        self.job['cancel'].set()
        return self.public_job()

    def public_job(self):
        return None if self.job is None else {k: v for k, v in self.job.items() if k != 'cancel'}

    def _run(self, job, review, files, staging, final):
        try:
            staging.mkdir(parents=True, exist_ok=True)
            for item in files:
                job['file'] = item['name']
                self._fetch(job, review, item, staging)
            manifest = {'schema_version': 1, 'kind': 'training_checkpoint', 'repo_id': review['repo_id'], 'revision': review['revision'],
                        'license': review['license'], 'license_name': review['license_name'], 'license_link': review['license_link'],
                        'files': [{'name': f['name'], 'size_bytes': f['size_bytes'], 'sha256': f['sha256'], 'git_blob': f['git_blob']} for f in files],
                        'total_bytes': review['total_bytes'], 'verified_at': utc_now(), 'source': 'huggingface.co'}
            (staging / MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
            final.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staging, final)  # refuses to replace an existing folder
            job.update(state='READY', file=None)
        except IntegrationError as error:
            job.update(state='CANCELLED' if error.code == 'CANCELLED' else 'ERROR', error={'code': error.code, 'message': str(error)})
        except HubError as error:
            job.update(state='ERROR', error={'code': error.code, 'message': str(error)})
        except OSError as error:
            job.update(state='ERROR', error={'code': 'STORAGE_ERROR', 'message': f'Saving the checkpoint failed: {error.strerror or error}.'})

    def _fetch(self, job, review, item, staging):
        target, part = staging / item['name'], staging / (item['name'] + '.part')
        if target.is_file():
            return  # verified in an earlier attempt
        offset = part.stat().st_size if part.is_file() else 0
        if item['size_bytes'] is not None and offset >= item['size_bytes']:
            part.unlink()
            offset = 0
        response = self.hub.open_file(review['repo_id'], review['revision'], item['name'], start=offset,
                                      expected_size=item['size_bytes'], expected_sha256=item['sha256'], names=TRAINING_NAME)
        try:
            with part.open('ab' if offset else 'wb') as out:
                while True:
                    if job['cancel'].is_set():
                        raise IntegrationError('CANCELLED', 'Download cancelled. The verified files are kept so it can resume.', 409)
                    try:
                        block = response.body.read(CHUNK)
                    except OSError:
                        raise IntegrationError('DOWNLOAD_INTERRUPTED', 'The connection was lost. Start the download again to resume it.', 502) from None
                    if not block:
                        break
                    out.write(block)
                    job['done_bytes'] += len(block)
        finally:
            response.close()
        data_hash = hashlib.sha256() if item['sha256'] else None
        size = 0
        with part.open('rb') as handle:
            if data_hash:
                for block in iter(lambda: handle.read(CHUNK), b''):
                    data_hash.update(block)
                    size += len(block)
                ok = data_hash.hexdigest() == item['sha256']
            else:
                raw = handle.read()
                size = len(raw)
                ok = git_blob_sha1(raw) == item['git_blob']
        if not ok or (item['size_bytes'] is not None and size != item['size_bytes']):
            part.unlink(missing_ok=True)
            raise IntegrationError('DIGEST_MISMATCH', f"{item['name']} does not match the hash Hugging Face publishes; it was discarded.", 409)
        os.replace(part, target)

    # ----- local -----------------------------------------------------------------
    def library(self):
        own = []
        if self.root.is_dir():
            for manifest in sorted(self.root.glob(f'*/*/{MANIFEST}')):
                try:
                    data = json.loads(manifest.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                folder = manifest.parent
                present = {p.name: p.stat().st_size for p in folder.iterdir() if p.is_file()}
                intact = all(present.get(f['name']) == f['size_bytes'] for f in data.get('files', []))
                own.append({'repo_id': data.get('repo_id'), 'revision': data.get('revision'), 'license': data.get('license'),
                            'total_bytes': data.get('total_bytes'), 'verified_at': data.get('verified_at'), 'path': str(folder),
                            'source': 'najdilab', 'status': 'READY' if intact else 'CHANGED',
                            **{k: v for k, v in plan(present).items() if k in ('complete', 'missing')}})
        return {'models': own, 'cache': self.cache(), 'job': self.public_job(), 'root': str(self.root),
                'note': 'Training happens outside NajdiLab (for example in Unsloth Studio). Inference models (GGUF) are listed in Downloads and library.'}

    def _cache_roots(self):
        if self.cache_roots is not None:
            return [Path(p) for p in self.cache_roots]
        roots = []
        if os.environ.get('HF_HUB_CACHE'):
            roots.append(Path(os.environ['HF_HUB_CACHE']))
        if os.environ.get('HF_HOME'):
            roots.append(Path(os.environ['HF_HOME']) / 'hub')
        roots.append(Path.home() / '.cache' / 'huggingface' / 'hub')
        return list(dict.fromkeys(roots))

    def cache(self):
        """Checkpoints already in the Hugging Face cache, read-only: names and sizes only, no file is opened."""
        found = []
        for root in self._cache_roots():
            if not root.is_dir():
                continue
            for repo in sorted(root.glob('models--*--*')):
                repo_id = repo.name[len('models--'):].replace('--', '/', 1)
                if not REPO_ID.fullmatch(repo_id):
                    continue
                for snapshot in sorted((repo / 'snapshots').glob('*')):
                    if not snapshot.is_dir() or not COMMIT.fullmatch(snapshot.name):
                        continue
                    files = {}
                    for path in snapshot.iterdir():
                        try:
                            files[path.name] = path.stat().st_size
                        except OSError:
                            continue
                    layout = plan(files)
                    if not layout['weights'] and not any(n.endswith('.gguf') for n in files):
                        continue
                    found.append({'repo_id': repo_id, 'revision': snapshot.name, 'path': str(snapshot), 'source': 'huggingface_cache',
                                  'total_bytes': sum(files.values()), 'complete': layout['complete'], 'missing': layout['missing'],
                                  'notes': layout['notes'], 'status': 'READ_ONLY'})
        return found
