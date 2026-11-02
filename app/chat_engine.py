"""Bounded raw-chat access: LM Studio helper process and Ollama loopback HTTP."""
from contextlib import contextmanager
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

from .db import ROOT
from .integrations import IntegrationError, request_json

MAX_WIRE = 512 * 1024
# Covers a cold model load plus an 8192-token reply on a mid-range GPU. Both
# engines keep running if a turn is abandoned here; only NajdiLab's call ends.
CHAT_DEADLINE = 600
SHOW_LIMIT = 8 * 1024 * 1024
CHAT_LIMIT = 2 * 1024 * 1024
UNAVAILABLE = 'Exact loaded-model chat is unavailable. Check the optional SDK and the existing engine; no model was loaded or settings changed.'
WORKER_ERRORS = {
    'SDK_REQUIRED': 'LM Studio Chat needs the pinned optional SDK (requirements-chat.txt) in NajdiLab\'s own environment.',
    'MODEL_NOT_LOADED': 'This model is not loaded in LM Studio. Load it there and retry; NajdiLab never loads models.',
    'MODEL_CHANGED': 'The loaded model, template or context changed during this turn; no pair was saved.',
    'RESULT_MISMATCH': 'The reply did not match the measured request; no pair was saved.',
    'NON_TEXT_RESPONSE': 'The model produced reasoning fragments, which LM Studio Chat refuses rather than edits; no pair was saved.',
    'RESPONSE_TOO_LARGE': 'The reply exceeded the size limit; no pair was saved.',
    'ENGINE_PROTOCOL_ERROR': UNAVAILABLE,
}
# Phase C / AI-02: fixed, content-free explanations for the four LM Studio
# post-generation integrity checks; the public error code remains unchanged.
WORKER_MISMATCH_DETAILS = {
    'INSTANCE_REFERENCE': 'The loaded model instance changed.',
    'STRUCTURED_OUTPUT': 'The SDK returned structured output instead of plain text.',
    'STREAM_CONTENT': 'The final reply differed from the streamed text.',
    'PROMPT_TOKEN_COUNT': 'The final token count differed from the measured prompt.',
}
# Ollama's llama-server refusal. Only ever matched, never shown to a user.
OVERFLOW = re.compile(r'request \((\d+) tokens\) exceeds the available context size \((\d+) tokens\)')
CLOUD_NAME = re.compile(r'[:-]cloud$')
LOCAL_DIGEST = re.compile(r'(?:sha256:)?([0-9a-f]{64})\Z')
# Verified from Ollama v0.40.13 source. Unknown resolver semantics must fail closed.
PINNED_REF_VERSION = '0.40.13'


class EngineProcess:
    def __init__(self, spec, model):
        # Only this child environment changes. No application config or service
        # is edited; SDK traffic must never inherit a network proxy/credential.
        env = {k:v for k,v in os.environ.items() if not (k.lower().endswith('_proxy') or k.lower().startswith('lmstudio'))}
        env.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        self.process = subprocess.Popen([sys.executable, '-m', 'app.chat_engine_worker'], cwd=ROOT,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.events = queue.Queue(maxsize=4)
        self.deadline = time.monotonic() + CHAT_DEADLINE
        self.stopped = False
        def read():
            try:
                while True:
                    line = self.process.stdout.readline(MAX_WIRE + 1)
                    if not line or len(line) > MAX_WIRE:
                        self.events.put_nowait({'error':'ENGINE_PROTOCOL_ERROR'})
                        return
                    self.events.put_nowait(json.loads(line))
            except (OSError, ValueError, queue.Full):
                try:
                    self.events.put_nowait({'error':'ENGINE_PROTOCOL_ERROR'})
                except queue.Full:
                    pass
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        self.write({'port':spec.port,'model':model,'deadline':CHAT_DEADLINE})

    def write(self, data):
        try:
            self.process.stdin.write(json.dumps(data, ensure_ascii=False).encode('utf-8') + b'\n')
            self.process.stdin.flush()
        except (OSError, BrokenPipeError):
            raise IntegrationError('ENGINE_UNAVAILABLE', 'Chat helper is unavailable; no pair was saved.', 502) from None

    def receive(self, stop=None):
        while time.monotonic() < self.deadline:
            if stop is not None and stop.is_set():
                self.stopped = True
                self.write({'stop':True})
                raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
            try:
                result = self.events.get(timeout=.1)
            except queue.Empty:
                continue
            if not isinstance(result, dict) or result.get('error'):
                code = result.get('error') if isinstance(result, dict) else 'ENGINE_PROTOCOL_ERROR'
                if code not in WORKER_ERRORS:
                    code = 'ENGINE_UNAVAILABLE'
                message = WORKER_ERRORS.get(code, UNAVAILABLE)
                if code == 'RESULT_MISMATCH' and isinstance(result, dict):
                    # Unknown/malicious check values are ignored, never reflected.
                    detail = WORKER_MISMATCH_DETAILS.get(result.get('check')) if isinstance(result.get('check'), str) else None
                    if detail:
                        message += ' Integrity check: ' + detail
                raise IntegrationError(code, message, 409)
            return result
        raise IntegrationError('ENGINE_TIMEOUT', f'Chat exceeded the {CHAT_DEADLINE}-second deadline; no pair was saved.', 504)

    def limits(self):
        self.write({'limits':True})
        return self.receive()

    def measure(self, messages, budget, stop=None):
        self.write({'messages':messages})
        return self.receive(stop)

    def generate(self, messages, reserve, stop):
        self.write({'reply_reserve':reserve})
        return self.receive(stop)

    def close(self):
        # Child cancellation asks only its own inference request to stop. It
        # never stops the engine/service; upstream cancellation is best effort.
        if self.process.poll() is None:
            try:
                self.write({'stop':True})
                self.process.wait(timeout=1)
            except (IntegrationError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdin.close()
        self.process.stdout.close()
        self.reader.join(1)


def kv_inputs(info, arch):
    """Only the fields the KV-cache estimate needs, from `/api/show` model_info."""
    keys = ('block_count', 'embedding_length', 'attention.head_count', 'attention.head_count_kv',
            'attention.key_length', 'attention.value_length')
    return {k: info.get(f'{arch}.{k}') for k in keys}


class OllamaEngine:
    """Proves admission per turn using only public `/api/*` behavior.

    Requests use a content-addressed local manifest reference, never the
    mutable selected tag. Ollama has no tokenize route. It silently drops old messages by default
    (`truncate`) and shifts context while generating (`shift`), so each request
    turns both off, and each turn first verifies the engine actually refuses an
    oversized history. `prompt_eval_count` of a one-token prediction is then the
    exact rendered prompt, from the same template, tokenizer and options the
    reply uses. `num_ctx` is sent with every request, so another client's
    runner settings cannot move the limit between those two calls.
    """

    def __init__(self, spec, model):
        self.spec, self.model = spec, model
        self.deadline = time.monotonic() + CHAT_DEADLINE
        self.budget, self.digest, self.model_ref = None, None, None
        self.expected_model_key = None

    def call(self, path, payload=None, *, stop=None, limit=None, error_status=()):
        if stop is not None and stop.is_set():
            raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise IntegrationError('ENGINE_TIMEOUT', f'Chat exceeded the {CHAT_DEADLINE}-second deadline; no pair was saved.', 504)
        try:
            return request_json(self.spec, path, payload, timeout=remaining, limit=limit or CHAT_LIMIT,
                                cancel=stop, error_status=error_status)
        except IntegrationError as error:
            if stop is not None and stop.is_set():
                raise IntegrationError('STOPPED', 'Turn stopped; no pair was saved.', 409) from None
            if error.code == 'TIMEOUT':
                raise IntegrationError('ENGINE_TIMEOUT', f'Chat exceeded the {CHAT_DEADLINE}-second deadline; no pair was saved.', 504) from None
            raise IntegrationError(error.code, str(error), 502) from None

    def current_digest(self, stop=None):
        rows = [m for m in self.call(self.spec.models_path, stop=stop).get('models', [])
                if isinstance(m, dict) and m.get('name') == self.model]
        if len(rows) != 1 or not isinstance(rows[0].get('digest'), str) or not rows[0]['digest']:
            raise IntegrationError('MODEL_UNAVAILABLE', 'Ollama no longer lists exactly this model; no pair was saved.', 409)
        return rows[0]

    def loaded(self, stop=None):
        rows = self.call('/api/ps', stop=stop).get('models')
        return rows if isinstance(rows, list) else []

    def limits(self, stop=None):
        """Resolve an immutable *local* manifest, not the mutable selected tag.

        Ollama v0.40.13 resolves sha256:<digest>:local against a content-addressed
        manifest and refuses remote models. Untested versions fail closed.
        """
        row = self.current_digest(stop)
        match = LOCAL_DIGEST.fullmatch(row.get('digest') if isinstance(row.get('digest'), str) else '')
        if not match:
            raise IntegrationError('MODEL_REFERENCE_UNVERIFIED', 'Ollama did not return a full local manifest digest; Chat is blocked.', 409)
        version = self.call('/api/version', stop=stop).get('version')
        if version != PINNED_REF_VERSION:
            raise IntegrationError('MODEL_REFERENCE_UNVERIFIED', 'This Ollama version has not been verified for immutable local references; Chat is blocked.', 409)
        pinned = f'sha256:{match.group(1)}:local'
        show = self.call('/api/show', {'model':pinned}, limit=SHOW_LIMIT, stop=stop)
        # A cloud tag forwards prompts off this machine. Chat stays local-only.
        if (CLOUD_NAME.search(self.model) or show.get('remote_host') or show.get('remote_model') or
                row.get('remote_host') or row.get('remote_model')):
            raise IntegrationError('REMOTE_MODEL_REFUSED', 'This is a cloud model; prompts would leave this machine. Chat only uses local models.', 409)
        capabilities = show.get('capabilities')
        info = show.get('model_info')
        if not isinstance(capabilities, list) or 'completion' not in capabilities or not isinstance(info, dict):
            raise IntegrationError('MODEL_UNSUPPORTED', 'Ollama does not report this as a local text-completion model.', 409)
        arch = info.get('general.architecture')
        maximum = info.get(f'{arch}.context_length')
        if type(maximum) is not int or maximum < 1:
            raise IntegrationError('CONTEXT_UNKNOWN', 'Ollama did not report this model\'s maximum context; admission cannot be proven.', 409)
        self.digest = match.group(1)
        self.model_ref = pinned
        running = self.loaded(stop)
        mine = next((m for m in running if isinstance(m, dict) and m.get('digest') == row['digest']), None)
        details = show.get('details') if isinstance(show.get('details'), dict) else {}
        return {'budget_ceiling':maximum, 'model_max_context':maximum, 'architecture':arch,
                'runtime_context':mine.get('context_length') if mine else None,
                'weights_bytes':row.get('size'), 'quantization':details.get('quantization_level'),
                'kv':kv_inputs(info, arch), 'capabilities':capabilities, 'model_system_prompt':bool(show.get('system')),
                'loaded':{'context':mine.get('context_length'), 'size_bytes':mine.get('size'), 'size_vram_bytes':mine.get('size_vram')} if mine else None,
                'other_loaded_models':[m.get('name') for m in running if m is not mine and isinstance(m, dict)],
                'model_key':f"ollama:{self.digest}", 'engine_version':version}

    def chat(self, messages, predict, stop, *, error_status=()):
        # Nothing here but the conversation and the two limits this workspace
        # must set: no system, tools, format, think, keep_alive or sampling.
        if not self.model_ref or not self.digest:
            raise IntegrationError('MODEL_REFERENCE_UNVERIFIED', 'No immutable local model reference was established; Chat is blocked.', 409)
        return self.call('/api/chat', {'model':self.model_ref, 'messages':messages, 'stream':False, 'truncate':False, 'shift':False,
                                       'options':{'num_ctx':self.budget, 'num_predict':predict}},
                         stop=stop, error_status=error_status)

    def prove_refusal(self, stop):
        """Old servers ignore `truncate`, so test the behavior, not a version.

        Dropping the first message would leave a tiny prompt, so a success here
        means overflow is silent on this engine/model. The filler needs no exact
        size: the engine's own refusal states the count, and evaluates nothing.
        """
        filler = ' '.join(map(str, range(self.budget + 512)))
        value = self.chat([{'role':'user','content':filler}, {'role':'assistant','content':'ok'}, {'role':'user','content':'ok'}],
                          1, stop, error_status=(400,))
        refused = OVERFLOW.search(str(value.get('error'))) if value.get('http_status') == 400 else None
        if not refused or int(refused[1]) <= int(refused[2]):
            raise IntegrationError('CONTEXT_REFUSAL_UNPROVEN', 'Ollama did not refuse an oversized history, so silent context truncation cannot be ruled out. Sending is blocked; update Ollama or use a different model.', 409)
        if int(refused[2]) < self.budget:
            raise self.mismatch()

    def mismatch(self):
        return IntegrationError('ENGINE_CONTEXT_MISMATCH', 'Ollama is not running this model at the selected context, so the budget cannot be proven. Choose a smaller budget in a new chat.', 409)

    def measure(self, messages, budget, stop=None):
        self.budget = budget
        limits = self.limits(stop)
        if self.expected_model_key is not None and self.expected_model_key != limits['model_key']:
            raise IntegrationError('MODEL_CHANGED', 'The selected model was replaced before inference; no prompt was sent.', 409)
        result = {'loaded_context':limits['model_max_context'], 'model_key':limits['model_key'],
                  'engine_version':limits['engine_version']}
        if budget > limits['model_max_context']:
            return {**result, 'input_tokens':0}
        self.prove_refusal(stop)
        value = self.chat(messages, 1, stop, error_status=(400,))
        if value.get('http_status') == 400:
            refused = OVERFLOW.search(str(value.get('error')))
            if not refused:
                raise IntegrationError('ENGINE_REFUSED', 'Ollama refused this request; no pair was saved.', 502)
            tokens = int(refused[1])
        else:
            tokens = value.get('prompt_eval_count')
            if value.get('done') is not True or type(tokens) is not int or tokens < 1:
                raise IntegrationError('EXACT_TOKEN_COUNT_UNAVAILABLE', 'Ollama did not report an exact prompt size; admission cannot be proven.', 409)
        # Ollama silently clamps num_ctx; only /api/ps shows what it really used.
        runtime = next((m.get('context_length') for m in self.loaded(stop) if isinstance(m, dict) and m.get('digest') == self.digest), None)
        if runtime != budget:
            raise self.mismatch()
        return {**result, 'input_tokens':tokens, 'loaded_context':runtime}

    def generate(self, messages, reserve, stop):
        value = self.chat(messages, reserve, stop)
        message = value.get('message')
        current = self.current_digest(stop).get('digest')
        matched = LOCAL_DIGEST.fullmatch(current if isinstance(current, str) else '')
        if not matched or matched.group(1) != self.digest:
            raise IntegrationError('MODEL_CHANGED', 'The Ollama model changed during this turn; no pair was saved.', 409)
        if (value.get('done') is not True or value.get('remote_host') or value.get('remote_model') or
                not isinstance(message, dict) or message.get('role') != 'assistant'):
            raise IntegrationError('INCOMPLETE_RESPONSE', 'Ollama did not return a finished local reply; no pair was saved.', 502)
        return {'content':message.get('content'), 'input_tokens':value.get('prompt_eval_count'),
                'output_tokens':value.get('eval_count'), 'stop_reason':value.get('done_reason'),
                'tool_calls':message.get('tool_calls'), 'reasoning_discarded':bool(message.get('thinking'))}

    def close(self):
        pass


@contextmanager
def open_engine(spec, model):
    engine = OllamaEngine(spec, model) if spec.name == 'Ollama' else EngineProcess(spec, model)
    try:
        yield engine
    finally:
        engine.close()
