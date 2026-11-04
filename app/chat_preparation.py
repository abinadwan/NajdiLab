"""One path from a composer choice to a chat-ready runtime (Chat V2 composer).

The composer offers a model and a context; this module is the only place that turns that choice
into a runtime that can answer (docs/development/CHAT_COMPOSER.md):

- models(): every model the composer may offer, from approved local runtimes only, with its
  verification state and whether it is loaded and at which context. Nothing is downloaded.
- prepare(): checks a choice against what is running. Without approval it only explains what is
  needed (start, restart at another context, select or load in LM Studio / Ollama). With approval
  it checks memory with the Smart Model Advisor and starts or restarts NajdiLab Native (only the
  process NajdiLab owns, never while a reply holds it) or selects the model in LM Studio / Ollama.

The conversation itself is still created and admitted by ChatWorkspace with all exact checks
(context ceiling, model identity, ENGINE_CONTEXT_MISMATCH, CONTEXT_SHRANK, consent); nothing here
relaxes them.
"""
from __future__ import annotations

import re
import threading

from .hardware import snapshot as hardware_snapshot
from .integrations import IntegrationError
from .model_advisor import assess, host_profile

CONTEXTS = (4096, 8192, 16384, 32768)
GPU_CHOICES = ('auto', 'all', '0')
EXTERNAL = ('lmstudio', 'ollama')
FIELDS = {'provider', 'model', 'context_budget', 'reply_reserve', 'gpu_layers', 'approved', 'new_session'}


def short_label(model_id: str, repo: str | None = None, quantization: str | None = None) -> str:
    """A readable name: the repository name (or file name) without the GGUF suffix, plus the quantization."""
    base = repo.split('/')[-1] if repo else model_id.rsplit('/', 1)[-1]
    base = re.sub(r'(?i)[-_.]?gguf$', '', re.sub(r'(?i)\.gguf$', '', base))
    if quantization and quantization.lower() not in base.lower():
        return f'{base} · {quantization}'
    return base


class ChatPreparation:
    def __init__(self, native, integrations, library=lambda: None, snapshot=hardware_snapshot):
        # `integrations` and `library` are callables so the server (or a test fixture) can replace them.
        self.native, self.integrations, self.library, self.snapshot = native, integrations, library, snapshot
        self._lock = threading.Lock()

    # ----- what the composer may offer ----------------------------------------
    def _managed(self):
        store = self.library()
        if store is None:
            return {}
        return {row['native_id']: row for row in store.library()['items'] if row.get('native_id')}

    def models(self):
        running = self.native.running()
        managed = self._managed()
        server = self.native.server_path.is_file()
        items = []
        for item in self.native.models()['items']:
            row = managed.get(item['id'])
            verification = ('VERIFIED' if row['status'] == 'READY' else 'UNVERIFIED') if row else 'LOCAL'
            loaded = running is not None and running['model'] == item['id']
            reason = (None if item['valid'] and verification != 'UNVERIFIED' and server else
                      'NATIVE_SERVER_MISSING' if not server else item['error'] or 'MODEL_NOT_VERIFIED')
            items.append({'provider': 'native', 'model': item['id'],
                          'label': short_label(item['id'], row and row.get('repo_id'), item.get('quantization')),
                          'quantization': item.get('quantization'), 'architecture': item.get('architecture'),
                          'max_context': item.get('model_max_context'), 'size_bytes': item.get('size_bytes'),
                          'verification': verification, 'sha256': row and row.get('verified_sha256'),
                          'repo_id': row and row.get('repo_id'), 'available': reason is None, 'reason': reason,
                          'state': 'RUNNING' if loaded else 'READY' if reason is None else 'UNAVAILABLE',
                          'loaded_context': running['context'] if loaded else None})
        for state in self.integrations().snapshot()['items']:
            if state['kind'] != 'model_runtime' or state['connection'] != 'CONNECTED':
                continue
            for model in state['models']:
                items.append({'provider': state['id'], 'model': model, 'label': model, 'verification': 'RUNTIME',
                              'available': True, 'reason': None, 'max_context': None,
                              'state': 'SELECTED' if state['selected_model'] == model else 'AVAILABLE',
                              'loaded_context': None})
        native_state, last_error, model, revision = self.native.brief()
        return {'items': items, 'contexts': list(CONTEXTS),
                'native': {'state': native_state, 'model': model, 'revision': revision, 'server_available': server,
                           'context': running['context'] if running else None,
                           'gpu_layers': running['gpu_layers'] if running else None,
                           'busy': bool(running and running['leased']), 'last_error': last_error}}

    # ----- preparation ---------------------------------------------------------
    def prepare(self, data):
        if not isinstance(data, dict) or not set(data) <= FIELDS or not {'provider', 'model', 'context_budget', 'reply_reserve'} <= set(data):
            raise IntegrationError('INVALID_PAYLOAD', 'Choose a model and a context first.')
        provider, model = data['provider'], data['model']
        context, reserve = data['context_budget'], data['reply_reserve']
        layers = data.get('gpu_layers', 'auto')
        approved, new_session = data.get('approved', False), data.get('new_session', True)
        if type(context) is not int or not 128 <= context <= 1048576:
            raise IntegrationError('INVALID_LIMIT', 'Choose a context between 128 and 1048576 tokens.')
        if type(reserve) is not int or not 1 <= reserve <= min(8192, context - 1):
            raise IntegrationError('INVALID_LIMIT', 'Reply space must be between 1 and 8192 tokens and smaller than the total context.')
        if layers not in GPU_CHOICES or type(approved) is not bool or type(new_session) is not bool:
            raise IntegrationError('INVALID_PAYLOAD', 'GPU use must be Automatic, All layers on GPU or CPU only.')
        if not isinstance(model, str) or not model:
            raise IntegrationError('INVALID_PAYLOAD', 'Choose a model first.')
        base = {'provider': provider, 'model': model, 'context_budget': context, 'reply_reserve': reserve, 'gpu_layers': layers}
        if provider == 'native':
            return {**base, **self._native(model, context, layers, approved)}
        if provider in EXTERNAL:
            return {**base, **self._external(provider, model, approved, new_session)}
        raise IntegrationError('UNKNOWN_PROVIDER', 'Choose an approved local runtime.')

    def _native(self, model, context, layers, approved):
        if not self.native.server_path.is_file():
            return {'state': 'BLOCKED', 'code': 'NATIVE_SERVER_MISSING',
                    'message': 'No llama.cpp runtime is installed. Install it in Model library → llama.cpp runtime, or set NAJDILAB_NATIVE_SERVER to your own llama-server.'}
        path = self.native._resolve(model)
        item = self.native.inspect(path)
        if not item['valid']:
            return {'state': 'BLOCKED', 'code': 'NATIVE_MODEL_INVALID', 'message': 'This file is not a usable GGUF text model.'}
        if context > item['model_max_context']:
            return {'state': 'BLOCKED', 'code': 'ENGINE_CONTEXT_LIMIT',
                    'message': f"This model allows at most {item['model_max_context']} tokens of context."}
        if self.native.start_gate is not None:
            self.native.start_gate(path)  # managed runtime exact, managed model verified READY
        running = self.native.running()
        if running and running['model'] == model and running['context'] == context:
            return {'state': 'READY', 'selection_revision': running['revision'], 'running': running}
        action = 'RESTART' if running else 'START'
        if running and running['leased']:
            return {'state': 'BUSY', 'code': 'NATIVE_BUSY', 'running': running,
                    'message': 'A reply is running in NajdiLab Native. Wait for it to finish or stop it first.'}
        explain = ('NajdiLab Native is stopped.' if not running else
                   'NajdiLab Native is running this model at a different context.' if running['model'] == model else
                   'NajdiLab Native is running a different model.')
        if not approved:
            return {'state': f'NEEDS_{action}', 'running': running, 'message': explain,
                    'model_max_context': item['model_max_context'], 'size_bytes': item['size_bytes']}
        if not self._lock.acquire(blocking=False):
            raise IntegrationError('RUNTIME_PREPARING', 'NajdiLab Native is already being prepared. Wait a moment.', 409)
        try:
            if running:
                # Restart only NajdiLab's own child; Native refuses (NATIVE_BUSY) while a reply holds it.
                self.native.stop({'approved': True})
            advice = assess(variant={'filename': item['file'], 'size_bytes': item['size_bytes'], 'quantization': item['quantization'],
                                     'supported': True, 'unsupported_reasons': []},
                            access='OPEN', model=item, host=host_profile(self.snapshot(), self.native.status()),
                            context=context, gpu_layers=layers)
            summary = {'classification': advice['load']['classification'], 'reasons': advice['load']['reasons'][:3],
                       'placement': advice['performance']['placement'], 'expectation': advice['performance']['expectation'],
                       'estimate_bytes': (advice['estimate'] or {}).get('required_bytes')}
            if summary['classification'] == 'BLOCKED':
                return {'state': 'BLOCKED', 'code': 'DOES_NOT_FIT', 'advice': summary, 'stopped_previous': bool(running),
                        'message': advice['load']['reasons'][0]['message'] if advice['load']['reasons'] else 'This model cannot be loaded here.'}
            self.native.start({'approved': True, 'model': model, 'context_budget': context, 'gpu_layers': layers})
            now = self.native.running()
            return {'state': 'READY', 'selection_revision': now['revision'], 'running': now, 'advice': summary,
                    'action': action, 'stopped_previous': bool(running)}
        finally:
            self._lock.release()

    def _external(self, provider, model, approved, new_session):
        state = next((s for s in self.integrations().snapshot()['items'] if s['id'] == provider), None)
        name = {'lmstudio': 'LM Studio', 'ollama': 'Ollama'}[provider]
        if not state or state['connection'] != 'CONNECTED':
            return {'state': 'BLOCKED', 'code': 'NOT_CONNECTED', 'message': f'Connect {name} in Settings → Integrations first.'}
        if model not in state['models']:
            return {'state': 'BLOCKED', 'code': 'MODEL_UNAVAILABLE', 'message': f'{name} does not list this model any more.'}
        needs_select = state['selected_model'] != model
        needs_load = provider == 'ollama' and new_session  # Ollama loads on request: each new chat asks first.
        if (needs_select or needs_load) and not approved:
            return {'state': 'NEEDS_APPROVAL', 'needs_select': needs_select, 'needs_load': needs_load,
                    'message': ('Ollama will load or reload this model at this context size, which takes time and memory.' if needs_load
                                else 'LM Studio must already have this model loaded; NajdiLab will select it for chat.')}
        if needs_select:
            snapshot = self.integrations().action(provider, 'select', {'approved': True, 'model': model})
            state = next(s for s in snapshot['items'] if s['id'] == provider)
        return {'state': 'READY', 'selection_revision': state['selection_revision'], 'load_approved': provider == 'ollama' and new_session}
