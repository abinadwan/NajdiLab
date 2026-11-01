"""Disposable real-Ollama fixture: installed binary, isolated dirs, synthetic model.

Runs the owner's unmodified ollama executable on a private loopback port with
its own HOME/model directory and GPUs hidden. The model is a tiny random-weight
GGUF generated here, so nothing is downloaded and no installed model, service or
setting is read or changed. Proves engine behavior, not installed-model quality.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request

EMBED, FF, HEADS, TRAIN_CONTEXT = 32, 64, 2, 8192
WORDS = [bytes([c]) for c in b'abcdefgh']


def binary():
    known = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'
    return str(known) if known.is_file() else shutil.which('ollama')


def _text(value):
    raw = value.encode('utf-8')
    return struct.pack('<Q', len(raw)) + raw


def _kv(key, kind, value):
    encode = {4: lambda v: struct.pack('<I', v), 6: lambda v: struct.pack('<f', v), 8: _text}
    if kind == 9:
        item, values = value
        body = struct.pack('<IQ', item, len(values)) + b''.join(encode.get(item, lambda v: struct.pack('<i', v))(v) for v in values)
    else:
        body = encode[kind](value)
    return _text(key) + struct.pack('<I', kind) + body


def write_gguf(path: Path, *, seed=7, eos=True):
    """Byte-token llama vocabulary: one token per UTF-8 byte, predictable counts.

    `eos=False` removes the end token, so a reply only ends at a limit or a stop.
    """
    rng = random.Random(seed)
    tokens = ['<unk>', '<s>', '</s>'] + [f'<0x{b:02X}>' for b in range(256)]
    kinds = [2, 3, 3] + [6] * 256
    metadata = [
        ('general.architecture', 8, 'llama'), ('general.name', 8, 'najdilab-synthetic'), ('general.file_type', 4, 0),
        ('general.alignment', 4, 32), ('llama.context_length', 4, TRAIN_CONTEXT), ('llama.embedding_length', 4, EMBED),
        ('llama.block_count', 4, 1), ('llama.feed_forward_length', 4, FF), ('llama.attention.head_count', 4, HEADS),
        ('llama.attention.layer_norm_rms_epsilon', 6, 1e-5), ('llama.rope.dimension_count', 4, EMBED // HEADS),
        ('tokenizer.ggml.model', 8, 'llama'), ('tokenizer.ggml.tokens', 9, (8, tokens)),
        ('tokenizer.ggml.scores', 9, (6, [0.0] * len(tokens))), ('tokenizer.ggml.token_type', 9, (5, kinds)),
        ('tokenizer.ggml.bos_token_id', 4, 1), ('tokenizer.ggml.eos_token_id', 4, 2), ('tokenizer.ggml.unknown_token_id', 4, 0),
    ]
    vocab = len(tokens)
    shapes = {'token_embd.weight': (EMBED, vocab), 'output_norm.weight': (EMBED,), 'output.weight': (EMBED, vocab),
              'blk.0.attn_norm.weight': (EMBED,), 'blk.0.ffn_norm.weight': (EMBED,),
              'blk.0.attn_q.weight': (EMBED, EMBED), 'blk.0.attn_k.weight': (EMBED, EMBED),
              'blk.0.attn_v.weight': (EMBED, EMBED), 'blk.0.attn_output.weight': (EMBED, EMBED),
              'blk.0.ffn_gate.weight': (EMBED, FF), 'blk.0.ffn_up.weight': (EMBED, FF), 'blk.0.ffn_down.weight': (FF, EMBED)}
    # Every other logit is exactly 0. Each +w/-w letter pair has one member at or
    # above that whatever the hidden state, so with top_k the four best tokens
    # are always letters: readable replies, and none can end without an EOS row.
    rows = {}
    for left, right in zip(b'abcd', b'efgh'):
        rows[3 + left] = [rng.gauss(0, 1) for _ in range(EMBED)]
        rows[3 + right] = [-v for v in rows[3 + left]]
    if eos:
        rows[2] = [rng.gauss(0, 1) for _ in range(EMBED)]
    info, blobs, offset = b'', [], 0
    for name, shape in shapes.items():
        count = 1
        for size in shape:
            count *= size
        if name == 'output.weight':
            values = [v for row in range(vocab) for v in rows.get(row, [0.0] * EMBED)]
        elif name.endswith('norm.weight'):
            values = [1.0] * count
        else:
            values = [rng.gauss(0, .1) for _ in range(count)]
        raw = struct.pack(f'<{count}f', *values)
        info += _text(name) + struct.pack('<I', len(shape)) + b''.join(struct.pack('<Q', s) for s in shape) + struct.pack('<IQ', 0, offset)
        pad = -len(raw) % 32
        blobs.append(raw + b'\0' * pad)
        offset += len(raw) + pad
    head = b'GGUF' + struct.pack('<IQQ', 3, len(shapes), len(metadata)) + b''.join(_kv(*row) for row in metadata) + info
    path.write_bytes(head + b'\0' * (-len(head) % 32) + b''.join(blobs))


class DisposableOllama:
    def __init__(self, root: Path, *, parallel=1):
        self.root, self.parallel = Path(root), parallel
        self.port, self.process = None, None

    def env(self):
        home = self.root / 'home'
        home.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC'}}
        return {**keep, 'HOME': str(home), 'USERPROFILE': str(home), 'LOCALAPPDATA': str(home), 'APPDATA': str(home),
                'OLLAMA_HOST': f'127.0.0.1:{self.port}', 'OLLAMA_MODELS': str(self.root / 'models'),
                'OLLAMA_NUM_PARALLEL': str(self.parallel), 'OLLAMA_MAX_LOADED_MODELS': '1', 'OLLAMA_NO_CLOUD': '1',
                'OLLAMA_KEEP_ALIVE': '5m', 'OLLAMA_LLM_LIBRARY': 'cpu', 'CUDA_VISIBLE_DEVICES': '-1',
                'ROCR_VISIBLE_DEVICES': '-1', 'GGML_VK_VISIBLE_DEVICES': '-1'}

    def __enter__(self):
        tool = binary()
        if not tool:
            raise FileNotFoundError('ollama executable')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = (self.root / 'serve.log').open('wb')
        self.process = subprocess.Popen([tool, 'serve'], env=self.env(), cwd=self.root, stdout=self.log, stderr=subprocess.STDOUT,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 30
        while True:
            try:
                self.call('GET', '/api/version')
                break
            except (OSError, urllib.error.URLError):
                if time.monotonic() > deadline or self.process.poll() is not None:
                    self.__exit__(None, None, None)
                    raise TimeoutError('disposable ollama did not start') from None
                time.sleep(.2)
        return self

    def __exit__(self, *_):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(10)
        self.log.close()

    def call(self, method, path, payload=None, timeout=120):
        """Raw client for assertions; returns (status, value). Never uses a proxy."""
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b'{}')

    def create(self, name='synthetic', *, seed=7, eos=True, modelfile=''):
        model = self.root / f'{name}.gguf'
        write_gguf(model, seed=seed, eos=eos)
        recipe = self.root / f'{name}.Modelfile'
        template = 'TEMPLATE """{{ range .Messages }}<{{ .Role }}>{{ .Content }}{{ end }}<assistant>"""\n'
        # The penalty avoids Ollama's "token repeat limit" abort on random weights.
        sampling = (f'PARAMETER temperature 1\nPARAMETER seed 42\nPARAMETER top_k {5 if eos else 4}\n'
                    'PARAMETER repeat_penalty 1.5\nPARAMETER repeat_last_n 16\n')
        recipe.write_text(f'FROM {model.as_posix()}\n{template}{sampling}{modelfile}', encoding='utf-8')
        subprocess.run([binary(), 'create', name, '-f', str(recipe)], env=self.env(), cwd=self.root, check=True,
                       capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return f'{name}:latest'
