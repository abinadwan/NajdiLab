"""A tiny random-weight llama GGUF, generated locally (nothing is downloaded).

Used by the managed runtime's GPU probe (app/managed_runtime.py) to prove that a llama-server build
can load and compute on a device, and by the tests as a synthetic model. It has a byte-level
vocabulary, one layer and 32-wide embeddings: a few hundred kilobytes, no real weights.
"""
from __future__ import annotations

from pathlib import Path
import random
import struct

EMBED, FF, HEADS, TRAIN_CONTEXT = 32, 64, 2, 8192


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
