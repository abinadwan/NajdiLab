"""Offer the managed llama.cpp runtime for NajdiLab Native (run by scripts/install.py).

Explains what it will read and asks; then shows the pinned package (source, files, sizes, SHA-256,
licenses, destination) and asks again. Nothing is read or downloaded without a yes, and a
non-interactive run never downloads (docs/development/MANAGED_RUNTIME.md).
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.integrations import IntegrationError  # noqa: E402
from app.managed_runtime import ManagedRuntime  # noqa: E402
from app.native_runtime import NativeRuntime  # noqa: E402


def ask(question):
    try:
        return input(question + ' [y/N] ').strip().lower() in {'y', 'yes'}
    except EOFError:
        return False


def offer_runtime(interactive):
    """Explain the managed llama.cpp runtime, then install it only on an explicit yes."""
    if os.environ.get('NAJDILAB_NATIVE_SERVER'):
        print('llama.cpp runtime: NAJDILAB_NATIVE_SERVER is set, so your own llama-server is used. Nothing to install.')
        return
    later = 'Install it later with: python scripts/install.py --runtime   (or in the app: Model library > llama.cpp runtime)'
    if not interactive:
        print('llama.cpp runtime: not installed by a non-interactive setup. ' + later)
        return
    managed = ManagedRuntime(NativeRuntime())
    status = managed.status()
    if not status['platform']['supported']:
        print(f"llama.cpp runtime: no managed package for {status['platform']['system']} {status['platform']['machine']}. "
              'Set NAJDILAB_NATIVE_SERVER to your own llama-server to use NajdiLab Native.')
        return
    if status['active'] and not status['problems'] and not status['update_available']:
        print(f"llama.cpp runtime: {status['active']['package']} {status['active']['build']} is installed and verified.")
        return
    print()
    print('NajdiLab Native runs local GGUF models with llama.cpp (llama-server). NajdiLab can install the')
    print(f"official llama.cpp build {status['build']['tag']} ({status['build']['source']}) into data/native/runtime.")
    print('To choose the right package it reads, on this computer only, the operating system, the NVIDIA GPU model,')
    print("its compute capability and the driver's CUDA version (nvidia-smi). Nothing is sent anywhere.")
    if not ask('Check this computer now?'):
        print('Skipped. ' + later)
        return
    status = managed.detect({'approved': True})
    row = next((c for c in status['candidates'] if c['recommended']), None)
    for candidate in status['candidates']:
        if not candidate['eligible']:
            print(f"  not used: {candidate['id']}: {candidate['reasons'][0]['message']}")
    if row is None:
        print('No compatible package for this computer. ' + later)
        return
    preflight = row['preflight']
    print()
    print(f"Recommended package: {row['label']} ({row['id']}), llama.cpp {status['build']['tag']} commit {status['build']['commit']}")
    for asset in row['assets']:
        source = 'offline copy in data/native/runtime/archives' if asset['offline_copy'] else asset['url']
        print(f"  {asset['name']}  {asset['size'] / 1024 ** 2:.1f} MiB  SHA-256 {asset['sha256']}")
        print(f"    from {source}")
    print(f"Destination: {preflight['destination']}  (free now {preflight['free_bytes'] / 1024 ** 3:.1f} GiB; "
          f"needs {preflight['required_bytes'] / 1024 ** 3:.1f} GiB including the safety reserve)")
    print('Licenses: llama.cpp and nlohmann/json (MIT), LLVM OpenMP (Apache 2.0 with LLVM exceptions)'
          + (', NVIDIA CUDA runtime libraries (NVIDIA CUDA Toolkit EULA, https://docs.nvidia.com/cuda/eula/)'
             if any(a['name'].startswith('cudart-') for a in row['assets']) else '') + '.')
    print('Every archive is checked against its pinned SHA-256, then the build must prove its version and run a tiny')
    print('generated test model on the device before it is used. No model is downloaded or loaded.')
    if preflight['decision'] != 'ALLOWED':
        print('Not enough free space: ' + preflight['reasons'][0]['message'])
        return
    if not ask('Download and install this runtime now, accepting the licenses above?'):
        print('Skipped. ' + later)
        return
    try:
        status = managed.install({'approved': True, 'package': row['id'], 'license_acknowledged': True}, wait=True, progress=print)
    except IntegrationError as error:
        print(f'llama.cpp runtime was not installed: {error} ({error.code}). Nothing was changed.')
        return
    probe = status['active']['verification']['probe']
    where = f"{probe['device_name']} ({probe['layers_on_gpu']} layers on the GPU)" if probe.get('layers_on_gpu') else 'the CPU'
    print(f"llama.cpp runtime installed and verified: {status['active']['package']} {status['active']['build']}; test model ran on {where}.")


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


if __name__ == '__main__':
    offer_runtime(interactive())
