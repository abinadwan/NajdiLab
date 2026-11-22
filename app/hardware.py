"""Explicit read-only host snapshot. No model allocation or stress test."""
import csv
import ctypes
import os
from pathlib import Path
import subprocess

from .db import utc_now

CANDIDATES = (4096, 8192, 16384, 32768, 65536)
# Rule-of-thumb margin for graph/scratch buffers and allocator overhead. It is
# not measured per model, which is why every result is labeled an estimate.
HEADROOM = 1.15
RUNTIME_OVERHEAD = 512 * 1024**2
UNVERIFIED = 'Unverified estimate, not a guaranteed safe limit. No allocation test was run.'


def largest(value):
    """GGUF stores per-layer attention as either one number or a list."""
    if isinstance(value, list):
        value = max((v for v in value if type(v) is int), default=None)
    return value if type(value) is int and value > 0 else None


def kv_bytes_per_token(kv):
    """Upper bound: every layer full-attention, keys and values as f16.

    Sliding-window layers and other cache types only ever reduce this.
    """
    if not isinstance(kv, dict):
        return None
    layers, embedding = largest(kv.get('block_count')), largest(kv.get('embedding_length'))
    heads = largest(kv.get('attention.head_count'))
    if not layers or not embedding or not heads:
        return None
    heads_kv = largest(kv.get('attention.head_count_kv')) or heads
    key = largest(kv.get('attention.key_length')) or embedding // heads
    value = largest(kv.get('attention.value_length')) or embedding // heads
    return layers * heads_kv * (key + value) * 2


def recommendation(snapshot, limits=None):
    """Keeps model maximum, runtime setting, estimate and measurement separate."""
    limits = limits or {}
    evidence = {'budget_ceiling':limits.get('budget_ceiling'),
                'model_max_context':limits.get('model_max_context'), 'runtime_context':limits.get('runtime_context'),
                'measured':limits.get('loaded'), 'candidates':[]}
    insufficient = {**evidence, 'status':'INSUFFICIENT_EVIDENCE', 'recommended_context':None, 'label':None}
    if not limits:
        return {**insufficient, 'missing':['model_resident_weights','kv_cache','backend_placement','runtime_overhead','concurrent_allocations'],
                'reason':'Free RAM/VRAM and model disk size do not prove safe context. Loaded context is an engine ceiling only. No allocation test was run.'}
    per_token = kv_bytes_per_token(limits.get('kv'))
    if per_token is None:
        if limits.get('runtime_context'):
            return {**evidence, 'status':'LOADED_CONTEXT_ONLY', 'recommended_context':limits['runtime_context'], 'missing':['kv_cache'],
                    'label':'Already allocated by the engine. Chat cannot change it, and memory use at other sizes is unknown.',
                    'reason':'This engine does not report the layer sizes a memory estimate needs, so the loaded context is the only evidence.'}
        return {**insufficient, 'missing':['kv_cache'], 'reason':'This engine does not report the layer sizes a memory estimate needs.'}
    gpus = [g['free_bytes'] for g in snapshot.get('gpus', []) if type(g.get('free_bytes')) is int]
    weights = limits.get('weights_bytes')
    if not gpus or type(weights) is not int or weights <= 0:
        return {**insufficient, 'missing':['gpu_memory' if not gpus else 'model_resident_weights'],
                'reason':'GPU free memory or model size is unavailable, so feasibility cannot be estimated.'}
    # A reload replaces this model's own allocation; other users of the GPU stay.
    loaded = limits.get('loaded') or {}
    held = loaded.get('size_vram_bytes') if type(loaded.get('size_vram_bytes')) is int else 0
    available = max(gpus) + held
    maximum = limits.get('model_max_context')
    fits = []
    for context in CANDIDATES:
        required = int((weights + per_token * context) * HEADROOM) + RUNTIME_OVERHEAD
        if maximum and context > maximum:
            assessment = 'ABOVE_MODEL_MAX'
        elif required <= available:
            assessment = 'ESTIMATE_FITS_FREE_VRAM'
            fits.append(context)
        else:
            assessment = 'ESTIMATE_EXCEEDS_FREE_VRAM'
        evidence['candidates'].append({'context':context, 'estimated_required_bytes':required, 'assessment':assessment})
    return {**evidence, 'status':'ESTIMATE_UNVERIFIED' if fits else 'NO_ESTIMATED_FIT', 'recommended_context':max(fits, default=None),
            'label':UNVERIFIED, 'missing':['backend_placement','runtime_overhead'],
            'reason':'Estimated from model size and an upper bound on KV cache against free VRAM right now. Free VRAM changes as other applications run.'}


def compute_processes(tool):
    """Count only: NajdiLab has no need for names of other GPU applications."""
    try:
        query = subprocess.run([str(tool), '--query-compute-apps=pid', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), check=True)
        return len(query.stdout[:16384].split())
    except (OSError, subprocess.SubprocessError):
        return None


def snapshot(limits=None, limits_error=None):
    result = {'at':utc_now(), 'read_only':True, 'ram_total_bytes':None, 'ram_available_bytes':None, 'gpus':[], 'warnings':[]}
    try:
        if os.name == 'nt':
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(k, ctypes.c_ulonglong) for k in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                raise OSError
            result.update(ram_total_bytes=memory.total, ram_available_bytes=memory.available)
        else:
            with open('/proc/meminfo', encoding='ascii') as stream:
                raw = stream.read(65536)
            rows = {a:int(b.strip().split()[0])*1024 for a,b in (line.split(':',1) for line in raw.splitlines())}
            result.update(ram_total_bytes=rows.get('MemTotal'), ram_available_bytes=rows.get('MemAvailable'))
    except (OSError, ValueError, IndexError):
        result['warnings'].append('RAM_UNAVAILABLE')
    tool = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/nvidia-smi.exe' if os.name == 'nt' else Path('/usr/bin/nvidia-smi')
    if tool.is_file():
        try:
            query = subprocess.run([str(tool), '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=3, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), check=True)
            if len(query.stdout) > 16384:
                raise ValueError
            for row in list(csv.reader(query.stdout.splitlines()))[:32]:
                name, total, free = row
                total, free = int(total)*1024**2, int(free)*1024**2
                if not 0 <= free <= total:
                    raise ValueError
                result['gpus'].append({'name':name.strip()[:200], 'total_bytes':total, 'free_bytes':free, 'backend':'NVIDIA'})
            result['gpu_compute_processes'] = compute_processes(tool)
        except (OSError, ValueError, subprocess.SubprocessError):
            result['warnings'].append('GPU_MEMORY_UNAVAILABLE')
    else:
        result['warnings'].append('GPU_BACKEND_UNAVAILABLE')
    if limits_error:
        result['warnings'].append(limits_error)
    if limits:
        result['model'] = {k:limits.get(k) for k in ('architecture','quantization','weights_bytes','capabilities','model_system_prompt','other_loaded_models','engine_version')}
    result['recommendation'] = recommendation(result, limits)
    return result
