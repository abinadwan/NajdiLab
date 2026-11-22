"""The pinned llama.cpp build NajdiLab may install, and which of its packages fits this computer.

Boundaries (docs/development/MANAGED_RUNTIME.md):
- One official build, pinned by tag, commit and the SHA-256 of every archive (GitHub's published
  asset digests). No binary is stored in the repository.
- Detection is local and read-only: the operating system, the CPU architecture, NVIDIA GPUs from
  `nvidia-smi` (name, compute capability, driver and its CUDA version) and whether a Vulkan loader
  exists. Nothing is sent anywhere.
- Selection only narrows the choice. A package becomes active only after the installed build proves
  its identity and computes on the device (app/managed_runtime.py). Unknown facts fail closed.
"""
from __future__ import annotations

import ctypes.util
import csv
import os
from pathlib import Path
import platform
import re
import subprocess

BUILD = {'repository': 'ggml-org/llama.cpp', 'tag': 'b12059', 'build': 12059,
         'commit': '1b6935b227b9f9aa89deea8016c0e208f547446f', 'published': '2026-11-02',
         'license': 'MIT', 'source': 'https://github.com/ggml-org/llama.cpp/releases/tag/b12059'}
RELEASE_URL = 'https://github.com/ggml-org/llama.cpp/releases/download/b12059/'
X86_64 = {'amd64', 'x86_64'}


def _asset(name, size, sha256):
    return {'name': name, 'size': size, 'sha256': sha256, 'url': RELEASE_URL + name}


# `compute`: the NVIDIA compute capability range the CUDA toolkit of that build supports.
PACKAGES = (
    {'id': 'windows-x64-cuda-13.4', 'system': 'Windows', 'backend': 'CUDA', 'cuda': (13, 4), 'compute': ((7, 5), (12, 1)),
     'label': 'NVIDIA GPU (CUDA 13.4)', 'assets': (
        _asset('llama-b12059-bin-win-cuda-13.4-x64.zip', 168970005, 'a23c6ed880b3e0e6e8e64b735fb7e0b7a6c8f995bd876b3fc56e5ba5cccb85dd'),
        _asset('cudart-llama-bin-win-cuda-13.4-x64.zip', 423535356, '738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668'))},
    {'id': 'windows-x64-cuda-12.4', 'system': 'Windows', 'backend': 'CUDA', 'cuda': (12, 4), 'compute': ((5, 0), (9, 0)),
     'label': 'NVIDIA GPU (CUDA 12.4)', 'assets': (
        _asset('llama-b12059-bin-win-cuda-12.4-x64.zip', 286834526, '1ff41fa5d85b39919b3939fc44b9b1d51d9afda0a97a05c79051ec8b69bab0ad'),
        _asset('cudart-llama-bin-win-cuda-12.4-x64.zip', 391443627, '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'))},
    {'id': 'windows-x64-vulkan', 'system': 'Windows', 'backend': 'Vulkan', 'label': 'GPU through Vulkan', 'assets': (
        _asset('llama-b12059-bin-win-vulkan-x64.zip', 37535415, 'ad44d80c5a0293359c2ed9313b17f1199380d2e1ad99890399d231521971c32e'),)},
    {'id': 'windows-x64-cpu', 'system': 'Windows', 'backend': 'CPU', 'label': 'CPU only', 'assets': (
        _asset('llama-b12059-bin-win-cpu-x64.zip', 24592565, '25310083fad7da14ce7788a7f3c5d7536be19b82a099d2566a805e99864a6f91'),)},
    {'id': 'linux-x64-cuda-13.4', 'system': 'Linux', 'backend': 'CUDA', 'cuda': (13, 4), 'compute': ((7, 5), (12, 1)),
     'label': 'NVIDIA GPU (CUDA 13.4)', 'assets': (
        _asset('llama-b12059-bin-ubuntu-cuda-13.4-x64.tar.gz', 168000361, '450df1b86abba802de6d1be2651400571f6638a0b14ac9e78b4189bffb1788bc'),
        _asset('cudart-llama-b12059-bin-ubuntu-cuda-13.4-x64.tar.gz', 440232323, '9d72de6d65637c5c21d5b66f6d9047ea3c65cc20d3c1c12d7f69a0c901271a08'))},
    {'id': 'linux-x64-cuda-12.8', 'system': 'Linux', 'backend': 'CUDA', 'cuda': (12, 8), 'compute': ((5, 0), (12, 0)),
     'label': 'NVIDIA GPU (CUDA 12.8)', 'assets': (
        _asset('llama-b12059-bin-ubuntu-cuda-12.8-x64.tar.gz', 187068380, '4b877b6df8fb44a8885280ed7defb625489154c6e71c679bb19e715afd4b1b52'),
        _asset('cudart-llama-b12059-bin-ubuntu-cuda-12.8-x64.tar.gz', 594371449, 'd6d0801fd59923ecb1e7aed398fcdee3e7fcf07d2d074e885809170e49978d6f'))},
    {'id': 'linux-x64-vulkan', 'system': 'Linux', 'backend': 'Vulkan', 'label': 'GPU through Vulkan', 'assets': (
        _asset('llama-b12059-bin-ubuntu-vulkan-x64.tar.gz', 35719894, '835764d2596fa79719992858f0a5ccfb73eba96f38f164e1fa4f51101a4678f0'),)},
    {'id': 'linux-x64-cpu', 'system': 'Linux', 'backend': 'CPU', 'label': 'CPU only', 'assets': (
        _asset('llama-b12059-bin-ubuntu-x64.tar.gz', 22912892, 'cfb45331bf4ab9af5834dedfed77ec10d531a83de9a2dc05a03d3e131c7cdb12'),)},
)
# Packages that passed acceptance on real hardware (docs/development/MANAGED_RUNTIME.md §8).
TESTED = {'windows-x64-cuda-13.4', 'windows-x64-cpu'}

# The Windows archives do not contain llama.cpp's own license files, so each install gets them.
LLAMA_LICENSE = '''MIT License

Copyright (c) 2023-2026 The ggml authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
JSON_LICENSE = LLAMA_LICENSE.replace('2023-2026 The ggml authors', '2013-2025 Niels Lohmann')


def notices(package: dict) -> dict:
    """File name → text for the install's NOTICES folder."""
    cuda = any(a['name'].startswith('cudart-') for a in package['assets'])
    readme = (f"llama.cpp {BUILD['tag']} (commit {BUILD['commit']}), package {package['id']}.\n"
              f"Source: {BUILD['source']}\nInstalled by NajdiLab from the official release archives; nothing was modified.\n\n"
              'llama.cpp: MIT License (LICENSE-llama.cpp.txt). Bundled nlohmann/json: MIT (LICENSE-jsonhpp.txt).\n'
              'LLVM OpenMP (Windows archives): see LICENSE-LLVM-OpenMP next to the program, as shipped.\n')
    if cuda:
        readme += ('NVIDIA CUDA runtime libraries (cudart, cuBLAS) come from the llama.cpp release and are governed by the\n'
                   'NVIDIA CUDA Toolkit End User License Agreement: https://docs.nvidia.com/cuda/eula/\n')
    return {'README.txt': readme, 'LICENSE-llama.cpp.txt': LLAMA_LICENSE, 'LICENSE-jsonhpp.txt': JSON_LICENSE}


def server_name(system: str) -> str:
    return 'llama-server.exe' if system == 'Windows' else 'llama-server'


# ----- detection -----------------------------------------------------------
def _nvidia_smi() -> Path:
    return Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/nvidia-smi.exe' if os.name == 'nt' else Path('/usr/bin/nvidia-smi')


def _version(text):
    match = re.fullmatch(r'\s*(\d{1,3})\.(\d{1,3})\s*', text or '')
    return (int(match[1]), int(match[2])) if match else None


def detect_host(run=subprocess.run) -> dict:
    """Local, read-only facts. Other programs using the GPU are never read or named."""
    host = {'system': platform.system(), 'machine': platform.machine(), 'nvidia': [], 'driver_version': None,
            'driver_cuda': None, 'vulkan_loader': False, 'warnings': []}
    tool = _nvidia_smi()
    if tool.is_file():
        flags = {'capture_output': True, 'text': True, 'timeout': 5, 'check': True,
                 'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        try:
            query = run([str(tool), '--query-gpu=name,compute_cap,driver_version,memory.total',
                         '--format=csv,noheader,nounits'], **flags)
            for row in list(csv.reader(query.stdout[:16384].splitlines()))[:16]:
                if len(row) != 4:
                    raise ValueError
                name, cap, driver, total = (v.strip() for v in row)
                host['nvidia'].append({'name': name[:200], 'compute_capability': _version(cap),
                                       'total_bytes': int(total) * 1024 ** 2 if total.isdigit() else None})
                host['driver_version'] = driver[:32] or None
            # The summary header names the newest CUDA version this driver supports. Only that line is read.
            header = run([str(tool)], **flags).stdout[:4096]
            match = re.search(r'CUDA (?:UMD )?Version:\s*(\d{1,3}\.\d{1,3})', header)
            host['driver_cuda'] = _version(match[1]) if match else None
        except (OSError, ValueError, subprocess.SubprocessError):
            host['warnings'].append('NVIDIA_QUERY_FAILED')
    if os.name == 'nt':
        host['vulkan_loader'] = (Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/vulkan-1.dll').is_file()
    else:
        host['vulkan_loader'] = ctypes.util.find_library('vulkan') is not None
    return host


def supported(system: str, machine: str) -> bool:
    return machine.lower() in X86_64 and any(p['system'] == system for p in PACKAGES)


def _reason(code, message):
    return {'code': code, 'message': message}


def assess(package: dict, host: dict) -> list:
    """Reasons this package cannot be used here; empty when it may be installed and probed."""
    if package['system'] != host['system'] or (host['machine'] or '').lower() not in X86_64:
        return [_reason('UNSUPPORTED_PLATFORM', 'This package is for another operating system or processor.')]
    reasons = []
    if package['backend'] == 'CUDA':
        low, high = package['compute']
        need = '.'.join(map(str, package['cuda']))
        if not host['nvidia']:
            reasons.append(_reason('NO_NVIDIA_GPU', 'No NVIDIA GPU was found by nvidia-smi.'))
        elif any(g['compute_capability'] is None for g in host['nvidia']):
            reasons.append(_reason('COMPUTE_CAPABILITY_UNKNOWN', 'The GPU compute capability could not be read, so CUDA compatibility is unknown.'))
        elif not all(low <= g['compute_capability'] <= high for g in host['nvidia']):
            reasons.append(_reason('GPU_ARCHITECTURE_UNSUPPORTED',
                                   f'CUDA {need} supports compute capability {low[0]}.{low[1]} to {high[0]}.{high[1]}; this GPU is outside that range.'))
        if host['nvidia'] and host['driver_cuda'] is None:
            reasons.append(_reason('DRIVER_CUDA_UNKNOWN', 'The NVIDIA driver did not report which CUDA version it supports.'))
        elif host['nvidia'] and host['driver_cuda'] < package['cuda']:
            reasons.append(_reason('DRIVER_TOO_OLD', f'This NVIDIA driver supports CUDA up to {host["driver_cuda"][0]}.{host["driver_cuda"][1]}; this package needs {need}. Update the driver or choose another package.'))
    elif package['backend'] == 'Vulkan' and not host['vulkan_loader']:
        reasons.append(_reason('NO_VULKAN_LOADER', 'No Vulkan loader was found (vulkan-1.dll or libvulkan), so the Vulkan build cannot use a GPU.'))
    return reasons


def candidates(host: dict) -> list:
    """Packages for this system, best first: newest eligible CUDA, then Vulkan, then CPU."""
    rank = {'CUDA': 0, 'Vulkan': 1, 'CPU': 2}
    own = [p for p in PACKAGES if p['system'] == host['system']]
    own.sort(key=lambda p: (rank[p['backend']], tuple(-v for v in p.get('cuda', (0, 0)))))
    return [{'package': p, 'reasons': assess(p, host)} for p in own]
