"""NajdiLab Native: one NajdiLab-owned llama.cpp `llama-server` child process.

Boundaries (docs/native-runtime.md):
- NajdiLab never downloads binaries or weights. The owner points it at an
  existing `llama-server` (NAJDILAB_NATIVE_SERVER) and a folder of local GGUF
  files (NAJDILAB_NATIVE_MODELS, default data/models).
- The child listens on 127.0.0.1 only, on a free port, with a per-start random
  API key, `--offline`, no web UI, no slots/props endpoints and no context
  shift. NajdiLab only ever stops the process it started.
- Admission is exact: the server's own template and tokenizer count the
  prompt, the loaded context must equal the session budget, and the final
  usage must match the measured prompt. Identity is the file's SHA-256 plus an
  unchanged size/mtime and the same running instance.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time

from .chat_engine import CHAT_DEADLINE, MAX_REPLY_BYTES, STREAM_LIMIT, StreamCollector, ms, open_engine
from .db import DATA_DIR, utc_now
from .gguf import GGUFError, describe, read_header
from .integrations import Connector, IntegrationError, request_json, request_stream

NAME = 'NajdiLab Native'
START_TIMEOUT = 180
GPU_LAYERS = re.compile(r'(?:auto|all|0|[1-9][0-9]{0,3})\Z')
SPLIT = re.compile(r'-\d{5}-of-\d{5}\.gguf\Z', re.IGNORECASE)
MAX_MODELS = 500
# Classified startup failures. Raw server output never reaches the UI or logs.
START_FAILURES = (
    (re.compile(rb'out of memory|failed to allocate|cudaMalloc|ErrorOutOfDeviceMemory', re.I), 'NATIVE_OUT_OF_MEMORY',
     'The model did not fit in memory at this context or GPU setting. Try a smaller context or fewer GPU layers.'),
    (re.compile(rb'unknown model architecture|unsupported model|failed to load model|error loading model', re.I), 'NATIVE_MODEL_UNSUPPORTED',
     'This llama-server build could not load the model file.'),
    (re.compile(rb'couldn\'t bind|address already in use', re.I), 'NATIVE_PORT_UNAVAILABLE',
     'The local port was taken before the server started. Try again.'),
)


def _env_path(name, default=None):
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def default_server_path():
    explicit = _env_path('NAJDILAB_NATIVE_SERVER')
    if explicit:
        return explicit
    exe = 'llama-server.exe' if os.name == 'nt' else 'llama-server'
    return DATA_DIR / 'native' / 'bin' / exe


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def file_stat(path):
    # Size, modification time and file id (inode / NTFS file index): replacing the
    # file, even with a copied mtime, changes the identity (review F3).
    value = path.stat()
    return (value.st_size, value.st_mtime_ns, value.st_ino)


def sha256_file(path, chunk=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def process_vram(pid):
    """Measured VRAM of exactly one process (ours), from nvidia-smi. No other
    process is named or counted. Returns None when unavailable."""
    tool = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/nvidia-smi.exe' if os.name == 'nt' else Path('/usr/bin/nvidia-smi')
    if not pid or not tool.is_file():
        return None
    try:
        query = subprocess.run([str(tool), '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
                               capture_output=True, text=True, timeout=3, check=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return None
    total = None
    for line in query.stdout[:65536].splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) == 2 and parts[0] == str(pid) and parts[1].isdigit():
            total = (total or 0) + int(parts[1]) * 1024 ** 2
    return total


@dataclass
class NativeLease:
    """What a chat turn holds: the connector plus the identity it must keep."""
    name: str
    connector: Connector
    headers: dict
    instance: str
    model: str
    path: Path
    stat: tuple
    sha256: str
    info: dict
    context: int
    runtime: 'NativeRuntime' = field(repr=False)


class NativeRuntime:
    def __init__(self, server_path=None, models_dir=None, *, start_timeout=START_TIMEOUT):
        self.server_path = Path(server_path) if server_path else default_server_path()
        self.models_dir = Path(models_dir) if models_dir else _env_path('NAJDILAB_NATIVE_MODELS', DATA_DIR / 'models')
        self.start_timeout = start_timeout
        self._lock = threading.RLock()
        self._hashes = {}
        self._proc = None
        self._run = None
        self._leased = False
        self.revision = 0
        self.state = 'STOPPED'
        self.last_error = None
        self._devices = None
        # Optional check before a start (Hugging Face Direct: managed files must be verified READY).
        self.start_gate = None

    # ----- discovery -------------------------------------------------------
    def _resolve(self, model_id):
        if not isinstance(model_id, str) or not model_id or len(model_id) > 512 or '\\' in model_id:
            raise IntegrationError('NATIVE_MODEL_INVALID', 'Choose a model from the NajdiLab Native list.')
        root = self.models_dir.resolve()
        path = (root / model_id).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise IntegrationError('NATIVE_MODEL_INVALID', 'The model must be inside the configured models folder.') from None
        if path.suffix.lower() != '.gguf' or not path.is_file():
            raise IntegrationError('NATIVE_MODEL_NOT_FOUND', 'That model file is not in the models folder.', 404)
        return path

    def inspect(self, path):
        item = {'id': path.relative_to(self.models_dir.resolve()).as_posix(), 'file': path.name,
                'size_bytes': path.stat().st_size, 'valid': False, 'error': None}
        if SPLIT.search(path.name):
            item['error'] = 'SPLIT_UNSUPPORTED'
            return item
        try:
            info = describe(read_header(path))
        except GGUFError as error:
            item['error'] = error.code
            return item
        except OSError:
            item['error'] = 'UNREADABLE'
            return item
        item.update(info)
        if info['architecture'] in {None, 'clip'}:
            item['error'] = 'NOT_A_TEXT_MODEL'
        elif not info['model_max_context']:
            item['error'] = 'CONTEXT_UNKNOWN'
        else:
            item['valid'] = True
        cached = self._hashes.get(str(path))
        item['sha256'] = cached[1] if cached and cached[0] == file_stat(path) else None
        return item

    def models(self):
        root = self.models_dir
        items = []
        if root.is_dir():
            resolved = root.resolve()
            for path in sorted(resolved.rglob('*.gguf'))[:MAX_MODELS]:
                # Symlinks that leave the models folder are never listed or read (review F2).
                try:
                    path.resolve().relative_to(resolved)
                except ValueError:
                    continue
                if path.is_file() and len(path.relative_to(resolved).parts) <= 4:
                    items.append(self.inspect(path))
        return {'models_dir': str(root), 'models_dir_exists': root.is_dir(), 'items': items,
                'downloads': 'NEVER',
                'license_note': 'A model file\'s license is separate from llama.cpp\'s MIT license. Check each model\'s own terms before use.'}

    def model_limits(self, model_id):
        """Estimate inputs for a model that is not loaded: nothing is started."""
        path = self._resolve(model_id)
        item = self.inspect(path)
        if not item['valid']:
            raise IntegrationError('NATIVE_MODEL_INVALID', 'This file is not a usable GGUF text model.', 409)
        return {'budget_ceiling': item['model_max_context'], 'model_max_context': item['model_max_context'],
                'runtime_context': None, 'architecture': item['architecture'], 'weights_bytes': item['size_bytes'],
                'quantization': item['quantization'], 'kv': item['kv'], 'capabilities': ['completion'],
                'model_system_prompt': False, 'loaded': None, 'other_loaded_models': [], 'engine_version': None,
                'model_key': None}

    def devices(self):
        """`llama-server --list-devices`, cached. Shows whether this build sees a GPU."""
        if self._devices is not None:
            return self._devices
        if not self.server_path.is_file():
            return []
        try:
            out = subprocess.run([str(self.server_path), '--list-devices'], capture_output=True, timeout=20,
                                 env=self._child_env(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            text = (out.stdout + out.stderr)[:65536].decode('utf-8', 'replace')
        except (OSError, subprocess.SubprocessError):
            return []
        found = []
        for line in text.splitlines():
            match = re.match(r'\s+([A-Za-z]+[0-9]*): (.{1,200}?) \((\d+) MiB, (\d+) MiB free\)', line)
            if match:
                found.append({'id': match[1], 'name': match[2], 'total_bytes': int(match[3]) * 1024 ** 2,
                              'free_bytes': int(match[4]) * 1024 ** 2})
        self._devices = found
        return found

    # ----- lifecycle -------------------------------------------------------
    def status(self):
        with self._lock:
            self._reap()
            run = self._run
            result = {'name': NAME, 'server_path': str(self.server_path), 'server_available': self.server_path.is_file(),
                      'models_dir': str(self.models_dir), 'state': self.state, 'revision': self.revision,
                      'last_error': self.last_error, 'busy': self._leased, 'listen': '127.0.0.1 only',
                      'downloads': 'NEVER'}
            if run:
                result.update({k: run[k] for k in ('model', 'context', 'gpu_layers', 'started_at', 'sha256', 'build')})
                result['pid'] = self._proc.pid
                result['measured_vram_bytes'] = process_vram(self._proc.pid)
            result['devices'] = self.devices()
            return result

    def _child_env(self):
        # No proxy or hub credentials can reach the child; it also runs --offline.
        # llama.cpp reads every LLAMA_ARG_* (and some LLAMA_*) variable as a
        # command-line flag, so an inherited one could re-enable /props writes,
        # metrics, slots, a web UI, another host or a model download. Only the
        # flags NajdiLab passes explicitly may configure the child (review F1).
        blocked = ('_proxy', 'hf_token', 'hugging_face_hub_token')
        return {k: v for k, v in os.environ.items()
                if not k.upper().startswith(('LLAMA_', 'GGML_RPC', 'HF_', 'HUGGING'))
                and not any(k.lower().endswith(b) or k.lower() == b for b in blocked)}

    def _reap(self):
        if self._proc is not None and self._proc.poll() is not None:
            self._proc = None
            self._run = None
            self.state = 'STOPPED' if self.state == 'STOPPING' else 'FAILED'
            if self.state == 'FAILED' and not self.last_error:
                self.last_error = {'code': 'NATIVE_EXITED', 'message': 'NajdiLab Native stopped unexpectedly.'}
            self.revision += 1

    def start(self, data):
        if not isinstance(data, dict) or set(data) != {'approved', 'model', 'context_budget', 'gpu_layers'} or data['approved'] is not True:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve starting NajdiLab Native with this model, context and GPU setting.', 403)
        context, layers = data['context_budget'], data['gpu_layers']
        if type(context) is not int or not 512 <= context <= 1048576:
            raise IntegrationError('INVALID_LIMIT', 'Choose a context between 512 and 1048576 tokens.')
        if not isinstance(layers, str) or not GPU_LAYERS.fullmatch(layers):
            raise IntegrationError('INVALID_PAYLOAD', 'GPU layers must be auto, all, 0 (CPU only) or a layer count.')
        if not self.server_path.is_file():
            raise IntegrationError('NATIVE_SERVER_MISSING', 'No llama-server binary is configured. Set NAJDILAB_NATIVE_SERVER to an existing llama.cpp llama-server; NajdiLab never downloads one.', 409)
        path = self._resolve(data['model'])
        if self.start_gate is not None:
            self.start_gate(path)
        item = self.inspect(path)
        if not item['valid']:
            raise IntegrationError('NATIVE_MODEL_INVALID', 'This file is not a usable GGUF text model.', 409)
        if context > item['model_max_context']:
            raise IntegrationError('ENGINE_CONTEXT_LIMIT', f"This model allows at most {item['model_max_context']} tokens of context.", 409)
        with self._lock:
            self._reap()
            if self._leased:
                raise IntegrationError('NATIVE_BUSY', 'A chat reply is using NajdiLab Native; stop it first.', 409)
            if self._proc is not None or self.state == 'STARTING':
                raise IntegrationError('NATIVE_RUNNING', 'Stop the running model before starting another.', 409)
            self.state, self.last_error = 'STARTING', None
            self.revision += 1
        try:
            stat = file_stat(path)
            cached = self._hashes.get(str(path))
            digest = cached[1] if cached and cached[0] == stat else sha256_file(path)
            if file_stat(path) != stat:
                raise IntegrationError('NATIVE_MODEL_CHANGED', 'The model file changed while it was being verified.', 409)
            self._hashes[str(path)] = (stat, digest)
            key, port = secrets.token_urlsafe(32), free_port()
            command = [str(self.server_path), '-m', str(path), '--host', '127.0.0.1', '--port', str(port),
                       '-c', str(context), '-np', '1', '--no-context-shift', '--no-webui', '--offline', '--no-slots',
                       '--jinja', '--reasoning-format', 'deepseek', '-ngl', layers, '--alias', 'najdilab-native']
            env = {**self._child_env(), 'LLAMA_API_KEY': key}
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       env=env, cwd=str(path.parent),
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                                       start_new_session=os.name != 'nt')
            startup = bytearray()
            healthy = threading.Event()

            def drain():
                # Bounded startup buffer for failure classification only; after
                # the server is healthy output is discarded unread.
                for line in iter(process.stderr.readline, b''):
                    if not healthy.is_set() and len(startup) < 256 * 1024:
                        startup.extend(line)
            threading.Thread(target=drain, daemon=True).start()
            connector = Connector(NAME, 'model_runtime', '', port, '/props', '/health',
                                  ('/apply-template', '/tokenize', '/v1/chat/completions'))
            headers = {'Authorization': f'Bearer {key}'}
            deadline = time.monotonic() + self.start_timeout
            props = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    if request_json(connector, '/health', timeout=2, headers=headers).get('status') == 'ok':
                        props = request_json(connector, '/props', timeout=5, headers=headers)
                        break
                except IntegrationError:
                    pass
                time.sleep(.25)
            healthy.set()
            if props is None:
                if process.poll() is None:
                    process.kill()
                    process.wait(10)
                for pattern, code, message in START_FAILURES:
                    if pattern.search(bytes(startup)):
                        raise IntegrationError(code, message, 409)
                raise IntegrationError('NATIVE_START_FAILED', 'NajdiLab Native did not become ready. Check the model file and llama-server build.', 409)
            settings = props.get('default_generation_settings') if isinstance(props.get('default_generation_settings'), dict) else {}
            # The file must still be the one that was hashed (narrows the swap window, F3).
            if (settings.get('n_ctx') != context or props.get('total_slots') != 1
                    or Path(str(props.get('model_path'))).resolve() != path or file_stat(path) != stat):
                process.kill()
                process.wait(10)
                raise IntegrationError('NATIVE_START_FAILED', 'llama-server did not start with the requested model and context.', 409)
            with self._lock:
                self._proc = process
                self._run = {'model': item['id'], 'context': context, 'gpu_layers': layers, 'started_at': utc_now(),
                             'sha256': digest, 'build': props.get('build_info') if isinstance(props.get('build_info'), str) else None,
                             'instance': secrets.token_hex(8), 'connector': connector, 'headers': headers,
                             'path': path, 'stat': stat, 'info': item}
                self.state = 'RUNNING'
                self.revision += 1
            return self.status()
        except IntegrationError as error:
            with self._lock:
                self.state, self.last_error = 'FAILED', {'code': error.code, 'message': str(error)}
                self.revision += 1
            raise

    def stop(self, data):
        if data != {'approved': True}:
            raise IntegrationError('APPROVAL_REQUIRED', 'Approve stopping NajdiLab Native.', 403)
        with self._lock:
            if self._leased:
                raise IntegrationError('NATIVE_BUSY', 'A chat reply is using NajdiLab Native; stop the reply first.', 409)
            self._terminate()
        return self.status()

    def _terminate(self):
        process, self._proc, self._run = self._proc, None, None
        if process is not None:
            self.state = 'STOPPING'
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(10)
        self.state = 'STOPPED'
        self.revision += 1

    def shutdown(self):
        with self._lock:
            self._terminate()

    @contextmanager
    def chat_lease(self, model, revision):
        with self._lock:
            self._reap()
            run = self._run
            if run is None or run['model'] != model:
                raise IntegrationError('NOT_CONNECTED', 'Start NajdiLab Native with this model first (Chat settings → NajdiLab Native).', 409)
            if type(revision) is not int or revision != self.revision:
                raise IntegrationError('STALE_SELECTION', 'NajdiLab Native changed; refresh before sending.', 409)
            if self._leased:
                raise IntegrationError('ENGINE_BUSY', 'NajdiLab Native is finishing another chat request.', 409)
            self._leased = True
            lease = NativeLease(NAME, run['connector'], run['headers'], run['instance'], run['model'], run['path'],
                                run['stat'], run['sha256'], run['info'], run['context'], self)
        try:
            yield lease
        finally:
            with self._lock:
                self._leased = False

    def serving(self, path):
        """True when NajdiLab Native is running this exact file (so it must not be deleted)."""
        with self._lock:
            self._reap()
            try:
                return self._run is not None and Path(self._run['path']).resolve() == Path(path).resolve()
            except OSError:
                return False

    def same_instance(self, lease):
        with self._lock:
            self._reap()
            return self._run is not None and self._run['instance'] == lease.instance and self._proc is not None

    def engine_factory(self):
        @contextmanager
        def factory(spec, model):
            if isinstance(spec, NativeLease):
                yield NativeEngine(spec)
            else:
                with open_engine(spec, model) as engine:
                    yield engine
        return factory


class NativeEngine:
    """Admission and streaming against NajdiLab's own llama-server."""

    def __init__(self, lease):
        self.lease = lease
        self.deadline = time.monotonic() + CHAT_DEADLINE
        self.expected_model_key = None

    @property
    def model_key(self):
        return f'native:{self.lease.sha256}'

    def call(self, path, payload=None, stop=None, error_status=()):
        if stop is not None and stop.is_set():
            raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise IntegrationError('ENGINE_TIMEOUT', f'Chat exceeded the {CHAT_DEADLINE}-second deadline; no pair was saved.', 504)
        try:
            return request_json(self.lease.connector, path, payload, timeout=remaining, limit=4 * 1024 * 1024,
                                cancel=stop, headers=self.lease.headers, error_status=error_status)
        except IntegrationError as error:
            if stop is not None and stop.is_set():
                raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409) from None
            raise IntegrationError(error.code, str(error), 502) from None

    def verify_identity(self, stop=None):
        if not self.lease.runtime.same_instance(self.lease):
            raise IntegrationError('MODEL_CHANGED', 'NajdiLab Native restarted or stopped during this turn; no pair was saved.', 409)
        try:
            current = file_stat(self.lease.path)
        except OSError:
            current = None
        if current != self.lease.stat:
            raise IntegrationError('MODEL_CHANGED', 'The model file changed on disk; no pair was saved.', 409)
        props = self.call('/props', stop=stop)
        settings = props.get('default_generation_settings') if isinstance(props.get('default_generation_settings'), dict) else {}
        if Path(str(props.get('model_path'))).resolve() != self.lease.path or settings.get('n_ctx') != self.lease.context:
            raise IntegrationError('MODEL_CHANGED', 'NajdiLab Native is no longer serving this model at this context.', 409)
        if self.expected_model_key is not None and self.expected_model_key != self.model_key:
            raise IntegrationError('MODEL_CHANGED', 'A different model file now answers to this name. Start a new conversation.', 409)
        return props

    def limits(self):
        props = self.verify_identity()
        info = self.lease.info
        return {'budget_ceiling': self.lease.context, 'model_max_context': info['model_max_context'],
                'runtime_context': self.lease.context, 'architecture': info['architecture'], 'weights_bytes': info['size_bytes'],
                'quantization': info['quantization'], 'kv': info['kv'], 'capabilities': ['completion'],
                'model_system_prompt': False,
                'loaded': {'context': self.lease.context, 'size_bytes': None,
                           'size_vram_bytes': process_vram(self.lease.runtime._proc.pid if self.lease.runtime._proc else None)},
                'other_loaded_models': [], 'model_key': self.model_key,
                'engine_version': props.get('build_info') if isinstance(props.get('build_info'), str) else None}

    def measure(self, messages, budget, stop=None):
        timings = {}
        started = time.monotonic()
        props = self.verify_identity(stop)
        timings['model_identity_ms'] = ms(started)
        result = {'model_key': self.model_key, 'loaded_context': self.lease.context, 'timings': timings,
                  'engine_version': props.get('build_info') if isinstance(props.get('build_info'), str) else None}
        if budget != self.lease.context:
            raise IntegrationError('ENGINE_CONTEXT_MISMATCH', 'NajdiLab Native is running at a different context than this chat. Restart it at this chat\'s context, or start a new chat.', 409)
        started = time.monotonic()
        rendered = self.call('/apply-template', {'messages': messages}, stop)
        prompt = rendered.get('prompt')
        if not isinstance(prompt, str) or not prompt:
            raise IntegrationError('EXACT_TOKEN_COUNT_UNAVAILABLE', 'NajdiLab Native did not render the chat template; admission cannot be proven.', 409)
        tokens = self.call('/tokenize', {'content': prompt, 'add_special': True, 'parse_special': True}, stop).get('tokens')
        if not isinstance(tokens, list) or not tokens or any(type(t) is not int for t in tokens):
            raise IntegrationError('EXACT_TOKEN_COUNT_UNAVAILABLE', 'NajdiLab Native did not report an exact prompt size; admission cannot be proven.', 409)
        timings['token_count_ms'] = ms(started)
        return {**result, 'input_tokens': len(tokens)}

    def generate(self, messages, reserve, stop, on_delta=None):
        collector = StreamCollector(on_delta)
        final = {'usage': None, 'finish': None, 'tool_calls': False, 'done': False}

        def line(raw):
            if not raw.startswith(b'data:'):
                return  # SSE comments/keep-alives
            body = raw[5:].strip()
            if body == b'[DONE]':
                final['done'] = True
                return
            if final['done']:
                raise IntegrationError('INCOMPLETE_RESPONSE', 'NajdiLab Native sent data after its final event; no pair was saved.', 502)
            value = json.loads(body.decode('utf-8'))
            if not isinstance(value, dict) or 'error' in value:
                raise IntegrationError('ENGINE_REFUSED', 'NajdiLab Native stopped this reply with an error; no pair was saved.', 502)
            if isinstance(value.get('usage'), dict):
                final['usage'] = value['usage']
            for choice in value.get('choices') or []:
                if not isinstance(choice, dict) or choice.get('index', 0) != 0:
                    raise IntegrationError('INCOMPLETE_RESPONSE', 'NajdiLab Native returned more than one reply; no pair was saved.', 502)
                delta = choice.get('delta') if isinstance(choice.get('delta'), dict) else {}
                collector.add('thinking', delta.get('reasoning_content'))
                collector.add('content', delta.get('content'))
                if delta.get('tool_calls'):
                    final['tool_calls'] = True
                if choice.get('finish_reason') is not None:
                    final['finish'] = choice['finish_reason']
        if stop is not None and stop.is_set():
            raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
        payload = {'messages': messages, 'max_tokens': reserve, 'stream': True, 'stream_options': {'include_usage': True}}
        remaining = self.deadline - time.monotonic()
        try:
            request_stream(self.lease.connector, '/v1/chat/completions', payload, line, timeout=max(remaining, .1),
                           limit=STREAM_LIMIT, cancel=stop, headers=self.lease.headers)
        except IntegrationError as error:
            if stop is not None and stop.is_set():
                raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409) from None
            if error.code == 'TIMEOUT':
                raise IntegrationError('ENGINE_TIMEOUT', f'Chat exceeded the {CHAT_DEADLINE}-second deadline; no pair was saved.', 504) from None
            raise IntegrationError(error.code, str(error), 502) from None
        if not final['done'] or not isinstance(final['usage'], dict) or final['finish'] is None:
            raise IntegrationError('INCOMPLETE_RESPONSE', 'NajdiLab Native ended the stream without its final usage; no pair was saved.', 502)
        started = time.monotonic()
        self.verify_identity(stop)
        usage = final['usage']
        return {'content': ''.join(collector.content), 'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens'),
                'stop_reason': 'stop' if final['finish'] == 'stop' else final['finish'],
                'tool_calls': final['tool_calls'], 'reasoning_discarded': bool(collector.thinking),
                'timings': {**collector.timings(), 'identity_recheck_ms': ms(started)}}

    def close(self):
        pass
