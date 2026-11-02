"""Bounded, read-only GGUF header reader for NajdiLab Native.

Independent implementation of the public GGUF container layout (magic, version,
tensor/metadata counts, typed key/value metadata). It reads metadata only, never
tensors, and keeps only the scalar keys NajdiLab needs. Large arrays such as the
tokenizer vocabulary are skipped without being stored.
"""
from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"GGUF"
VERSIONS = {2, 3}
MAX_KV = 65536
MAX_TENSORS = 1_000_000
MAX_STRING = 16 * 1024 * 1024
MAX_ARRAY = 16 * 1024 * 1024
SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
# llama.cpp file-type numbers as published in GGUF metadata (general.file_type).
FILE_TYPES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1", 10: "Q2_K", 11: "Q3_K_S",
    12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K",
    19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S", 22: "IQ3_XS", 23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL",
    26: "IQ3_S", 27: "IQ3_M", 28: "IQ2_S", 29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M", 32: "BF16",
    36: "TQ1_0", 37: "TQ2_0", 38: "MXFP4_MOE",
}
KV_SUFFIXES = ("block_count", "embedding_length", "attention.head_count", "attention.head_count_kv",
               "attention.key_length", "attention.value_length")


class GGUFError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Reader:
    def __init__(self, stream, size):
        self.stream, self.size = stream, size

    def take(self, count):
        data = self.stream.read(count)
        if len(data) != count:
            raise GGUFError("TRUNCATED")
        return data

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self, keep=True):
        length = self.unpack("<Q")
        if length > MAX_STRING:
            raise GGUFError("STRING_TOO_LARGE")
        if not keep:
            self.stream.seek(length, 1)
            if self.stream.tell() > self.size:
                raise GGUFError("TRUNCATED")
            return None
        try:
            return self.take(length).decode("utf-8")
        except UnicodeDecodeError:
            raise GGUFError("INVALID_STRING") from None

    def value(self, kind, keep):
        if kind in SCALAR:
            return self.unpack(SCALAR[kind])
        if kind == 8:
            return self.string(keep)
        if kind == 9:
            item, count = self.unpack("<I"), self.unpack("<Q")
            if count > MAX_ARRAY or item == 9:
                raise GGUFError("ARRAY_UNSUPPORTED")
            if item in SCALAR:
                width = struct.calcsize(SCALAR[item])
                if not keep or count > 4096:
                    self.stream.seek(width * count, 1)
                    if self.stream.tell() > self.size:
                        raise GGUFError("TRUNCATED")
                    return {"array_length": count}
                return [self.unpack(SCALAR[item]) for _ in range(count)]
            if item == 8:
                for _ in range(count):
                    self.string(keep=False)
                return {"array_length": count}
            raise GGUFError("UNKNOWN_TYPE")
        raise GGUFError("UNKNOWN_TYPE")


def read_header(path: Path | str) -> dict:
    """Returns {'version', 'tensor_count', 'metadata': {...}} or raises GGUFError.

    Kept keys: general.*, <arch>.context_length and KV-cache sizes, and the
    presence/length of tokenizer.chat_template (not its text)."""
    path = Path(path)
    size = path.stat().st_size
    if size < 24:
        raise GGUFError("TOO_SMALL")
    with path.open("rb") as stream:
        reader = _Reader(stream, size)
        if reader.take(4) != MAGIC:
            raise GGUFError("NOT_GGUF")
        version = reader.unpack("<I")
        if version not in VERSIONS:
            raise GGUFError("UNSUPPORTED_VERSION")
        tensors, count = reader.unpack("<Q"), reader.unpack("<Q")
        if tensors > MAX_TENSORS or count > MAX_KV:
            raise GGUFError("HEADER_LIMITS")
        metadata: dict = {}
        for _ in range(count):
            key = reader.string()
            kind = reader.unpack("<I")
            if key == "tokenizer.chat_template":
                start = stream.tell()
                reader.value(kind, keep=False)
                metadata["tokenizer.chat_template.length"] = stream.tell() - start
                continue
            keep = key.startswith("general.") or ".context_length" in key or key.endswith(KV_SUFFIXES)
            value = reader.value(kind, keep)
            if keep:
                metadata[key] = value
    if tensors == 0:
        raise GGUFError("NO_TENSORS")
    return {"version": version, "tensor_count": tensors, "metadata": metadata}


def describe(header: dict) -> dict:
    meta = header["metadata"]
    arch = meta.get("general.architecture") if isinstance(meta.get("general.architecture"), str) else None
    file_type = meta.get("general.file_type")
    context = meta.get(f"{arch}.context_length") if arch else None
    return {
        "architecture": arch,
        "name": meta.get("general.name") if isinstance(meta.get("general.name"), str) else None,
        "license": meta.get("general.license") if isinstance(meta.get("general.license"), str) else None,
        "quantization": FILE_TYPES.get(file_type, f"file_type {file_type}") if type(file_type) is int else None,
        "model_max_context": context if type(context) is int and context > 0 else None,
        "kv": {k: meta.get(f"{arch}.{k}") for k in KV_SUFFIXES} if arch else None,
        "chat_template": bool(meta.get("tokenizer.chat_template.length")),
        "gguf_version": header["version"],
        "tensor_count": header["tensor_count"],
    }
