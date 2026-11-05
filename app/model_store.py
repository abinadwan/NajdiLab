"""Managed GGUF downloads for Hugging Face Direct: storage safety, integrity and the local registry.

Rules (docs/development/HUGGING_FACE_DIRECT.md §5):
- Files live only in `<NajdiLab Native models folder>/huggingface/<owner>--<name>/<revision12>/<file>.gguf`.
  Nothing outside that folder is listed, changed or deleted; Ollama and LM Studio folders are never read.
- A download starts only after explicit approval and license acknowledgement, at a pinned revision,
  with the size and SHA-256 published for that revision.
- Storage: the destination's own volume is measured; the bytes still to write, a safety reserve
  (larger on the system volume) and the bytes reserved by other active downloads on that volume must
  all fit. Bytes go to `<file>.part` beside the final file, so finalisation is an atomic rename on the
  same volume and no second copy is ever needed. Free space is re-measured during the transfer and
  the download pauses safely before the reserve is reached. Nothing is ever deleted to make room.
- READY requires the exact size and SHA-256 and a readable GGUF text-model header. Anything less is
  UNVERIFIED or ERROR, and NajdiLab Native refuses to start a managed file that is not READY.
"""
from __future__ import annotations

import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import threading
import time
from uuid import uuid4

from .db import connect, transaction, utc_now
from .gguf import GGUFError, describe, read_header
from .hf_hub import COMMIT, GGUF_NAME, REPO_ID, HubError
from .integrations import IntegrationError

GIB = 1024 ** 3
SIDECAR_BYTES = 64 * 1024
MAX_ACTIVE = 2
CHUNK = 1024 * 1024
CHECK_EVERY = 32 * 1024 * 1024


def _gib_env(name, default):
    try:
        value = float(os.environ.get(name, default))
    except ValueError:
        value = float(default)
    return int(max(value, 0) * GIB)


def nearest_existing(path: Path) -> Path:
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def volume_of(path: Path) -> dict:
    """The filesystem holding `path` (or its nearest existing parent), and whether it is the OS volume."""
    existing = nearest_existing(path).resolve()
    stat = os.stat(existing)
    if os.name == 'nt':
        drive = os.path.splitdrive(str(existing))[0] or str(existing.anchor)
        system = drive.upper() == os.environ.get('SystemDrive', 'C:').upper()
        label = drive
    else:
        system = stat.st_dev == os.stat('/').st_dev
        label = str(existing)
    return {'id': stat.st_dev, 'label': label, 'system_volume': system, 'measured_at': str(existing)}


def _no_link_escape(path: Path):
    for part in [path, *path.parents]:
        if part.exists() and (part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction())):
            raise IntegrationError('PATH_REFUSED', 'A folder in the download path is a link; NajdiLab only writes to plain folders.', 409)


class _Job:
    def __init__(self, row, volume):
        self.id, self.row, self.volume = row['id'], row, volume
        self.downloaded = row['downloaded_bytes']
        self.cancel, self.pause = threading.Event(), threading.Event()
        self.speed = None
        self.started = time.monotonic()
        self.thread = None

    @property
    def remaining(self):
        return max(self.row['size_bytes'] - self.downloaded, 0)


class ModelStore:
    def __init__(self, db_path, root, hub, *, disk_usage=shutil.disk_usage, reserve_bytes=None,
                 system_reserve_bytes=None, max_active=MAX_ACTIVE, chunk=CHUNK, check_every=CHECK_EVERY, in_use=None):
        self.db_path = db_path
        self.root = Path(root)
        self.hub = hub
        self.disk_usage = disk_usage
        self.reserve = _gib_env('NAJDILAB_DOWNLOAD_RESERVE_GIB', 2) if reserve_bytes is None else reserve_bytes
        self.system_reserve = _gib_env('NAJDILAB_SYSTEM_RESERVE_GIB', 10) if system_reserve_bytes is None else system_reserve_bytes
        self.max_active, self.chunk, self.check_every = max_active, chunk, check_every
        self.in_use = in_use or (lambda path: False)
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        with connect(self.db_path) as conn:
            # A download cannot survive a restart; its verified prefix stays for an explicit resume.
            conn.execute("UPDATE managed_models SET status='PAUSED',error_code='INTERRUPTED',updated_at=? WHERE status='DOWNLOADING'",
                         (utc_now(),))

    # ----- paths ---------------------------------------------------------
    def _root(self):
        _no_link_escape(self.root)
        return self.root.resolve() if self.root.exists() else self.root.absolute()

    def _relative(self, repo_id, revision, filename):
        owner, name = repo_id.split('/')
        return f'{owner}--{name}/{revision[:12]}/{filename}'

    def _path(self, relative):
        root = self._root()
        path = (root / relative)
        try:
            path.resolve().relative_to(root.resolve() if root.exists() else root)
        except ValueError:
            raise IntegrationError('PATH_REFUSED', 'The file path would leave the managed models folder.', 409) from None
        _no_link_escape(path.parent)
        return path

    # ----- storage -------------------------------------------------------
    def _reserve_for(self, volume):
        return max(self.reserve, self.system_reserve) if volume['system_volume'] else self.reserve

    def preflight(self, size_bytes, already_bytes=0, exclude=None):
        """Storage decision for writing `size_bytes - already_bytes` more bytes into the managed folder."""
        if type(size_bytes) is not int or size_bytes <= 0:
            return {'decision': 'BLOCKED', 'reasons': [{'code': 'SIZE_UNKNOWN', 'message': 'Hugging Face did not publish a size for this file, so safe space cannot be shown.'}]}
        volume = volume_of(self.root)
        usage = self.disk_usage(volume['measured_at'])
        reserve = self._reserve_for(volume)
        with self._lock:
            others = sum(j.remaining for j in self._jobs.values() if j.volume['id'] == volume['id'] and j.id != exclude)
        to_write = max(size_bytes - already_bytes, 0)
        required = to_write + SIDECAR_BYTES + reserve + others
        after = usage.free - others - to_write
        reasons = []
        if usage.free < required:
            reasons.append({'code': 'INSUFFICIENT_SPACE',
                            'message': 'Not enough free space on this drive for the file, the safety reserve and other downloads in progress.'})
        return {'decision': 'BLOCKED' if reasons else 'ALLOWED', 'reasons': reasons,
                'destination': str(self.root), 'volume': volume['label'], 'system_volume': volume['system_volume'],
                'total_bytes': usage.total, 'free_bytes': usage.free, 'file_bytes': size_bytes,
                'already_downloaded_bytes': already_bytes, 'to_write_bytes': to_write,
                # The .part file sits next to the final file on the same volume; finalising is a rename.
                'temporary_bytes': to_write + SIDECAR_BYTES, 'reserve_bytes': reserve,
                'reserved_by_other_downloads_bytes': others, 'required_bytes': required,
                'free_after_bytes': after, 'measured': 'free space measured now on this drive; it can change while you download'}

    # ----- registry ------------------------------------------------------
    def _rows(self, where='', args=()):
        with connect(self.db_path) as conn:
            return [dict(r) for r in conn.execute(f'SELECT * FROM managed_models {where} ORDER BY created_at DESC', args)]

    def _row(self, model_id):
        rows = self._rows('WHERE id=?', (model_id,)) if isinstance(model_id, str) and len(model_id) <= 64 else []
        if not rows:
            raise IntegrationError('MODEL_NOT_FOUND', 'That model is not in the NajdiLab model library.', 404)
        return rows[0]

    def _update(self, model_id, **values):
        values['updated_at'] = utc_now()
        with connect(self.db_path) as conn:
            conn.execute(f"UPDATE managed_models SET {','.join(f'{k}=?' for k in values)} WHERE id=?", (*values.values(), model_id))

    def library(self):
        rows = self._rows()
        with self._lock:
            for row in rows:
                job = self._jobs.get(row['id'])
                # A finished row is never shown as active, even in the instant before its job is removed.
                row['active'] = job is not None and row['status'] == 'DOWNLOADING'
                if job:
                    row['downloaded_bytes'] = job.downloaded
                    row['speed_bytes_per_second'] = job.speed
                    row['eta_seconds'] = int(job.remaining / job.speed) if job.speed else None
                row['path'] = str(self.root / row['relative_path'])
                row['native_id'] = f"huggingface/{row['relative_path']}"
        return {'root': str(self.root), 'items': rows, 'reserve_bytes': self.reserve, 'system_reserve_bytes': self.system_reserve,
                'storage': self.preflight(1) | {'decision': None, 'reasons': []}}

    # ----- downloads -----------------------------------------------------
    def start(self, data):
        if not isinstance(data, dict) or set(data) != {'approved', 'license_acknowledged', 'repo_id', 'revision', 'filename'}:
            raise IntegrationError('INVALID_PAYLOAD', 'Choose a repository, a pinned revision and a file.')
        if data['license_acknowledged'] is not True:
            raise IntegrationError('LICENSE_ACKNOWLEDGEMENT_REQUIRED', "Review this model's license and confirm it before downloading.", 403)
        if data['approved'] is not True:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve this download first.', 403)
        repo_id, revision, filename = data['repo_id'], data['revision'], data['filename']
        if not (isinstance(repo_id, str) and REPO_ID.fullmatch(repo_id) and isinstance(revision, str) and COMMIT.fullmatch(revision)
                and isinstance(filename, str) and GGUF_NAME.fullmatch(filename)):
            raise IntegrationError('INVALID_FILE', 'Only a top-level .gguf file at a pinned revision can be downloaded.')
        try:
            details = self.hub.model(repo_id, revision)
        except HubError as error:
            raise IntegrationError(error.code, str(error), error.status) from None
        if details['access'] != 'OPEN' or details['private'] or details['disabled']:
            raise IntegrationError('REPOSITORY_GATED', 'This repository needs an account and license approval on Hugging Face. NajdiLab does not bypass that.', 403)
        chosen = next((v for v in details['variants'] if v['filename'] == filename), None)
        if chosen is None:
            raise IntegrationError('FILE_NOT_FOUND', 'That file is not in this revision of the repository.', 404)
        if not chosen['supported']:
            raise IntegrationError('FILE_UNSUPPORTED', 'NajdiLab supports single-file GGUF text models with a published SHA-256 only.', 409)
        relative = self._relative(repo_id, revision, filename)
        final = self._path(relative)
        with self._lock:
            if len(self._jobs) >= self.max_active:
                raise IntegrationError('DOWNLOADS_BUSY', f'At most {self.max_active} downloads run at once. Wait for one to finish.', 409)
            existing = self._rows('WHERE relative_path=?', (relative,))
            if existing:
                raise IntegrationError('ALREADY_IN_LIBRARY', 'This file is already in the model library. Resume or delete it there.', 409)
            if final.exists():
                raise IntegrationError('ALREADY_PRESENT', 'A file already exists at the destination; NajdiLab never replaces it.', 409)
            storage = self.preflight(chosen['size_bytes'])
            if storage['decision'] != 'ALLOWED':
                raise IntegrationError('INSUFFICIENT_SPACE', storage['reasons'][0]['message'], 409)
            now = utc_now()
            row = {'id': uuid4().hex, 'repo_id': repo_id, 'revision': revision, 'filename': filename, 'relative_path': relative,
                   'size_bytes': chosen['size_bytes'], 'expected_sha256': chosen['sha256'], 'verified_sha256': None,
                   'status': 'DOWNLOADING', 'error_code': None, 'license': details['license'], 'architecture': None,
                   'quantization': chosen['quantization'], 'model_max_context': None, 'downloaded_bytes': 0,
                   'created_at': now, 'updated_at': now, 'verified_at': None}
            with connect(self.db_path) as conn, transaction(conn):
                conn.execute(f"INSERT INTO managed_models({','.join(row)}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
            self._launch(row, storage)
        return self._row(row['id'])

    def _launch(self, row, storage):
        job = _Job(row, volume_of(self.root))
        self._jobs[row['id']] = job
        job.thread = threading.Thread(target=self._run, args=(job,), daemon=True, name=f'najdilab-download-{row["id"][:8]}')
        job.thread.start()

    def control(self, model_id, action, data=None):
        row = self._row(model_id)
        if action == 'pause':
            with self._lock:
                job = self._jobs.get(model_id)
            if not job:
                raise IntegrationError('NOT_DOWNLOADING', 'This model is not downloading.', 409)
            job.pause.set()
            job.thread.join(30)
            return self._row(model_id)
        if action == 'cancel':
            with self._lock:
                job = self._jobs.get(model_id)
            if job:
                job.cancel.set()
                job.thread.join(30)
            elif row['status'] not in ('PAUSED', 'ERROR'):
                raise IntegrationError('NOT_CANCELLABLE', 'Only an unfinished download can be cancelled; use Delete for a finished file.', 409)
            self._discard_partial(row)
            with connect(self.db_path) as conn:
                conn.execute('DELETE FROM managed_models WHERE id=? AND status IN (?,?,?)', (model_id, 'PAUSED', 'ERROR', 'DOWNLOADING'))
            return {'cancelled': True, 'id': model_id}
        if action == 'resume':
            if data != {'approved': True}:
                raise IntegrationError('APPROVAL_REQUIRED', 'Approve resuming this download.', 403)
            if row['status'] != 'PAUSED':
                raise IntegrationError('NOT_PAUSED', 'Only a paused download can be resumed.', 409)
            part = self._path(row['relative_path'] + '.part')
            already = part.stat().st_size if part.exists() else 0
            with self._lock:
                if len(self._jobs) >= self.max_active:
                    raise IntegrationError('DOWNLOADS_BUSY', f'At most {self.max_active} downloads run at once.', 409)
                storage = self.preflight(row['size_bytes'], already)
                if storage['decision'] != 'ALLOWED':
                    raise IntegrationError('INSUFFICIENT_SPACE', storage['reasons'][0]['message'], 409)
                self._update(model_id, status='DOWNLOADING', error_code=None)
                self._launch(self._row(model_id), storage)
            return self._row(model_id)
        raise IntegrationError('UNKNOWN_ACTION', 'Unknown download action.', 404)

    def _discard_partial(self, row):
        for suffix in ('.part', '.part.json'):
            path = self._path(row['relative_path'] + suffix)
            if path.is_file() and not path.is_symlink():
                path.unlink()
        self._prune(self._path(row['relative_path']).parent)

    def _prune(self, folder):
        root = self._root()
        while folder != root and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent

    def _finish(self, job, status, code=None, **values):
        # Record the outcome before the job leaves the active list, so no reader ever sees a
        # DOWNLOADING row without a running download.
        self._update(job.id, **{'status': status, 'error_code': code, 'downloaded_bytes': job.downloaded, **values})
        with self._lock:
            self._jobs.pop(job.id, None)

    def _run(self, job):
        row = job.row
        final = self._path(row['relative_path'])
        part = self._path(row['relative_path'] + '.part')
        sidecar = self._path(row['relative_path'] + '.part.json')
        identity = {k: row[k] for k in ('repo_id', 'revision', 'filename', 'size_bytes', 'expected_sha256')}
        digest = hashlib.sha256()
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
            _no_link_escape(final.parent)
            already = 0
            if part.exists():
                # Resume only a prefix that was written for exactly this file; it is hashed again here
                # and the whole file is verified at the end, so a damaged prefix cannot pass.
                try:
                    recorded = json.loads(sidecar.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    recorded = None
                already = part.stat().st_size
                if recorded != identity or already > row['size_bytes']:
                    part.unlink()
                    already = 0
                else:
                    with part.open('rb') as stream:
                        while block := stream.read(8 * 1024 * 1024):
                            digest.update(block)
            sidecar.write_text(json.dumps(identity), encoding='utf-8')
            job.downloaded = already
            if already < row['size_bytes']:
                response = self.hub.open_file(row['repo_id'], row['revision'], row['filename'], start=already,
                                              expected_size=row['size_bytes'], expected_sha256=row['expected_sha256'])
                try:
                    self._transfer(job, response, part, digest)
                finally:
                    response.close()
            if job.cancel.is_set():
                return self._finish(job, 'PAUSED', 'CANCELLED')
            if job.pause.is_set():
                return self._finish(job, 'PAUSED', job.row.get('pause_code') or 'PAUSED_BY_USER')
            if part.stat().st_size != row['size_bytes']:
                self._discard_partial(row)
                return self._finish(job, 'ERROR', 'SIZE_MISMATCH', downloaded_bytes=0)
            actual = digest.hexdigest()
            if actual != row['expected_sha256']:
                self._discard_partial(row)
                return self._finish(job, 'ERROR', 'HASH_MISMATCH', downloaded_bytes=0)
            if final.exists():
                self._discard_partial(row)
                return self._finish(job, 'ERROR', 'ALREADY_PRESENT', downloaded_bytes=0)
            os.replace(part, final)
            sidecar.unlink(missing_ok=True)
            self._finish(job, *self._classify(final), verified_sha256=actual, verified_at=utc_now(), **self._header_values(final))
        except HubError as error:
            self._finish(job, 'PAUSED' if error.code in ('HUB_UNREACHABLE', 'RATE_LIMITED', 'HUB_UNAVAILABLE') else 'ERROR', error.code)
        except IntegrationError as error:
            self._finish(job, 'ERROR', error.code)
        except OSError as error:
            full = error.errno == errno.ENOSPC or getattr(error, 'winerror', None) in (39, 112)
            self._finish(job, 'PAUSED' if full else 'ERROR', 'DISK_FULL' if full else 'WRITE_FAILED')
        except Exception:  # noqa: BLE001 - never leave a job running silently
            self._finish(job, 'ERROR', 'DOWNLOAD_FAILED')

    def _transfer(self, job, response, part, digest):
        row = job.row
        reserve = self._reserve_for(job.volume)
        last_check, window_start, window_bytes = job.downloaded, time.monotonic(), 0
        with part.open('ab') as out:
            while job.downloaded < row['size_bytes']:
                if job.cancel.is_set() or job.pause.is_set():
                    break
                try:
                    block = response.body.read(min(self.chunk, row['size_bytes'] - job.downloaded))
                except (OSError, http.client.HTTPException):
                    # A network failure while reading, not a disk failure: the prefix stays for a resume.
                    raise HubError('HUB_UNREACHABLE', 'The connection to Hugging Face was interrupted.') from None
                if not block:
                    raise HubError('HUB_UNREACHABLE', 'The connection ended before the file was complete.')
                if job.downloaded - last_check >= self.check_every or last_check == job.downloaded:
                    # Free space can shrink while we download (other programs, other downloads).
                    usage = self.disk_usage(job.volume['measured_at'])
                    with self._lock:
                        others = sum(j.remaining for j in self._jobs.values() if j.volume['id'] == job.volume['id'] and j.id != job.id)
                    if usage.free - job.remaining - others < reserve:
                        job.row['pause_code'] = 'STORAGE_RESERVE'
                        job.pause.set()
                        break
                    last_check = job.downloaded
                out.write(block)
                digest.update(block)
                job.downloaded += len(block)
                window_bytes += len(block)
                elapsed = time.monotonic() - window_start
                if elapsed >= 1:
                    job.speed = int(window_bytes / elapsed)
                    window_start, window_bytes = time.monotonic(), 0
            out.flush()
            os.fsync(out.fileno())
        self._update(job.id, downloaded_bytes=job.downloaded)

    # ----- verification and use -------------------------------------------
    def _header_values(self, path):
        try:
            info = describe(read_header(path))
        except (GGUFError, OSError):
            return {}
        return {'architecture': info['architecture'], 'model_max_context': info['model_max_context'],
                'quantization': info['quantization']}

    def _classify(self, path):
        try:
            info = describe(read_header(path))
        except GGUFError as error:
            return 'UNVERIFIED', f'GGUF_{error.code}'
        except OSError:
            return 'ERROR', 'UNREADABLE'
        if info['architecture'] in (None, 'clip'):
            return 'UNVERIFIED', 'NOT_A_TEXT_MODEL'
        if not info['model_max_context']:
            return 'UNVERIFIED', 'CONTEXT_UNKNOWN'
        return 'READY', None

    def recheck(self, model_id):
        row = self._row(model_id)
        if row['status'] not in ('READY', 'UNVERIFIED', 'ERROR') or row['id'] in self._jobs:
            raise IntegrationError('NOT_FINISHED', 'Finish or cancel the download before checking it.', 409)
        path = self._path(row['relative_path'])
        if not path.is_file() or path.is_symlink():
            self._update(model_id, status='ERROR', error_code='MISSING')
            return self._row(model_id)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
        actual = digest.hexdigest()
        if path.stat().st_size != row['size_bytes'] or actual != row['expected_sha256']:
            self._update(model_id, status='ERROR', error_code='HASH_MISMATCH', verified_sha256=actual, verified_at=utc_now())
        else:
            status, code = self._classify(path)
            self._update(model_id, status=status, error_code=code, verified_sha256=actual, verified_at=utc_now(), **self._header_values(path))
        return self._row(model_id)

    def delete_plan(self, model_id):
        """Exactly what deleting this library entry removes, before anything is removed."""
        row = self._row(model_id)
        path = self._path(row['relative_path'])
        files = []
        for candidate, role in ((path, 'model file'), (self._path(row['relative_path'] + '.part'), 'partial download'),
                                (self._path(row['relative_path'] + '.part.json'), 'download progress')):
            if candidate.is_file() and not candidate.is_symlink():
                files.append({'path': str(candidate), 'role': role, 'size_bytes': candidate.stat().st_size})
        complete = any(f['role'] == 'model file' for f in files)
        with self._lock:
            downloading = model_id in self._jobs
        in_use = complete and self.in_use(path)
        blocked = ('DOWNLOAD_ACTIVE' if downloading else 'MODEL_IN_USE' if in_use else None)
        return {'id': model_id, 'filename': row['filename'], 'repo_id': row['repo_id'], 'status': row['status'],
                'action': 'delete_model_file' if complete else 'remove_download_record',
                'files': files, 'frees_bytes': sum(f['size_bytes'] for f in files), 'in_use': in_use,
                'blocked': blocked, 'confirm_text': row['filename'],
                'note': 'Removes the library entry and the files listed; nothing outside the NajdiLab models folder is touched.'}

    def delete(self, model_id, data):
        row = self._row(model_id)
        if not isinstance(data, dict) or data.get('approved') is not True or data.get('confirm') != row['filename'] or set(data) != {'approved', 'confirm'}:
            raise IntegrationError('CONFIRMATION_REQUIRED', 'Type the exact file name to confirm deleting this model.', 403)
        plan = self.delete_plan(model_id)
        if plan['blocked'] == 'DOWNLOAD_ACTIVE':
            raise IntegrationError('DOWNLOAD_ACTIVE', 'Cancel the download before deleting.', 409)
        if plan['blocked'] == 'MODEL_IN_USE':
            raise IntegrationError('MODEL_IN_USE', 'NajdiLab Native is running this model. Stop it first.', 409)
        freed = 0
        for item in plan['files']:  # model file first: if it cannot be removed, the entry stays and can be retried
            try:
                Path(item['path']).unlink(missing_ok=True)
            except OSError as error:
                raise IntegrationError('DELETE_FAILED', f"Could not delete {Path(item['path']).name} ({error.strerror or error}); "
                                       'another program may be using it. The library entry was kept so you can try again.', 409) from None
            freed += item['size_bytes']
        self._prune(self._path(row['relative_path']).parent)
        with connect(self.db_path) as conn:
            conn.execute('DELETE FROM managed_models WHERE id=?', (model_id,))
        return {'deleted': True, 'id': model_id, 'filename': row['filename'], 'action': plan['action'], 'freed_bytes': freed}

    def native_gate(self, path):
        """Called by NajdiLab Native before it starts a file: managed files must be READY."""
        root = self._root()
        try:
            relative = Path(path).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            return  # owner-supplied files outside the managed folder keep their existing rules
        rows = self._rows('WHERE relative_path=?', (relative,))
        if not rows:
            raise IntegrationError('MODEL_NOT_VERIFIED', 'This file is in the Hugging Face folder but not in the model library, so its integrity is unknown.', 409)
        if rows[0]['status'] != 'READY':
            raise IntegrationError('MODEL_NOT_VERIFIED', 'This model has not passed its size and SHA-256 check. Recheck it in the model library first.', 409)

    def shutdown(self):
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            job.pause.set()
        for job in jobs:
            job.thread.join(10)
