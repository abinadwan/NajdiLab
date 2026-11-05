"""HTTP-facing operations of Hugging Face Direct (search, details, advice, downloads, library).

Every operation is an explicit POST from the interface (CSRF-protected like all mutations), so no
page load ever reaches the network by itself. Hugging Face errors become IntegrationError with a
stable code; nothing from chats, datasets or the hardware snapshot is sent to Hugging Face.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re

from . import model_discovery as discovery
from .db import utc_now
from .hardware import snapshot as hardware_snapshot
from .hf_hub import CURSOR, HubClient, HubError
from .integrations import IntegrationError
from .model_advisor import assess, host_profile
from .model_store import ModelStore
from .gguf import GGUFError, describe, read_header

GPU_CHOICES = {'auto', 'all', '0'}


def _failure(error):
    failure = IntegrationError(error.code, str(error), error.status)
    if error.retry_after:
        failure.hint = f'Retry after about {error.retry_after} seconds.'
    return failure


def _hub_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except HubError as error:
        raise _failure(error) from None


def _options(data):
    context, layers = data.get('context'), data.get('gpu_layers', 'auto')
    if type(context) is not int or not 512 <= context <= 1048576:
        raise IntegrationError('INVALID_LIMIT', 'Choose a context between 512 and 1048576 tokens.')
    if layers not in GPU_CHOICES:
        raise IntegrationError('INVALID_PAYLOAD', 'GPU use must be Automatic, All layers on GPU or CPU only.')
    if type(data.get('hardware_approved')) is not bool:
        raise IntegrationError('INVALID_PAYLOAD', 'Say whether the local hardware snapshot may be read.')
    return context, layers


def _filters(data, extra):
    allowed = {'size', 'source', 'purpose', 'refresh'} | set(extra)
    if not isinstance(data, dict) or not set(data) <= allowed:
        raise IntegrationError('INVALID_PAYLOAD', 'Unknown discovery option.')
    size, source, purpose = data.get('size', 'all'), data.get('source', 'official'), data.get('purpose', 'chat')
    if size not in discovery.SIZES or source not in discovery.SOURCES or purpose not in discovery.PURPOSES:
        raise IntegrationError('INVALID_PAYLOAD', 'Choose a size, source and purpose from the lists.')
    if type(data.get('refresh', False)) is not bool:
        raise IntegrationError('INVALID_PAYLOAD', 'Refresh must be true or false.')
    return {'size': size, 'source': source, 'purpose': purpose}, data.get('refresh', False)


class ModelLibrary:
    def __init__(self, db_path, native, *, hub=None, store=None, snapshot=hardware_snapshot):
        self.native = native
        self.hub = hub or HubClient()
        self.store = store or ModelStore(db_path, native.models_dir / 'huggingface', self.hub, in_use=native.serving)
        self.snapshot = snapshot
        self.discovery = discovery.Discovery(self.hub)

    def _host(self, approved):
        return host_profile(self.snapshot() if approved else None, self.native.status())

    def handle(self, path, data):
        if path == 'hub/search':
            return _hub_call(self.hub.search, data.get('query', ''), data.get('author', ''))
        if path == 'hub/repo':
            return _hub_call(self.hub.model, data.get('repo_id'), data.get('revision'))
        if path == 'hub/trending':
            return self.trending(data)
        if path == 'hub/recommended':
            return self.recommended(data)
        if path == 'advise':
            return self.advise(data)
        if path == 'downloads':
            return self.store.start(data)
        if match := re.fullmatch(r'library/([a-f0-9]{32})/delete-plan', path):
            return self.store.delete_plan(match.group(1))
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

    def trending(self, data):
        filters, refresh = _filters(data, {'sort', 'include_unknown_size', 'cursor', 'offset'})
        sort, cursor, offset = data.get('sort', 'trending'), data.get('cursor'), data.get('offset', 0)
        if sort not in discovery.SORTS or type(data.get('include_unknown_size', False)) is not bool:
            raise IntegrationError('INVALID_PAYLOAD', 'Choose a ranking from the list.')
        if cursor is not None and not (isinstance(cursor, str) and CURSOR.fullmatch(cursor)):
            raise IntegrationError('INVALID_PAYLOAD', 'The page marker is not valid; start the list again.')
        if type(offset) is not int or not 0 <= offset <= 100000:
            raise IntegrationError('INVALID_PAYLOAD', 'The list position is not valid.')
        return _hub_call(self.discovery.trending, sort=sort, include_unknown_size=data.get('include_unknown_size', False),
                         cursor=cursor, offset=offset, refresh=refresh, **filters)

    def recommended(self, data):
        """Models from Hugging Face's most downloaded and trending lists, ranked by how they fit this computer."""
        filters, refresh = _filters(data, {'context', 'gpu_layers', 'hardware_approved'})
        context, layers = _options(data)
        if data['hardware_approved'] is not True:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve reading this computer\'s hardware to get recommendations (it stays on this computer).', 403)
        candidates, counts, fetched = _hub_call(self.discovery.pool, refresh=refresh, **filters)
        host = self._host(True)

        def facts(candidate):
            details = self.discovery.details(candidate['id'], refresh=refresh)
            variants = [v for v in details['variants'] if v['supported']]
            model = None
            if variants and details['access'] == 'OPEN':
                # One bounded header read per repository: layer sizes are the same for every quantization.
                reference = min(variants, key=lambda v: v['size_bytes'])
                model = self.hub.remote_header(details['id'], details['revision'], reference['filename'],
                                               reference['size_bytes'], reference['sha256'])
            return candidate, details, variants, model

        def attempt(candidate):
            try:
                return facts(candidate)
            except HubError as error:
                return error
        with ThreadPoolExecutor(4) as pool:
            fetched_facts = list(pool.map(attempt, candidates))
        failures = [f for f in fetched_facts if isinstance(f, HubError)]
        if failures and len(failures) == len(fetched_facts):
            raise _failure(failures[0])
        counts['not_checked'] = len(failures)
        items = []
        for candidate, details, variants, model in (f for f in fetched_facts if not isinstance(f, HubError)):
            if not variants:
                continue
            results = [{'variant': v, 'advice': assess(variant=v, access=details['access'], model=model, host=host, context=context,
                                                       gpu_layers=layers, storage=self.store.preflight(v['size_bytes']))}
                       for v in variants]
            best = discovery.best_variant(results)
            advice = best['advice']
            items.append({**candidate, 'revision': details['revision'], 'license': details['license'] or candidate['license'],
                          'chosen': {k: best['variant'][k] for k in ('filename', 'size_bytes', 'quantization', 'sha256')},
                          'variants_checked': len(results), 'advice': {k: advice[k] for k in ('load', 'performance', 'download', 'estimate')},
                          'compatibility': advice['load']['classification'], 'performance': advice['performance']['expectation']})
        items.sort(key=discovery.rank_key)
        return {'items': items, 'counts': counts, 'fetched_at': fetched, 'checked_at': utc_now(), 'context': context, 'gpu_layers': layers,
                'host': {'gpus': host['gpus'], 'ram_available_bytes': host['ram_available_bytes'], 'runtime': host['runtime']},
                'method': ('Popularity only chooses which models are checked (Hugging Face\'s most downloaded and trending GGUF models). '
                           'The order comes from the Smart Model Advisor on this computer: compatibility first, then provenance, '
                           'license and where the model would run.'),
                'note': 'Compatibility is a memory estimate, not a load test; performance is an expectation, not a benchmark.'}

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
