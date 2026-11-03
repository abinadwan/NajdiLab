"""HTTP-facing operations of Hugging Face Direct (search, details, advice, downloads, library).

Every operation is an explicit POST from the interface (CSRF-protected like all mutations), so no
page load ever reaches the network by itself. Hugging Face errors become IntegrationError with a
stable code; nothing from chats, datasets or the hardware snapshot is sent to Hugging Face.
"""
from __future__ import annotations

import re

from .hardware import snapshot as hardware_snapshot
from .hf_hub import HubClient, HubError
from .integrations import IntegrationError
from .model_advisor import assess, host_profile
from .model_store import ModelStore
from .gguf import GGUFError, describe, read_header

GPU_CHOICES = {'auto', 'all', '0'}


def _hub_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except HubError as error:
        failure = IntegrationError(error.code, str(error), error.status)
        if error.retry_after:
            failure.hint = f'Retry after about {error.retry_after} seconds.'
        raise failure from None


def _options(data):
    context, layers = data.get('context'), data.get('gpu_layers', 'auto')
    if type(context) is not int or not 512 <= context <= 1048576:
        raise IntegrationError('INVALID_LIMIT', 'Choose a context between 512 and 1048576 tokens.')
    if layers not in GPU_CHOICES:
        raise IntegrationError('INVALID_PAYLOAD', 'GPU use must be Automatic, All layers on GPU or CPU only.')
    if type(data.get('hardware_approved')) is not bool:
        raise IntegrationError('INVALID_PAYLOAD', 'Say whether the local hardware snapshot may be read.')
    return context, layers


class ModelLibrary:
    def __init__(self, db_path, native, *, hub=None, store=None, snapshot=hardware_snapshot):
        self.native = native
        self.hub = hub or HubClient()
        self.store = store or ModelStore(db_path, native.models_dir / 'huggingface', self.hub, in_use=native.serving)
        self.snapshot = snapshot

    def _host(self, approved):
        return host_profile(self.snapshot() if approved else None, self.native.status())

    def handle(self, path, data):
        if path == 'hub/search':
            return _hub_call(self.hub.search, data.get('query', ''), data.get('author', ''))
        if path == 'hub/repo':
            return _hub_call(self.hub.model, data.get('repo_id'), data.get('revision'))
        if path == 'advise':
            return self.advise(data)
        if path == 'downloads':
            return self.store.start(data)
        if match := re.fullmatch(r'library/([a-f0-9]{32})/(pause|resume|cancel|recheck|delete|advise)', path):
            model_id, action = match.groups()
            if action == 'recheck':
                return self.store.recheck(model_id)
            if action == 'delete':
                return self.store.delete(model_id, data)
            if action == 'advise':
                return self.advise_local(model_id, data)
            return self.store.control(model_id, action, data)
        raise IntegrationError('ROUTE_NOT_FOUND', 'Unknown model library action.', 404)

    def advise(self, data):
        context, layers = _options(data)
        details = _hub_call(self.hub.model, data.get('repo_id'), data.get('revision'))
        chosen = next((v for v in details['variants'] if v['filename'] == data.get('filename')), None)
        if chosen is None:
            raise IntegrationError('FILE_NOT_FOUND', 'That file is not in this revision of the repository.', 404)
        model = None
        if chosen['supported'] and details['access'] == 'OPEN':
            model = _hub_call(self.hub.remote_header, details['id'], details['revision'], chosen['filename'],
                              chosen['size_bytes'], chosen['sha256'])
        result = assess(variant=chosen, access=details['access'], model=model, host=self._host(data['hardware_approved']),
                        context=context, gpu_layers=layers, storage=self.store.preflight(chosen['size_bytes']))
        result['file'] = {**chosen, 'repo_id': details['id'], 'revision': details['revision'], 'license': details['license'],
                          'header_source': 'first bytes of the file, read with a bounded Range request' if model else None}
        return result

    def advise_local(self, model_id, data):
        context, layers = _options(data)
        row = self.store._row(model_id)
        path = self.store._path(row['relative_path'])
        try:
            model = describe(read_header(path))
        except (GGUFError, OSError) as error:
            model = {'error': getattr(error, 'code', 'UNREADABLE')}
        variant = {'filename': row['filename'], 'size_bytes': row['size_bytes'], 'quantization': row['quantization'],
                   'supported': True, 'unsupported_reasons': []}
        result = assess(variant=variant, access='OPEN', model=model, host=self._host(data['hardware_approved']),
                        context=context, gpu_layers=layers, storage=None)
        result['download'] = {'decision': 'DONE', 'reasons': [], 'storage': None}
        if row['status'] != 'READY':
            result['load']['classification'] = 'BLOCKED'
            result['load']['reasons'].insert(0, {'code': 'MODEL_NOT_VERIFIED', 'message': 'This file has not passed its size and SHA-256 check.'})
        result['file'] = {**row, 'native_id': f"huggingface/{row['relative_path']}", 'header_source': 'local file'}
        return result
