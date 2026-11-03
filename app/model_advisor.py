"""Smart Model Advisor: may this GGUF file be downloaded, may it be loaded, and how will it run?

Three separate answers (docs/development/HUGGING_FACE_DIRECT.md §6):
- download: repository access, NajdiLab support for the file, and the storage preflight;
- load: COMPATIBLE, LIMITED, UNVERIFIED or BLOCKED for one context size and GPU setting;
- performance: where the model would run (GPU, split GPU/CPU, CPU) as a plain expectation.

Every figure carries its kind: measured (this computer, now), reported (Hugging Face or the GGUF
header), estimate (the shared formula in app/hardware.py) or unknown. Missing evidence gives
UNVERIFIED, never COMPATIBLE. Nothing here is sent anywhere.
"""
from __future__ import annotations

import os
import platform

from .hardware import CANDIDATES, HEADROOM, RUNTIME_OVERHEAD, kv_bytes_per_token

LABELS = {'COMPATIBLE', 'LIMITED', 'UNVERIFIED', 'BLOCKED'}


def host_profile(snapshot: dict | None, native_status: dict | None) -> dict:
    """Local facts only. `snapshot` comes from the approved read-only hardware snapshot."""
    native_status = native_status or {}
    devices = native_status.get('devices') or []
    profile = {'approved': snapshot is not None, 'os': f'{platform.system()} {platform.release()}'.strip(),
               'cpu_architecture': platform.machine() or None, 'cpu_count': os.cpu_count(),
               'ram_total_bytes': None, 'ram_available_bytes': None, 'gpus': [],
               'runtime': {'name': 'NajdiLab Native (llama.cpp llama-server)',
                           'server_available': bool(native_status.get('server_available')),
                           'server_path': native_status.get('server_path'),
                           'gpu_devices_seen_by_runtime': [{'name': d.get('name'), 'total_bytes': d.get('total_bytes')} for d in devices]}}
    if snapshot:
        profile['ram_total_bytes'] = snapshot.get('ram_total_bytes')
        profile['ram_available_bytes'] = snapshot.get('ram_available_bytes')
        profile['gpus'] = [{'name': g.get('name'), 'total_bytes': g.get('total_bytes'), 'free_bytes': g.get('free_bytes'),
                            'backend': g.get('backend')} for g in snapshot.get('gpus') or []]
        profile['warnings'] = list(snapshot.get('warnings') or [])
    return profile


def required_bytes(weights: int, per_token: int, context: int) -> int:
    return int((weights + per_token * context) * HEADROOM) + RUNTIME_OVERHEAD


def _reason(code, message):
    return {'code': code, 'message': message}


def assess(*, variant: dict, access: str, model: dict | None, host: dict, context: int, gpu_layers: str = 'auto',
           storage: dict | None = None) -> dict:
    """`variant`: file name/size/support from the repository; `model`: GGUF header facts (remote or local)."""
    model = model or {}
    size = variant.get('size_bytes')
    per_token = kv_bytes_per_token(model.get('kv'))
    max_context = model.get('model_max_context')
    evidence = [
        {'label': 'File size', 'value': size, 'unit': 'bytes', 'kind': 'reported' if size else 'unknown'},
        {'label': 'Architecture', 'value': model.get('architecture'), 'kind': 'reported' if model.get('architecture') else 'unknown'},
        {'label': 'Quantization', 'value': model.get('quantization') or variant.get('quantization'),
         'kind': 'reported' if (model.get('quantization') or variant.get('quantization')) else 'unknown'},
        {'label': 'Model maximum context', 'value': max_context, 'unit': 'tokens', 'kind': 'reported' if max_context else 'unknown'},
        {'label': 'KV cache per token (upper bound, f16)', 'value': per_token, 'unit': 'bytes', 'kind': 'estimate' if per_token else 'unknown'},
        {'label': 'System memory available now', 'value': host.get('ram_available_bytes'), 'unit': 'bytes',
         'kind': 'measured' if host.get('ram_available_bytes') else 'unknown'},
    ]
    for gpu in host.get('gpus') or []:
        evidence.append({'label': f"GPU memory free now: {gpu.get('name') or 'GPU'}", 'value': gpu.get('free_bytes'),
                         'unit': 'bytes', 'kind': 'measured' if type(gpu.get('free_bytes')) is int else 'unknown'})

    # ---- download --------------------------------------------------------
    download_reasons = []
    if access != 'OPEN':
        download_reasons.append(_reason('REPOSITORY_GATED', 'This repository needs an account and license approval on Hugging Face; NajdiLab does not bypass that.'))
    for code in variant.get('unsupported_reasons') or []:
        download_reasons.append(_reason(code, {
            'SPLIT_UNSUPPORTED': 'Split GGUF files (…-00001-of-0000N) are not supported yet.',
            'PROJECTOR_NOT_A_TEXT_MODEL': 'This is a vision projector file, not a text model.',
            'IN_SUBFOLDER': 'Only files at the top of the repository are supported.',
            'UNSAFE_FILE_NAME': 'The file name contains characters NajdiLab does not accept.',
            'SIZE_UNKNOWN': 'Hugging Face did not publish this file\'s size.',
            'DIGEST_UNKNOWN': 'Hugging Face did not publish this file\'s SHA-256, so it could not be verified.',
        }.get(code, 'This file is not supported.')))
    if storage and storage.get('decision') == 'BLOCKED':
        download_reasons.extend(storage.get('reasons') or [])
    download = {'decision': 'BLOCKED' if download_reasons else 'ALLOWED', 'reasons': download_reasons, 'storage': storage}

    # ---- load ------------------------------------------------------------
    blocked, unverified, limits = [], [], []
    if download_reasons and any(r['code'] != 'INSUFFICIENT_SPACE' for r in download_reasons):
        blocked.append(_reason('NOT_DOWNLOADABLE', 'This file cannot be downloaded through NajdiLab, so it cannot be loaded.'))
    if model.get('error'):
        unverified.append(_reason('HEADER_UNREADABLE', 'The GGUF header could not be read, so the architecture and memory needs are unknown.'))
    elif model.get('architecture') in ('clip',):
        blocked.append(_reason('NOT_A_TEXT_MODEL', 'This GGUF file is not a text model.'))
    elif not model.get('architecture'):
        unverified.append(_reason('ARCHITECTURE_UNKNOWN', 'The model architecture is unknown.'))
    if max_context and context > max_context:
        blocked.append(_reason('CONTEXT_ABOVE_MODEL_MAX', f'This model supports at most {max_context} tokens of context.'))
    runtime = host.get('runtime') or {}
    if not runtime.get('server_available'):
        blocked.append(_reason('NATIVE_SERVER_MISSING', 'No llama-server is configured for NajdiLab Native. NajdiLab never installs one; set NAJDILAB_NATIVE_SERVER to your own llama.cpp build.'))
    if not host.get('approved'):
        unverified.append(_reason('HARDWARE_NOT_READ', 'Read this computer\'s hardware first (it stays on this computer).'))
    if not per_token:
        unverified.append(_reason('KV_UNKNOWN', 'The header does not give the layer sizes needed for a memory estimate.'))
    if type(size) is not int:
        unverified.append(_reason('SIZE_UNKNOWN', 'The file size is unknown.'))

    estimate = None
    placement = 'UNKNOWN'
    recommended = gpu_recommended = None
    ram_free = host.get('ram_available_bytes') if type(host.get('ram_available_bytes')) is int else None
    ram_total = host.get('ram_total_bytes') if type(host.get('ram_total_bytes')) is int else None
    gpus = [g for g in host.get('gpus') or [] if type(g.get('free_bytes')) is int]
    runtime_sees_gpu = bool(runtime.get('gpu_devices_seen_by_runtime'))
    use_gpu = gpu_layers != '0' and gpus and (runtime_sees_gpu or not runtime.get('server_available'))
    gpu_free = max((g['free_bytes'] for g in gpus), default=0) if use_gpu else 0
    gpu_total = max((g.get('total_bytes') or 0 for g in gpus), default=0)
    if gpus and gpu_layers != '0' and runtime.get('server_available') and not runtime_sees_gpu:
        limits.append(_reason('RUNTIME_NO_GPU', 'This llama-server build does not report a GPU, so the model would run on the CPU.'))
    if host.get('approved') and ram_free is None:
        unverified.append(_reason('RAM_UNKNOWN', 'Available system memory could not be measured.'))

    def placement_for(needed):
        if use_gpu and needed <= gpu_free:
            return 'GPU'
        if use_gpu and gpu_layers != 'all' and ram_free is not None and needed <= gpu_free + ram_free:
            return 'PARTIAL_OFFLOAD'
        if ram_free is not None and needed <= ram_free and gpu_layers != 'all':
            return 'CPU'
        return None

    if per_token and type(size) is int:
        needed = required_bytes(size, per_token, context)
        estimate = {'context': context, 'weights_bytes': size, 'kv_bytes_per_token': per_token, 'kv_bytes': per_token * context,
                    'overhead_bytes': needed - size - per_token * context, 'required_bytes': needed, 'kind': 'estimate',
                    'formula': '(weights + KV per token × context) × 1.15 + 512 MiB, the same estimate Chat presets use'}
        if host.get('approved') and ram_free is not None:
            placement = placement_for(needed) or 'NONE'
            allowed = [c for c in CANDIDATES if not max_context or c <= max_context]
            recommended = max((c for c in allowed if placement_for(required_bytes(size, per_token, c))), default=None)
            gpu_recommended = max((c for c in allowed if placement_for(required_bytes(size, per_token, c)) == 'GPU'), default=None)
            if ram_total is not None and needed > ram_total + gpu_total:
                blocked.append(_reason('EXCEEDS_TOTAL_MEMORY', 'Even all of this computer\'s memory together is smaller than the estimate at this context.'))
            elif placement == 'NONE':
                blocked.append(_reason('INSUFFICIENT_FREE_MEMORY',
                                       'The estimate does not fit the memory free right now' + (' with all layers on the GPU' if gpu_layers == 'all' else '')
                                       + '. Choose a smaller context, a smaller quantization or Automatic GPU use, or close other programs.'))
            elif placement == 'PARTIAL_OFFLOAD':
                limits.append(_reason('PARTIAL_OFFLOAD', 'The estimate is larger than free GPU memory, so part of the model would run from system memory (slower).'))
            elif placement == 'CPU':
                limits.append(_reason('CPU_ONLY', 'The model would run on the CPU from system memory (much slower than a GPU).'))

    if blocked:
        label = 'BLOCKED'
    elif unverified:
        label = 'UNVERIFIED'
    elif limits:
        label = 'LIMITED'
    else:
        label = 'COMPATIBLE'
    reasons = blocked + unverified + limits
    if label == 'COMPATIBLE':
        reasons = [_reason('FITS_GPU', 'The estimate fits the GPU memory free right now, with every layer on the GPU. This is an estimate, not a load test.')]
    performance = {
        'GPU': 'If loaded, it would run fully on the GPU: the fastest option on this computer.',
        'PARTIAL_OFFLOAD': 'If loaded, it would be split between GPU and system memory: noticeably slower than full GPU use.',
        'CPU': 'If loaded, it would run on the CPU only: expect slow replies, especially for long prompts.',
    }.get(placement, 'Unknown until hardware and model details are available.')
    return {'download': download,
            'load': {'classification': label, 'reasons': reasons, 'recommended_context': recommended,
                     'largest_gpu_context': gpu_recommended,
                     'context': context, 'gpu_layers': gpu_layers},
            'performance': {'placement': placement, 'expectation': performance, 'kind': 'estimate'},
            'estimate': estimate, 'evidence': evidence, 'host': host,
            'note': 'Free memory changes as other programs run. Nothing is loaded or tested by this check.'}
