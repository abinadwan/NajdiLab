"""Bounded helper process for an existing LM Studio loaded-model API handle."""
from contextlib import contextmanager
import json
import os
import queue
import subprocess
import sys
import threading
import time

from .db import ROOT
from .integrations import IntegrationError

MAX_WIRE = 512 * 1024


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
        self.deadline = time.monotonic() + 90
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
        self.write({'port':spec.port,'model':model})

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
                if code not in {'SDK_REQUIRED','MODEL_NOT_LOADED','ENGINE_PROTOCOL_ERROR'}:
                    code = 'ENGINE_UNAVAILABLE'
                raise IntegrationError(code, 'Exact loaded-model chat is unavailable. Check the optional SDK and the existing engine; no model was loaded or settings changed.', 409)
            return result
        raise IntegrationError('ENGINE_TIMEOUT', 'Chat exceeded the 90-second deadline; no pair was saved.', 504)

    def measure(self, messages):
        self.write({'messages':messages})
        return self.receive()

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


@contextmanager
def open_engine(spec, model):
    if spec.name != 'LM Studio':
        raise IntegrationError('EXACT_TOKEN_COUNT_UNAVAILABLE', 'Ollama chat is blocked: an exact public template-token preflight is not verified. Runtime connectivity does not establish safe Chat admission.', 409)
    engine = EngineProcess(spec, model)
    try:
        yield engine
    finally:
        engine.close()
