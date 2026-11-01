"""Explicit read-only host snapshot. No model allocation or stress test."""
import csv
import ctypes
import os
from pathlib import Path
import subprocess

from .db import utc_now


def recommendation(snapshot):
    return {'status':'INSUFFICIENT_EVIDENCE', 'recommended_context':None,
            'missing':['model_resident_weights','kv_cache','backend_placement','runtime_overhead','concurrent_allocations'],
            'reason':'Free RAM/VRAM and model disk size do not prove safe context. Loaded context is an engine ceiling only. No allocation test was run.'}


def snapshot():
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
        except (OSError, ValueError, subprocess.SubprocessError):
            result['warnings'].append('GPU_MEMORY_UNAVAILABLE')
    else:
        result['warnings'].append('GPU_BACKEND_UNAVAILABLE')
    result['recommendation'] = recommendation(result)
    return result
