from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import training_control as training

RUNTIMES_FILE = training.TRAINING_ROOT / "runtimes.json"
RUNTIME_ROOT = training.TRAINING_ROOT / "runtime"
RUNTIME_CHECK_MAX_AGE_SECONDS = 600
WORKER_HEARTBEAT_MAX_AGE_SECONDS = 90
SAFE_ENV_KEYS = {"CUDA_VISIBLE_DEVICES", "PYTHONUNBUFFERED", "TOKENIZERS_PARALLELISM"}
REQUIRED_PACKAGES = ("torch", "unsloth", "transformers", "bitsandbytes", "peft", "accelerate")
WORKER_STATES = {"OFFLINE", "IDLE", "BUSY", "ERROR"}
AUTH_TTL_SECONDS = 300
ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
ACTIVE_LOCK = threading.Lock()


def _parse_time(value: str | None) -> datetime | None:
    if not value: return None
    try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError): return None


def _age_seconds(value: str | None, now: datetime | None = None) -> float | None:
    parsed = _parse_time(value)
    if parsed is None: return None
    return max(0.0, ((now or datetime.now(timezone.utc)) - parsed).total_seconds())


def _posix_path(value: Any, field: str) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or not path.is_absolute() or ".." in path.parts or any(ord(ch) < 32 for ch in text):
        raise training.TrainingControlError("INVALID_RUNTIME", f"{field} is not a safe absolute WSL path")
    return text


def initialize_runtime_control() -> None:
    training.initialize_training_control(); RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if not RUNTIMES_FILE.exists():
        training._atomic_json(RUNTIMES_FILE, {"runtimes": [{
            "id": "najditrain-wsl", "display_name": "NajdiTrain WSL2", "type": "WSL2", "enabled": True,
            "host_os": "Windows", "wsl_distro": "NajdiTrain", "linux_user": "najdi",
            "project_root": "/home/najdi/najdi-training", "python_path": "/home/najdi/najdi-training/.venv/bin/python",
            "venv_path": "/home/najdi/najdi-training/.venv", "training_script_path": "/home/najdi/najdi-training/scripts/najdilab_training_adapter.py",
            "dataset_root": "/home/najdi/najdi-training/data/najdilab", "default_output_root": "/home/najdi/najdi-training/runs",
            "checkpoint_root": "/home/najdi/najdi-training/checkpoints", "logs_root": "/home/najdi/najdi-training/logs",
            "notes": "Configurable local runtime. The adapter contract is prepared but training execution is not implemented in Phase 2-B1.",
        }]})
    for runtime in list_runtimes():
        path = _worker_path(runtime["id"])
        if not path.exists():
            training._atomic_json(path, {"runtime_id": runtime["id"], "state": "OFFLINE", "pid": None,
                "current_job_id": None, "started_at": None, "heartbeat_at": None, "last_error": None,
                "capabilities": ["runtime_check", "execution_gate", "dry_run"], "worker_version": "2-B1"})


def list_runtimes() -> list[dict[str, Any]]:
    if not RUNTIMES_FILE.exists():
        initialize_runtime_control()
    value = json.loads(RUNTIMES_FILE.read_text(encoding="utf-8"))
    return value.get("runtimes", []) if isinstance(value, dict) else []


def get_runtime(runtime_id: str) -> dict[str, Any]:
    if not training.SAFE_ID.fullmatch(runtime_id): raise training.TrainingControlError("RUNTIME_NOT_FOUND", "Invalid runtime ID", status=404)
    runtime = next((item for item in list_runtimes() if item.get("id") == runtime_id), None)
    if not runtime: raise training.TrainingControlError("RUNTIME_NOT_FOUND", "Runtime is not registered", status=404)
    return runtime


def register_runtime(data: dict[str, Any]) -> dict[str, Any]:
    runtime_id = str(data.get("id") or "")
    if not training.SAFE_ID.fullmatch(runtime_id): raise training.TrainingControlError("INVALID_RUNTIME", "Invalid runtime ID")
    if str(data.get("type")) != "WSL2": raise training.TrainingControlError("INVALID_RUNTIME", "Phase 2-B1 supports WSL2 only")
    distro = str(data.get("wsl_distro") or "")
    if not training.SAFE_ID.fullmatch(distro): raise training.TrainingControlError("INVALID_RUNTIME", "Invalid WSL distribution name")
    runtimes = list_runtimes()
    if any(item.get("id") == runtime_id for item in runtimes): raise training.TrainingControlError("RUNTIME_EXISTS", "Runtime ID is already in use", status=409)
    fields = ("project_root", "python_path", "venv_path", "training_script_path", "dataset_root", "default_output_root", "checkpoint_root", "logs_root")
    runtime = {"id": runtime_id, "display_name": str(data.get("display_name") or runtime_id), "type": "WSL2",
        "enabled": bool(data.get("enabled", True)), "host_os": "Windows", "wsl_distro": distro,
        "linux_user": str(data.get("linux_user") or ""), **{field: _posix_path(data.get(field), field) for field in fields},
        "notes": data.get("notes")}
    runtimes.append(runtime); training._atomic_json(RUNTIMES_FILE, {"runtimes": runtimes}); return runtime


def _runtime_dir(runtime_id: str) -> Path:
    if not training.SAFE_ID.fullmatch(runtime_id): raise training.TrainingControlError("RUNTIME_NOT_FOUND", "Invalid runtime ID", status=404)
    return RUNTIME_ROOT / runtime_id


def _runtime_result_path(runtime_id: str) -> Path: return _runtime_dir(runtime_id) / "latest-check.json"
def _worker_path(runtime_id: str) -> Path: return _runtime_dir(runtime_id) / "worker-state.json"


def get_runtime_result(runtime_id: str) -> dict[str, Any] | None:
    get_runtime(runtime_id); path = _runtime_result_path(runtime_id)
    if not path.is_file(): return None
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return None


def get_worker_state(runtime_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    get_runtime(runtime_id); path = _worker_path(runtime_id)
    if not path.is_file(): initialize_runtime_control()
    state = json.loads(path.read_text(encoding="utf-8")); age = _age_seconds(state.get("heartbeat_at"), now)
    freshness = "NO_HEARTBEAT" if age is None else "FRESH" if age <= WORKER_HEARTBEAT_MAX_AGE_SECONDS else "STALE"
    return {**state, "heartbeat_freshness": freshness, "heartbeat_age_seconds": None if age is None else round(age, 1),
        "heartbeat_max_age_seconds": WORKER_HEARTBEAT_MAX_AGE_SECONDS}


def set_worker_state(runtime_id: str, state: str, *, current_job_id: str | None = None, error: str | None = None, heartbeat: bool = True) -> dict[str, Any]:
    if state not in WORKER_STATES: raise training.TrainingControlError("INVALID_WORKER_STATE", "Invalid worker state")
    current = get_worker_state(runtime_id); now = training._now()
    updated = {key: current.get(key) for key in ("runtime_id", "pid", "started_at", "capabilities", "worker_version")}
    updated.update({"state": state, "current_job_id": current_job_id, "heartbeat_at": now if heartbeat else current.get("heartbeat_at"), "last_error": error})
    if state == "IDLE" and not updated.get("started_at"): updated["started_at"] = now
    training._atomic_json(_worker_path(runtime_id), updated); return get_worker_state(runtime_id)


def _run(command: list[str], timeout: int = 12) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return subprocess.CompletedProcess(result.args, result.returncode, (result.stdout or "")[:65536], (result.stderr or "")[:65536])


def _wsl(runtime: dict[str, Any], args: list[str], timeout: int = 12, runner: Callable[..., subprocess.CompletedProcess[str]] = _run) -> subprocess.CompletedProcess[str]:
    return runner(["wsl.exe", "-d", runtime["wsl_distro"], "--", *args], timeout)


def probe_live_gpu(runtime: dict[str, Any], *, runner: Callable[..., subprocess.CompletedProcess[str]] = _run) -> dict[str, Any]:
    """Measure CUDA memory in the interpreter that will execute training.

    This probe is intentionally uncached. Persisted runtime GPU values are useful
    diagnostics, but they are not authoritative for execution eligibility.
    """
    observed_at = training._now()
    probe = """import json,torch
if not torch.cuda.is_available(): raise RuntimeError('CUDA is not available')
free,total=torch.cuda.mem_get_info(); p=torch.cuda.get_device_properties(torch.cuda.current_device())
print(json.dumps({'gpu_name':p.name,'free_bytes':int(free),'total_bytes':int(total),'used_bytes':int(total-free)}))"""
    try:
        primary = _wsl(runtime, [runtime["python_path"], "-c", probe], 20, runner)
    except (OSError, subprocess.TimeoutExpired) as exc:
        primary = None; primary_error = f"{type(exc).__name__}: {exc}"
    else:
        primary_error = (primary.stderr or "")[-2000:]

    secondary: dict[str, Any] = {"source": "wsl:nvidia-smi", "success": False}
    try:
        smi = _wsl(runtime, ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version", "--format=csv,noheader,nounits"], 12, runner)
        if smi.returncode == 0 and smi.stdout.strip():
            values = [value.strip() for value in smi.stdout.splitlines()[0].split(",")]
            secondary.update({"success": True, "gpu_name": values[0], "total_mib": float(values[1]), "used_mib": float(values[2]), "free_mib": float(values[3]), "driver": values[4] if len(values) > 4 else None})
        else: secondary["error"] = (smi.stderr or "nvidia-smi returned no data")[-2000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        secondary["error"] = f"{type(exc).__name__}: {exc}"

    result: dict[str, Any] = {"measurement": "LIVE", "probe_source": "torch.cuda.mem_get_info", "observed_at": observed_at,
        "units": {"bytes": "bytes", "mib": "MiB", "gib": "GiB"}, "success": False, "secondary_diagnostic": secondary}
    if primary is None or primary.returncode != 0:
        result["error"] = primary_error or "Live CUDA probe failed"
    else:
        try:
            payload = json.loads(primary.stdout.strip().splitlines()[-1]); free = int(payload["free_bytes"]); total = int(payload["total_bytes"]); used = int(payload["used_bytes"])
            result.update({"success": True, "gpu_name": payload.get("gpu_name"), "total_bytes": total, "used_bytes": used, "free_bytes": free,
                "total_mib": round(total / 1024**2, 2), "used_mib": round(used / 1024**2, 2), "free_mib": round(free / 1024**2, 2),
                "total_gib": round(total / 1024**3, 4), "used_gib": round(used / 1024**3, 4), "free_gib": round(free / 1024**3, 4)})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, IndexError) as exc:
            result["error"] = f"Invalid live CUDA probe result: {type(exc).__name__}: {exc}"
    runtime_dir = _runtime_dir(runtime["id"]); runtime_dir.mkdir(parents=True, exist_ok=True)
    training._atomic_json(runtime_dir / "live-gpu-check.json", result)
    with (runtime_dir / "live-gpu-checks.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


def _check(name: str, passed: bool, value: Any = None, details: str = "", code: str | None = None, warning: bool = False) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if passed else "WARN" if warning else "FAIL", "value": value, "details": str(details or "")[:2000], "code": None if passed else code}


def _decode_wsl_list(raw: bytes | str) -> str:
    if isinstance(raw, str): return raw.replace("\x00", "")
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = raw.decode(encoding)
            if text.strip(): return text.replace("\x00", "")
        except UnicodeError: pass
    return raw.decode("utf-8", errors="replace").replace("\x00", "")


def check_runtime(runtime_id: str, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _run) -> dict[str, Any]:
    runtime = get_runtime(runtime_id); checked_at = training._now(); checks: list[dict[str, Any]] = []; detected: dict[str, Any] = {}
    if not runtime.get("enabled"):
        result = {"runtime_id": runtime_id, "status": "UNAVAILABLE", "checks": [_check("runtime_enabled", False, False, "Runtime disabled", "RUNTIME_DISABLED")], "blockers": ["RUNTIME_DISABLED"], "warnings": [], "detected": {}, "checked_at": checked_at, "runtime_fingerprint": None}
        training._atomic_json(_runtime_result_path(runtime_id), result); return result
    try:
        listed = runner(["wsl.exe", "--list", "--verbose"], 12)
    except FileNotFoundError:
        listed = None; checks.append(_check("wsl_available", False, False, "wsl.exe not found", "WSL_NOT_AVAILABLE"))
    except (OSError, subprocess.TimeoutExpired) as exc:
        listed = None; checks.append(_check("wsl_available", False, False, str(exc), "WSL_EXEC_FAILED"))
    if listed is not None:
        text = _decode_wsl_list(listed.stdout); lines = [line.strip().lstrip("*").strip() for line in text.splitlines() if line.strip()]
        distros = []
        if listed.returncode == 0:
            for line in lines[1:]:
                parts = line.rsplit(None, 2)
                if parts: distros.append({"name": parts[0], "state": parts[1] if len(parts) > 1 else "UNKNOWN", "version": parts[2] if len(parts) > 2 else None})
        detected["wsl_distros"] = distros; target = next((item for item in distros if item["name"] == runtime["wsl_distro"]), None)
        checks.append(_check("wsl_available", listed.returncode == 0, listed.returncode == 0, (text+"\n"+listed.stderr).strip(), "WSL_EXEC_FAILED" if listed.returncode else "WSL_NOT_AVAILABLE"))
        if listed.returncode == 0: checks.append(_check("wsl_distro", target is not None, target, f"Target: {runtime['wsl_distro']}", "WSL_DISTRO_NOT_FOUND"))
    else: target = None
    if target is not None:
        probe = """import importlib,json,os,platform,sys
pkgs={}
for name in ('pip','torch','unsloth','transformers','bitsandbytes','peft','accelerate'):
 try:
  m=importlib.import_module(name); pkgs[name]={'available':True,'version':getattr(m,'__version__',None)}
 except Exception as e: pkgs[name]={'available':False,'error':type(e).__name__+': '+str(e)[:300]}
t=pkgs.get('torch',{}); cuda=False; cv=None
if t.get('available'):
 import torch; cuda=bool(torch.cuda.is_available()); cv=getattr(torch.version,'cuda',None)
print(json.dumps({'user':os.environ.get('USER'),'python':sys.version.split()[0],'packages':pkgs,'cuda_available':cuda,'torch_cuda_version':cv,'platform':platform.platform()}))"""
        try: py = _wsl(runtime, [runtime["python_path"], "-c", probe], 25, runner)
        except (OSError, subprocess.TimeoutExpired) as exc: py = None; checks.append(_check("wsl_shell", False, None, str(exc), "WSL_EXEC_FAILED"))
        if py is not None:
            checks.append(_check("wsl_shell", py.returncode == 0, py.returncode, py.stderr, "WSL_EXEC_FAILED"))
            try: info = json.loads(py.stdout.strip().splitlines()[-1]) if py.returncode == 0 else {}
            except (json.JSONDecodeError, IndexError): info = {}
            detected.update({key: info.get(key) for key in ("user", "python", "platform", "cuda_available", "torch_cuda_version")}); detected["packages"] = info.get("packages", {}); detected["pip"] = (info.get("packages") or {}).get("pip", {}).get("version")
            checks.append(_check("python", bool(info.get("python")), info.get("python"), py.stderr, "PYTHON_NOT_FOUND"))
            checks.append(_check("pip", bool(detected.get("pip")), detected.get("pip"), "pip is useful for maintenance but is not required to execute an already provisioned stack", "PIP_NOT_AVAILABLE", warning=True))
            for pkg in REQUIRED_PACKAGES:
                item = (info.get("packages") or {}).get(pkg, {}); code = {"torch":"TORCH_NOT_AVAILABLE","unsloth":"UNSLOTH_NOT_AVAILABLE"}.get(pkg, f"{pkg.upper()}_NOT_AVAILABLE")
                checks.append(_check(pkg, bool(item.get("available")), item.get("version"), item.get("error", ""), code))
            checks.append(_check("cuda_available", bool(info.get("cuda_available")), info.get("cuda_available"), f"torch CUDA {info.get('torch_cuda_version')}", "CUDA_NOT_AVAILABLE"))
        default_model = next((item for item in training.list_models() if item.get("enabled")), {})
        path_payload = json.dumps({"paths": {"project": runtime["project_root"], "python": runtime["python_path"], "venv": runtime["venv_path"], "script": runtime["training_script_path"],
            "dataset_root": str(PurePosixPath(runtime["dataset_root"]) / "gold-v008-split-clean"), "model": default_model.get("path", ""),
            "output": runtime["default_output_root"], "checkpoint": runtime["checkpoint_root"], "logs": runtime["logs_root"]}})
        path_probe = """import hashlib,json,os,sys
p=json.loads(sys.argv[1])['paths']; result={}
for k,v in p.items():
 item={'exists':os.path.exists(v),'is_file':os.path.isfile(v),'writable':os.access(v if os.path.exists(v) else os.path.dirname(v),os.W_OK)}
 if os.path.isfile(v): item['sha256']=hashlib.sha256(open(v,'rb').read()).hexdigest()
 if k=='model' and os.path.isdir(v):
  item['size_bytes']=sum(os.path.getsize(os.path.join(root,f)) for root,_,files in os.walk(v) for f in files if os.path.isfile(os.path.join(root,f)))
  cfg=os.path.join(v,'config.json'); item['config_sha256']=hashlib.sha256(open(cfg,'rb').read()).hexdigest() if os.path.isfile(cfg) else None
  item['tokenizer_exists']=any(os.path.isfile(os.path.join(v,n)) for n in ('tokenizer.json','tokenizer.model','tokenizer_config.json'))
 result[k]=item
print(json.dumps(result))"""
        try: paths_run = _wsl(runtime, [runtime["python_path"], "-c", path_probe, path_payload], 12, runner); path_info = json.loads(paths_run.stdout.strip().splitlines()[-1]) if paths_run.returncode == 0 else {}
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError): path_info = {}
        detected["paths"] = path_info
        path_codes = {"project":"PROJECT_PATH_NOT_ACCESSIBLE","python":"PYTHON_NOT_FOUND","venv":"VENV_NOT_FOUND","script":"TRAINING_SCRIPT_NOT_FOUND","dataset_root":"DATASET_PATH_NOT_ACCESSIBLE","model":"MODEL_PATH_NOT_ACCESSIBLE","output":"OUTPUT_NOT_WRITABLE","checkpoint":"OUTPUT_NOT_WRITABLE","logs":"OUTPUT_NOT_WRITABLE"}
        for key, code in path_codes.items():
            item = path_info.get(key, {}); needed = item.get("is_file") if key in {"python", "script"} else item.get("exists")
            if key in {"output", "checkpoint", "logs"}: needed = item.get("writable")
            checks.append(_check(f"path_{key}", bool(needed), item, runtime.get(key if key != "project" else "project_root"), code, warning=key == "script"))
        smi_args = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version", "--format=csv,noheader,nounits"]
        try: smi = _wsl(runtime, smi_args, 12, runner)
        except (OSError, subprocess.TimeoutExpired): smi = None
        if smi and smi.returncode == 0 and smi.stdout.strip():
            values = [x.strip() for x in smi.stdout.splitlines()[0].split(",")]; gpu = {"name": values[0], "total_vram_mb": float(values[1]), "used_vram_mb": float(values[2]), "free_vram_mb": float(values[3]), "driver": values[4] if len(values)>4 else None}; detected["gpu"] = gpu
            checks.append(_check("gpu", True, gpu["name"], smi.stdout));
        else: checks.append(_check("gpu", False, None, smi.stderr if smi else "nvidia-smi failed", "GPU_NOT_FOUND"))
        try:
            smi_full = _wsl(runtime, ["nvidia-smi"], 12, runner); match = re.search(r"CUDA Version:\s*([0-9.]+)", smi_full.stdout)
            detected["nvidia_smi_cuda_version"] = match.group(1) if match else None
        except (OSError, subprocess.TimeoutExpired): detected["nvidia_smi_cuda_version"] = None
        try:
            refreshed = runner(["wsl.exe", "--list", "--verbose"], 12); refreshed_text = _decode_wsl_list(refreshed.stdout)
            target_line = next((line for line in refreshed_text.splitlines() if runtime["wsl_distro"] in line), "")
            if target_line: detected["target_distro_state_after_check"] = "Running" if "Running" in target_line else "Stopped" if "Stopped" in target_line else "UNKNOWN"
        except (OSError, subprocess.TimeoutExpired): pass
    blockers = [item["code"] for item in checks if item["status"] == "FAIL" and item.get("code")]
    warnings = [item["code"] for item in checks if item["status"] == "WARN" and item.get("code")]
    canonical = json.dumps({"runtime": runtime, "detected": detected}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    status = "ERROR" if "WSL_EXEC_FAILED" in blockers else "UNAVAILABLE" if blockers else "AVAILABLE_WITH_WARNINGS" if warnings else "AVAILABLE"
    result = {"runtime_id": runtime_id, "status": status, "checks": checks, "blockers": blockers, "warnings": warnings,
        "detected": detected, "checked_at": checked_at, "runtime_fingerprint": hashlib.sha256(canonical).hexdigest(),
        "max_age_seconds": RUNTIME_CHECK_MAX_AGE_SECONDS}
    training._atomic_json(_runtime_result_path(runtime_id), result)
    set_worker_state(runtime_id, "IDLE" if status in {"AVAILABLE", "AVAILABLE_WITH_WARNINGS"} else "OFFLINE", error=None if not blockers else ", ".join(blockers))
    return result


def _windows_to_wsl(path: Path) -> str:
    resolved = path.resolve(); drive = resolved.drive.rstrip(":").lower()
    if not drive: raise training.TrainingControlError("STAGING_FAILED", "Source path is not on a Windows drive")
    return f"/mnt/{drive}/" + resolved.as_posix().split(":/", 1)[1]


def staging_status(runtime_id: str, version: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id); gate = training.quality_gate(version); destination = str(PurePosixPath(runtime["dataset_root"]) / version)
    probe = """import hashlib,json,os,sys
d=sys.argv[1]; result={'path':d,'exists':os.path.isdir(d),'valid':False}
mp=os.path.join(d,'staging-manifest.json')
if os.path.isfile(mp):
 m=json.load(open(mp)); result['manifest']=m; result['valid']=all(os.path.isfile(os.path.join(d,n)) and hashlib.sha256(open(os.path.join(d,n),'rb').read()).hexdigest()==h for n,h in m.get('staged_sha256',{}).items())
print(json.dumps(result))"""
    try: run = _wsl(runtime, [runtime["python_path"], "-c", probe, destination], 20); found = json.loads(run.stdout.strip().splitlines()[-1])
    except Exception: found = {"path":destination,"exists":False,"valid":False}
    manifest = found.get("manifest") or {}; fingerprint_ok = manifest.get("source_fingerprint") == gate.get("dataset_fingerprint")
    return {**found,"runtime_id":runtime_id,"dataset_version":version,"fingerprint_matches":fingerprint_ok,
        "status":"PASS" if found.get("valid") and fingerprint_ok else "MISSING" if not found.get("exists") else "STALE"}


def stage_dataset(runtime_id: str, version: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id); gate = training.quality_gate(version)
    if gate["status"] not in {"PASS","PASS_WITH_WARNINGS"}: raise training.TrainingControlError("QUALITY_GATE_BLOCKED","Dataset cannot be staged",status=409)
    source = training._version_dir(version); names = ["sft.jsonl","multi_turn.jsonl","loss-mask-validation.json","manifest.json"]
    names += [name for name in ("native_tool_use.jsonl","capability-registry.json","native-tool-loss-mask-validation.json") if (source/name).is_file()]
    source_hashes = {name:training._sha256(source/name) for name in names}; destination = str(PurePosixPath(runtime["dataset_root"]) / version)
    payload={"source":_windows_to_wsl(source),"destination":destination,"files":names,"hashes":source_hashes,"fingerprint":gate["dataset_fingerprint"],"runtime_id":runtime_id,"version":version,"staged_at":training._now()}
    script="""import hashlib,json,os,shutil,sys,uuid
p=json.loads(sys.argv[1]); dest=p['destination']; parent=os.path.dirname(dest); os.makedirs(parent,exist_ok=True); tmp=dest+'.staging-'+uuid.uuid4().hex; os.makedirs(tmp)
try:
 for n in p['files']:
  shutil.copy2(os.path.join(p['source'],n),os.path.join(tmp,n))
 staged={n:hashlib.sha256(open(os.path.join(tmp,n),'rb').read()).hexdigest() for n in p['files']}
 if staged!=p['hashes']: raise RuntimeError('staged SHA-256 mismatch')
 m={'dataset_version':p['version'],'source_fingerprint':p['fingerprint'],'source_files':p['files'],'source_sha256':p['hashes'],'staged_files':p['files'],'staged_sha256':staged,'staged_at':p['staged_at'],'runtime_id':p['runtime_id'],'immutable':True,'validation_result':'PASS'}
 open(os.path.join(tmp,'staging-manifest.json'),'w').write(json.dumps(m,indent=2)+'\\n')
 if os.path.exists(dest):
  old=json.load(open(os.path.join(dest,'staging-manifest.json'))) if os.path.isfile(os.path.join(dest,'staging-manifest.json')) else {}
  if old.get('source_fingerprint')!=p['fingerprint']: raise RuntimeError('destination exists with different fingerprint')
  shutil.rmtree(tmp); print(json.dumps(m)); sys.exit(0)
 os.rename(tmp,dest); print(json.dumps(m))
except Exception:
 shutil.rmtree(tmp,ignore_errors=True); raise"""
    run=_wsl(runtime,[runtime["python_path"],"-c",script,json.dumps(payload)],60)
    if run.returncode!=0: raise training.TrainingControlError("STAGING_FAILED",run.stderr[-2000:],status=409)
    return staging_status(runtime_id,version)


ADAPTER_DEPLOY_MODE = 0o444
ADAPTER_DEPLOY_SCRIPT = r"""import hashlib,json,os,shutil,stat,sys,time,uuid
p=json.loads(sys.argv[1]); src=p['source']; dst=p['destination']; expected=p['source_sha256']; mode=int(p['mode'])
lock=dst+'.deploy.lock'; lock_acquired=False; tmp=None; backup=None; replaced=False; had_destination=False
def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as handle:
  for chunk in iter(lambda:handle.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
def live_training_process():
 own={os.getpid(),os.getppid()}; directory=os.path.dirname(dst)
 markers=(dst,os.path.join(directory,'train_najdi_sft.py'))
 for name in os.listdir('/proc') if os.path.isdir('/proc') else ():
  if not name.isdigit() or int(name) in own: continue
  try:
   command=open('/proc/'+name+'/cmdline','rb').read().replace(b'\0',b' ').decode('utf-8','replace')
  except (OSError,PermissionError): continue
  if any(marker in command for marker in markers): return {'pid':int(name),'command':command[:500]}
 return None
def fail(code,message): raise RuntimeError(code+': '+message)
try:
 if not os.path.isfile(src): fail('SOURCE_NOT_FOUND','adapter source is not a regular file')
 if os.path.islink(src): fail('INVALID_SOURCE','adapter source must not be a symlink')
 if sha256(src)!=expected: fail('SOURCE_HASH_MISMATCH','source changed before deployment')
 parent=os.path.dirname(dst)
 if not os.path.isdir(parent): fail('TARGET_DIRECTORY_NOT_FOUND','target directory does not exist')
 if not os.access(parent,os.W_OK): fail('TARGET_NOT_WRITABLE','target directory is not writable')
 if os.path.islink(dst): fail('INVALID_TARGET','deployment target must not be a symlink')
 active=live_training_process()
 if active: fail('ACTIVE_TRAINING_PROCESS',json.dumps(active,separators=(',',':')))
 try: os.mkdir(lock,0o700); lock_acquired=True
 except FileExistsError: fail('DEPLOYMENT_IN_PROGRESS','another adapter deployment holds the target lock')
 active=live_training_process()
 if active: fail('ACTIVE_TRAINING_PROCESS',json.dumps(active,separators=(',',':')))
 had_destination=os.path.exists(dst)
 current_sha=sha256(dst) if had_destination and os.path.isfile(dst) else None
 if had_destination and current_sha==expected:
  os.chmod(dst,mode); actual_mode=stat.S_IMODE(os.stat(dst).st_mode)
  if actual_mode!=mode or actual_mode & stat.S_IWOTH: fail('INSECURE_TARGET_MODE','unable to enforce secure target permissions')
  print(json.dumps({'status':'PASS','action':'UNCHANGED','destination':dst,'source_sha256':expected,'destination_sha256':current_sha,'mode':oct(actual_mode),'backup':None}))
  sys.exit(0)
 token=uuid.uuid4().hex; tmp=dst+'.tmp-'+token
 if had_destination:
  stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()); backup=dst+'.backup-'+stamp+'-'+token
  shutil.copy2(dst,backup)
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with open(src,'rb') as source_handle,os.fdopen(fd,'wb') as tmp_handle: shutil.copyfileobj(source_handle,tmp_handle)
 tmp_sha=sha256(tmp)
 if tmp_sha!=expected: fail('DESTINATION_HASH_MISMATCH','temporary file checksum differs from source')
 os.replace(tmp,dst); tmp=None; replaced=True
 os.chmod(dst,mode)
 destination_sha=sha256(dst); actual_mode=stat.S_IMODE(os.stat(dst).st_mode)
 if destination_sha!=expected: fail('DESTINATION_HASH_MISMATCH','deployed file checksum differs from source')
 if actual_mode!=mode or actual_mode & stat.S_IWOTH: fail('INSECURE_TARGET_MODE','unable to enforce secure target permissions')
 print(json.dumps({'status':'PASS','action':'DEPLOYED','destination':dst,'source_sha256':expected,'destination_sha256':destination_sha,'mode':oct(actual_mode),'backup':backup}))
except Exception as exc:
 rollback_error=None
 try:
  if replaced:
   if had_destination and backup and os.path.isfile(backup):
    rollback=dst+'.rollback-'+uuid.uuid4().hex; shutil.copy2(backup,rollback); os.replace(rollback,dst)
   elif not had_destination and os.path.exists(dst): os.unlink(dst)
 except Exception as rollback_exc: rollback_error=type(rollback_exc).__name__+': '+str(rollback_exc)
 if tmp and os.path.exists(tmp):
  try: os.unlink(tmp)
  except OSError: pass
 print(json.dumps({'status':'FAIL','error':str(exc),'rollback_error':rollback_error,'backup':backup}),file=sys.stderr)
 sys.exit(1)
finally:
 try:
  if lock_acquired and os.path.isdir(lock): os.rmdir(lock)
 except OSError: pass
"""


def _active_local_training() -> bool:
    with ACTIVE_LOCK:
        return any(process.poll() is None for process in ACTIVE_PROCESSES.values())


def deploy_adapter(runtime_id: str, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _run) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    if runtime.get("type") != "WSL2" or not runtime.get("enabled", False):
        raise training.TrainingControlError("INVALID_RUNTIME", "Runtime must be an enabled WSL2 target", status=409)
    destination = _posix_path(runtime.get("training_script_path"), "training_script_path")
    python_path = _posix_path(runtime.get("python_path"), "python_path")
    if PurePosixPath(destination).name != "najdilab_training_adapter.py":
        raise training.TrainingControlError("INVALID_RUNTIME", "Runtime adapter target has an unexpected filename", status=409)
    source = training.PROJECT_ROOT / "scripts" / "najdilab_training_adapter.py"
    if not source.is_file() or source.is_symlink():
        raise training.TrainingControlError("ADAPTER_SOURCE_INVALID", "Official adapter source is missing or unsafe", status=409)
    try:
        worker = get_worker_state(runtime_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise training.TrainingControlError("WORKER_STATE_UNAVAILABLE", f"Cannot verify worker state: {exc}", status=409) from exc
    if worker.get("state") == "BUSY" or worker.get("current_job_id") or _active_local_training():
        raise training.TrainingControlError("ACTIVE_TRAINING", "Adapter deployment is forbidden while training is active", status=409)
    source_sha = training._sha256(source)
    payload = {"source": _windows_to_wsl(source), "destination": destination, "source_sha256": source_sha, "mode": ADAPTER_DEPLOY_MODE}
    run = _wsl(runtime, [python_path, "-c", ADAPTER_DEPLOY_SCRIPT, json.dumps(payload)], 60, runner)
    if run.returncode != 0:
        details: dict[str, Any] = {}
        try: details = json.loads(run.stderr.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError): pass
        message = str(details.get("error") or run.stderr or "Adapter deployment failed")[-2000:]
        code = "ACTIVE_TRAINING" if message.startswith("ACTIVE_TRAINING_PROCESS:") else "ADAPTER_DEPLOY_FAILED"
        raise training.TrainingControlError(code, message, status=409)
    try: deployed = json.loads(run.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise training.TrainingControlError("ADAPTER_DEPLOY_FAILED", "Invalid deployment verification result", status=409) from exc
    if deployed.get("source_sha256") != source_sha or deployed.get("destination_sha256") != source_sha or deployed.get("mode") != oct(ADAPTER_DEPLOY_MODE):
        raise training.TrainingControlError("ADAPTER_DEPLOY_FAILED", "Deployment evidence did not match the official source", status=409)
    return {"status": "PASS", "runtime_id": runtime_id, "files": {destination: source_sha}, **deployed}


def job_fingerprint(job: dict[str, Any]) -> str:
    immutable = {key: job.get(key) for key in ("job_id", "status", "dataset_version", "dataset_fingerprint", "model_config", "training_config", "runtime_target", "output_directory", "checkpoint_directory", "logs_path")}
    return hashlib.sha256(json.dumps(immutable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _runtime_for_job(job: dict[str, Any]) -> str:
    target = job.get("runtime_target") or {}; return str(target.get("runtime_id") or "najditrain-wsl")


def build_training_command(job: dict[str, Any], runtime: dict[str, Any], *, mode: str = "validate", attempt_id: str = "validation") -> dict[str, Any]:
    cfg = training.validate_training_config(job.get("training_config") or {})
    dataset = str(PurePosixPath(_posix_path(runtime["dataset_root"], "dataset_root")) / job["dataset_version"])
    root=PurePosixPath(runtime["default_output_root"])/job["job_id"]/attempt_id; output=str(root/"artifacts"); checkpoint=str(root/"checkpoints"); logs=str(root/"logs")
    mode_flag={"smoke":"--smoke-test","full":"--full-training","validate":"--validate-only"}.get(mode)
    if not mode_flag: raise training.TrainingControlError("INVALID_TRAINING_MODE","Unsupported training mode")
    args = [mode_flag, "--model-path", _posix_path(job["model_config"]["path"], "model_path"),
        "--model-id", str(job["model_config"]["id"]), "--model-revision", str(job["model_config"].get("revision") or "local"),
        "--sft-file", str(PurePosixPath(dataset)/"sft.jsonl"), "--multi-turn-file", str(PurePosixPath(dataset)/"multi_turn.jsonl"),
        "--output-dir", output, "--checkpoint-dir", checkpoint, "--logs-dir", logs,
        "--epochs", str(cfg["epochs"]), "--max-steps", "2" if mode=="smoke" else str(cfg["max_steps"] if cfg["max_steps"] is not None else -1),
        "--expected-steps", str(job["calculated_steps"]["estimated_total_optimizer_steps"]), "--save-steps", str(cfg["save_steps"]), "--learning-rate", str(cfg["learning_rate"]),
        "--batch-size", str(cfg["batch_size"]), "--gradient-accumulation-steps", str(cfg["gradient_accumulation_steps"]), "--max-seq-length", str(cfg["max_seq_length"]),
        "--warmup-ratio", str(cfg["warmup_ratio"]), "--weight-decay", str(cfg["weight_decay"]), "--lr-scheduler", cfg["lr_scheduler"], "--optimizer", cfg["optimizer"],
        "--seed", str(cfg["seed"]), "--lora-r", str(cfg["lora_rank"]), "--lora-alpha", str(cfg["lora_alpha"]), "--lora-dropout", str(cfg["lora_dropout"]),
        "--target-modules", ",".join(cfg["target_modules"])]
    local_dataset=training._version_dir(job["dataset_version"])
    if (local_dataset/"native_tool_use.jsonl").is_file():
        args += ["--native-tool-file",str(PurePosixPath(dataset)/"native_tool_use.jsonl"),"--capability-registry",str(PurePosixPath(dataset)/"capability-registry.json")]
    for flag, enabled in (("--bf16",cfg["bf16"]),("--fp16",cfg["fp16"]),("--packing", cfg["packing"]), ("--gradient-checkpointing", cfg["gradient_checkpointing"])):
        if enabled: args.append(flag)
    command = {"executable": _posix_path(runtime["python_path"], "python_path"), "args": [_posix_path(runtime["training_script_path"], "training_script_path"), *args],
        "env": {"PYTHONUNBUFFERED": "1", "TOKENIZERS_PARALLELISM": "false"}}
    command["preview"] = " ".join(shlex.quote(part) for part in [command["executable"], *command["args"]])
    command["paths"]={"root":str(root),"output":output,"checkpoint":checkpoint,"logs":logs}
    return command


def execution_gate(job_id: str, *, now: datetime | None = None, live_gpu_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    job = training.get_job(job_id); blockers: list[dict[str, str]] = []; warnings: list[dict[str, str]] = []; checks: dict[str, Any] = {}
    def block(code: str, message: str) -> None: blockers.append({"code": code, "message": message})
    gate = training.quality_gate(job["dataset_version"]); checks["dataset_gate"] = gate["status"]
    if gate["status"] not in {"PASS", "PASS_WITH_WARNINGS"}: block("QUALITY_GATE_BLOCKED", "Dataset Quality Gate is invalid")
    if gate.get("dataset_fingerprint") != job.get("dataset_fingerprint"): block("STALE_DATASET_FINGERPRINT", "The dataset fingerprint changed")
    checks["job_status"] = job.get("status")
    if job.get("status") != "READY": block("JOB_NOT_READY", "The job must be READY")
    if job.get("warnings") and not (job.get("acknowledged_warnings") or {}).get("acknowledged"): block("WARNING_ACK_REQUIRED", "Dataset warnings have not been acknowledged")
    try: model = training.get_model(str((job.get("model_config") or {}).get("id") or ""))
    except training.TrainingControlError: model = None; block("MODEL_NOT_FOUND", "Base model is not registered")
    if model and not model.get("enabled"): block("MODEL_DISABLED", "Base model is disabled")
    runtime_id = _runtime_for_job(job); runtime = get_runtime(runtime_id); result = get_runtime_result(runtime_id); worker = get_worker_state(runtime_id, now=now)
    staged=staging_status(runtime_id,job["dataset_version"]); checks.update({"runtime_id": runtime_id, "worker": worker, "runtime": result,"staging":staged})
    if staged["status"]!="PASS": block("STAGING_INVALID","Staged dataset missing, stale, or corrupt")
    age = _age_seconds((result or {}).get("checked_at"), now)
    if result is None: block("RUNTIME_CHECK_REQUIRED", "Run the Runtime Check manually")
    elif age is None or age > RUNTIME_CHECK_MAX_AGE_SECONDS: block("RUNTIME_CHECK_STALE", "The Runtime Check is stale")
    elif result.get("status") not in {"AVAILABLE", "AVAILABLE_WITH_WARNINGS"}: block("RUNTIME_UNAVAILABLE", "Runtime is unavailable: " + ", ".join(result.get("blockers") or []))
    if worker.get("state") != "IDLE": block("WORKER_NOT_IDLE", f"Worker state is {worker.get('state')}")
    if worker.get("heartbeat_freshness") != "FRESH": block("WORKER_HEARTBEAT_STALE", "Worker heartbeat is not fresh")
    detected = (result or {}).get("detected") or {}; paths = detected.get("paths") or {}
    for key, code in (("script","TRAINING_SCRIPT_NOT_FOUND"),("dataset_root","DATASET_PATH_NOT_ACCESSIBLE"),("output","OUTPUT_NOT_WRITABLE"),("checkpoint","OUTPUT_NOT_WRITABLE"),("logs","OUTPUT_NOT_WRITABLE")):
        item = paths.get(key, {}); ok = item.get("writable") if key in {"output","checkpoint","logs"} else item.get("exists")
        if result and not ok: block(code, f"Runtime path {key} is invalid")
    if result:
        package = detected.get("packages") or {}
        if not (package.get("torch") or {}).get("available"): block("TORCH_NOT_AVAILABLE", "PyTorch is unavailable")
        if not detected.get("cuda_available"): block("CUDA_NOT_AVAILABLE", "CUDA is unavailable")
        if not detected.get("gpu"): block("GPU_NOT_FOUND", "GPU was not detected")
        if not (package.get("unsloth") or {}).get("available"): block("UNSLOTH_NOT_AVAILABLE", "Unsloth is unavailable")
        model_path = (paths.get("model") or {})
        if model_path and not model_path.get("exists"): block("MODEL_PATH_NOT_ACCESSIBLE", "Model path is unavailable")
        if model_path and not model_path.get("tokenizer_exists", True): block("TOKENIZER_NOT_AVAILABLE", "Tokenizer files are unavailable")
    config = training.validate_training_config(job.get("training_config") or {})
    static_model = dict(model or job.get("model_config") or {})
    if not static_model.get("model_size_gb") and (paths.get("model") or {}).get("size_bytes"):
        static_model["model_size_gb"] = round(paths["model"]["size_bytes"] / 1024**3, 3)
    cached_gpu = detected.get("gpu") or {}
    live_gpu = (live_gpu_probe or probe_live_gpu)(runtime); checks["gpu_measurement"] = live_gpu; checks["cached_gpu_diagnostic"] = {"authoritative": False, "checked_at": (result or {}).get("checked_at"), **cached_gpu}
    if not live_gpu.get("success"):
        block("LIVE_GPU_PROBE_FAILED", "Unable to measure live GPU memory from the training runtime")
    runtime_vram = {"gpu_vram_total_gb": live_gpu.get("total_gib") if live_gpu.get("success") else None,
        "gpu_vram_free_gb": live_gpu.get("free_gib") if live_gpu.get("success") else None}
    vram = training.estimate_vram(static_model, config, runtime_vram); checks["vram"] = vram
    if vram["status"] == "LIKELY_OOM": block("LIKELY_OOM", "The VRAM estimate indicates likely out-of-memory failure")
    elif vram["status"] == "TIGHT": warnings.append({"code":"VRAM_TIGHT","message":"The VRAM margin is narrow"})
    elif vram["status"] == "UNKNOWN": block("VRAM_UNKNOWN", "VRAM cannot be estimated without model size and runtime data")
    warnings.extend({"code": item.get("code", "QUALITY_WARNING"), "message": item.get("message", "")} for item in gate.get("warnings", []))
    status = "BLOCKED" if blockers else "PASS_WITH_WARNINGS" if warnings else "PASS"
    if result is None or (result and (age is None or age > RUNTIME_CHECK_MAX_AGE_SECONDS)): status = "UNAVAILABLE" if blockers else status
    return {"job_id": job_id, "status": status, "blockers": blockers, "warnings": warnings, "checks": checks, "quality_gate": gate,
        "job_fingerprint": job_fingerprint(job), "runtime_fingerprint": (result or {}).get("runtime_fingerprint"), "checked_at": training._now()}


def dry_run(job_id: str, *, attempt_type: str = "SMOKE") -> dict[str, Any]:
    if attempt_type not in {"SMOKE","FULL"}: raise training.TrainingControlError("INVALID_ATTEMPT_TYPE","Invalid dry-run type")
    job = training.get_job(job_id); gate = execution_gate(job_id)
    runtime = get_runtime(_runtime_for_job(job)); command = build_training_command(job, runtime)
    result = {"job_id": job_id, "status": "BLOCKED" if gate["status"] in {"BLOCKED", "UNAVAILABLE"} else gate["status"], "execution_gate": gate,
        "command": command, "env_summary": sorted(command["env"]), "dataset": job["dataset_version"], "model": job["model_config"],
        "output_path": job["output_directory"], "checkpoint_path": job["checkpoint_directory"], "logs_path": job["logs_path"],
        "estimated_steps": job.get("calculated_steps"), "vram": gate["checks"].get("vram"), "blockers": gate["blockers"], "warnings": gate["warnings"],
        "generated_at": training._now(), "training_started": False}
    if result["status"] in {"PASS", "PASS_WITH_WARNINGS"}:
        validate=_wsl(runtime,[command["executable"],*command["args"]],60)
        if validate.returncode!=0:
            result["status"]="BLOCKED"; result["blockers"].append({"code":"ADAPTER_VALIDATION_FAILED","message":validate.stderr[-2000:]}); result["adapter_validation"]={"exit_code":validate.returncode,"stderr":validate.stderr[-2000:]}; return result
        try: adapter_validation=json.loads(validate.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError,IndexError):
            result["status"]="BLOCKED"; result["blockers"].append({"code":"ADAPTER_VALIDATION_INVALID","message":"Adapter validation did not return JSON"}); return result
        result["adapter_validation"]={"exit_code":0,"result":adapter_validation}
        runtime_result = get_runtime_result(runtime["id"]); manifest = {"schema_version": 1, "job_id": job_id, "generated_at": result["generated_at"],
            "job_fingerprint": gate["job_fingerprint"], "dataset_fingerprint": job["dataset_fingerprint"], "model_identity": {"id": job["model_config"]["id"], "path": job["model_config"]["path"],
                "config_sha256": ((get_runtime_result(runtime["id"]) or {}).get("detected", {}).get("paths", {}).get("model", {}) or {}).get("config_sha256")},
            "runtime_id": runtime["id"], "runtime_fingerprint": gate["runtime_fingerprint"], "gpu_snapshot": (runtime_result or {}).get("detected", {}).get("gpu"),
            "attempt_type":attempt_type,"staged_dataset":gate["checks"]["staging"],"training_config": job["training_config"], "command": command, "env_allowlist": sorted(SAFE_ENV_KEYS),
            "adapter_sha256":((((runtime_result or {}).get("detected") or {}).get("paths") or {}).get("script") or {}).get("sha256"),
            "tokenizer_fingerprint":adapter_validation.get("tokenizer_fingerprint"),"chat_template_sha256":adapter_validation.get("chat_template_file_sha256"),"adapter_plan":adapter_validation,
            "output_paths": command["paths"],
            "estimated_steps": job.get("calculated_steps"), "vram_estimate": result["vram"], "warnings": result["warnings"],
            "quality_gate": gate["quality_gate"], "execution_gate": gate, "training_started": False}
        path = training.JOBS_ROOT / job_id / "execution-manifest.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("job_fingerprint") != manifest["job_fingerprint"] or old.get("runtime_fingerprint") != manifest["runtime_fingerprint"]:
                archive = path.with_name(f"execution-manifest.stale-{datetime.now().strftime('%Y%m%d%H%M%S%f')}.json"); os.replace(path, archive)
        training._atomic_json(path, manifest); result["execution_manifest"] = str(path)
    return result


def start_worker(runtime_id: str) -> dict[str,Any]:
    result=get_runtime_result(runtime_id)
    if not result or result.get("status") not in {"AVAILABLE","AVAILABLE_WITH_WARNINGS"}: raise training.TrainingControlError("RUNTIME_UNAVAILABLE","Runtime must pass before worker start",status=409)
    previous=get_worker_state(runtime_id)
    if previous.get("state")=="ERROR":
        history=RUNTIME_ROOT/f"{runtime_id}-worker-history.jsonl"; history.parent.mkdir(parents=True,exist_ok=True)
        with history.open("a",encoding="utf-8") as handle: handle.write(json.dumps(previous,ensure_ascii=False)+"\n")
    return set_worker_state(runtime_id,"IDLE")


def prepare_full_recovery(job_id: str) -> dict[str,Any]:
    """Prepare the one permitted from-scratch recovery without erasing attempt-001."""
    job=training.get_job(job_id); attempts=training.JOBS_ROOT/job_id/"attempts"
    first=get_attempt(job_id,"attempt-001")
    if not job.get("production_mode") or job.get("status")!="FAILED" or first.get("attempt_type")!="FULL" or first.get("status")!="FAILED":
        raise training.TrainingControlError("RECOVERY_NOT_ELIGIBLE","A failed production attempt-001 is required",status=409)
    if (attempts/"attempt-002").exists(): raise training.TrainingControlError("RECOVERY_ATTEMPT_LIMIT","Recovery attempt-002 already exists",status=409)
    reason="trainer_plan_mismatch_due_to_max_steps_zero"; now=training._now()
    checkpoint={"status":"NON_RESUMABLE","resume_allowed":False,"reason":reason,"source_attempt":"attempt-001","marked_at":now}
    training._atomic_json(attempts/"attempt-001"/"checkpoint-validation.json",checkpoint)
    first["checkpoint_validation"]=checkpoint; first["resume_available"]=False; training._atomic_json(attempts/"attempt-001"/"attempt.json",first)
    archived=[]
    for name in ("execution-manifest.json","full-training-authorization.json"):
        path=training.JOBS_ROOT/job_id/name
        if path.exists():
            target=path.with_name(f"{path.stem}.stale-attempt-001-{datetime.now().strftime('%Y%m%d%H%M%S%f')}{path.suffix}"); os.replace(path,target); archived.append(str(target))
    job["training_config"]=training.validate_training_config(job.get("training_config") or {})
    job["calculated_steps"]=training.calculate_plan(int(job["dataset_counts"]["training"]),job["training_config"])
    job["status"]="READY"; job["full_training_status"]="RECOVERY_READY"; job["updated_at"]=now
    job.setdefault("provenance",{})["recovery"]={"authorized_attempt":"attempt-002","from_scratch":True,"resume_from":None,"invalidated_attempt":"attempt-001","reason":reason,"prepared_at":now,"archived_artifacts":archived}
    training._atomic_json(training._job_path(job_id),job)
    return {"status":"RECOVERY_READY","job":job,"checkpoint":checkpoint,"archived_artifacts":archived}


def resume_full_training(job_id: str, attempt_id: str, checkpoint: str) -> None:
    metadata=_attempt_dir(job_id,attempt_id)/"checkpoint-validation.json"
    if metadata.is_file() and json.loads(metadata.read_text(encoding="utf-8")).get("resume_allowed") is False:
        raise training.TrainingControlError("CHECKPOINT_NOT_RESUMABLE","Checkpoint is marked NON_RESUMABLE",status=409)
    raise training.TrainingControlError("CHECKPOINT_RESUME_NOT_SUPPORTED","Checkpoint resume is not supported by this workflow",status=409)


def worker_heartbeat(runtime_id: str) -> dict[str,Any]:
    state=get_worker_state(runtime_id)
    if state["state"]=="OFFLINE": raise training.TrainingControlError("WORKER_OFFLINE","Worker is offline",status=409)
    return set_worker_state(runtime_id,state["state"],current_job_id=state.get("current_job_id"),error=state.get("last_error"))


def _attempt_dir(job_id: str, attempt_id: str) -> Path: return training.JOBS_ROOT/job_id/"attempts"/attempt_id


def get_attempt(job_id: str, attempt_id: str) -> dict[str,Any]:
    if not re.fullmatch(r"attempt-\d{3}",attempt_id): raise training.TrainingControlError("ATTEMPT_NOT_FOUND","Invalid attempt",status=404)
    path=_attempt_dir(job_id,attempt_id)/"attempt.json"
    if not path.is_file(): raise training.TrainingControlError("ATTEMPT_NOT_FOUND","Attempt not found",status=404)
    return json.loads(path.read_text(encoding="utf-8"))


def _tail(path: Path, offset: int=0, limit: int=32768) -> dict[str,Any]:
    if not path.is_file(): return {"text":"","next_offset":0}
    size=path.stat().st_size; start=max(0,min(offset,size));
    with path.open("rb") as f: f.seek(start); data=f.read(limit)
    return {"text":data.decode("utf-8",errors="replace"),"next_offset":start+len(data),"truncated":start+len(data)<size}


def attempt_logs(job_id: str, attempt_id: str, stream: str, offset: int=0) -> dict[str,Any]:
    if stream not in {"stdout","stderr"}: raise training.TrainingControlError("INVALID_LOG_STREAM","Invalid stream")
    get_attempt(job_id,attempt_id); return _tail(_attempt_dir(job_id,attempt_id)/f"{stream}.log",offset)


def attempt_metrics(job_id: str, attempt_id: str, offset: int=0) -> dict[str,Any]:
    get_attempt(job_id,attempt_id); directory=_attempt_dir(job_id,attempt_id)
    return {"metrics":_tail(directory/"metrics.jsonl",offset),"gpu":_tail(directory/"gpu-metrics.jsonl",offset)}


def _run_smoke_thread(job_id: str, attempt_id: str, command: dict[str,Any], runtime: dict[str,Any]) -> None:
    directory=_attempt_dir(job_id,attempt_id); stdout_path=directory/"stdout.log"; stderr_path=directory/"stderr.log"; gpu_path=directory/"gpu-metrics.jsonl"; started=time.time(); proc=None
    try:
        env_args=[f"{k}={v}" for k,v in command["env"].items() if k in SAFE_ENV_KEYS]
        argv=["wsl.exe","-d",runtime["wsl_distro"],"--","env",*env_args,command["executable"],*command["args"]]
        with stdout_path.open("w",encoding="utf-8") as out, stderr_path.open("w",encoding="utf-8") as err:
            proc=subprocess.Popen(argv,stdout=out,stderr=err,text=True,encoding="utf-8",errors="replace",shell=False)
            with ACTIVE_LOCK: ACTIVE_PROCESSES[attempt_id]=proc
            attempt=get_attempt(job_id,attempt_id); attempt.update({"status":"RUNNING","pid":proc.pid,"started_at":training._now()}); training._atomic_json(directory/"attempt.json",attempt)
            if attempt.get("attempt_type")=="FULL":
                running_job=training.get_job(job_id); running_job["status"]="RUNNING"; running_job["updated_at"]=training._now(); training._atomic_json(training._job_path(job_id),running_job)
            while proc.poll() is None:
                set_worker_state(runtime["id"],"BUSY",current_job_id=job_id)
                gpu=_wsl(runtime,["nvidia-smi","--query-gpu=timestamp,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu","--format=csv,noheader,nounits"],15)
                sample={"captured_at":training._now(),"exit_code":gpu.returncode,"sample":gpu.stdout.strip(),"error":gpu.stderr.strip()[-500:]}
                with gpu_path.open("a",encoding="utf-8") as handle: handle.write(json.dumps(sample,ensure_ascii=False)+"\n")
                time.sleep(3)
        stdout=stdout_path.read_text(encoding="utf-8",errors="replace"); stderr=stderr_path.read_text(encoding="utf-8",errors="replace")
        result_data=None; metrics=[]
        for line in (stdout or "").splitlines():
            if line.startswith("NAJDILAB_METRIC="):
                try: metrics.append(json.loads(line.split("=",1)[1]))
                except json.JSONDecodeError: pass
        with (directory/"metrics.jsonl").open("w",encoding="utf-8") as handle:
            for metric in metrics: handle.write(json.dumps(metric,ensure_ascii=False)+"\n")
        for line in reversed((stdout or "").splitlines()):
            if line.startswith("NAJDILAB_RESULT="):
                result_data=json.loads(line.split("=",1)[1]); break
        current=get_attempt(job_id,attempt_id)
        if current.get("status")=="CANCELLED":
            result={"status":"CANCELLED","exit_code":proc.returncode,"adapter_result":None,"metric_count":len(metrics),"elapsed_seconds":round(time.time()-started,3),"training_started":True,"full_training_started":False}
            training._atomic_json(directory/"result.json",result); current.update({"ended_at":current.get("ended_at") or training._now(),"exit_code":proc.returncode,"result":result}); training._atomic_json(directory/"attempt.json",current); set_worker_state(runtime["id"],"IDLE"); return
        attempt_kind=current.get("attempt_type","SMOKE"); expected=2 if attempt_kind=="SMOKE" else int(current.get("expected_steps") or 0)
        status="COMPLETED" if proc.returncode==0 and result_data and result_data.get("global_step")==expected and not result_data.get("nan_or_inf") else "FAILED"
        result={"status":"PASSED" if status=="COMPLETED" else "FAILED","exit_code":proc.returncode,"adapter_result":result_data,"metric_count":len(metrics),"elapsed_seconds":round(time.time()-started,3),"training_started":True,"full_training_started":attempt_kind=="FULL"}
        training._atomic_json(directory/"result.json",result); attempt=get_attempt(job_id,attempt_id); attempt.update({"status":status,"ended_at":training._now(),"exit_code":proc.returncode,"result":result}); training._atomic_json(directory/"attempt.json",attempt)
        job=training.get_job(job_id); job["latest_attempt_id"]=attempt_id
        if attempt_kind=="SMOKE": job["smoke_status"]="PASSED" if status=="COMPLETED" else "FAILED"; job["execution_ready"]=status=="COMPLETED"; job["provenance"]["execution_started"]=False
        else: job["status"]=status; job["full_training_status"]="PASSED" if status=="COMPLETED" else "FAILED"; job["provenance"]["execution_started"]=True; job["updated_at"]=training._now()
        training._atomic_json(training._job_path(job_id),job)
        set_worker_state(runtime["id"],"IDLE" if status=="COMPLETED" else "ERROR",error=None if status=="COMPLETED" else (stderr or "")[-1000:])
    except Exception as exc:
        attempt=get_attempt(job_id,attempt_id); attempt.update({"status":"FAILED","ended_at":training._now(),"error":f"{type(exc).__name__}: {exc}"}); training._atomic_json(directory/"attempt.json",attempt); set_worker_state(runtime["id"],"ERROR",error=str(exc))
    finally:
        with ACTIVE_LOCK: ACTIVE_PROCESSES.pop(attempt_id,None)


def start_smoke(job_id: str) -> dict[str,Any]:
    job=training.get_job(job_id)
    if job.get("status")!="READY": raise training.TrainingControlError("JOB_NOT_READY","Smoke requires READY",status=409)
    gate=execution_gate(job_id)
    if gate["status"] not in {"PASS","PASS_WITH_WARNINGS"}: raise training.TrainingControlError("EXECUTION_GATE_BLOCKED","Execution Gate blocks smoke",status=409)
    manifest_path=training.JOBS_ROOT/job_id/"execution-manifest.json"
    if not manifest_path.is_file(): raise training.TrainingControlError("DRY_RUN_REQUIRED","Passing Dry Run required",status=409)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("job_fingerprint")!=gate["job_fingerprint"] or manifest.get("runtime_fingerprint")!=gate["runtime_fingerprint"]: raise training.TrainingControlError("EXECUTION_MANIFEST_STALE","Execution manifest is stale",status=409)
    runtime=get_runtime(_runtime_for_job(job)); attempts=training.JOBS_ROOT/job_id/"attempts"; attempts.mkdir(exist_ok=True); used={p.name for p in attempts.iterdir() if p.is_dir()}; number=next(i for i in range(1,1000) if f"attempt-{i:03d}" not in used); attempt_id=f"attempt-{number:03d}"; directory=_attempt_dir(job_id,attempt_id); directory.mkdir()
    command=build_training_command(job,runtime,mode="smoke",attempt_id=attempt_id)
    attempt={"attempt_id":attempt_id,"attempt_type":"SMOKE","status":"QUEUED","job_id":job_id,"created_at":training._now(),"max_steps":2,"command":command,"full_training":False}
    training._atomic_json(directory/"attempt.json",attempt); training._atomic_json(directory/"execution-manifest.json",{**manifest,"attempt_id":attempt_id,"attempt_type":"SMOKE","command":command});
    runtime_result=get_runtime_result(runtime["id"]); training._atomic_json(directory/"runtime-snapshot.json",runtime_result)
    job["latest_attempt_id"]=attempt_id; job["attempt_count"]=number; job["smoke_status"]="QUEUED"; training._atomic_json(training._job_path(job_id),job); set_worker_state(runtime["id"],"BUSY",current_job_id=job_id)
    threading.Thread(target=_run_smoke_thread,args=(job_id,attempt_id,command,runtime),daemon=True).start(); return attempt


def cancel_attempt(job_id: str, attempt_id: str) -> dict[str,Any]:
    attempt=get_attempt(job_id,attempt_id)
    if attempt["status"] not in {"QUEUED","RUNNING"}: raise training.TrainingControlError("ATTEMPT_NOT_RUNNING","Attempt is not running",status=409)
    with ACTIVE_LOCK: proc=ACTIVE_PROCESSES.get(attempt_id)
    if proc:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
    attempt["status"]="CANCELLED"; attempt["ended_at"]=training._now(); training._atomic_json(_attempt_dir(job_id,attempt_id)/"attempt.json",attempt); return attempt


def _authorization_path(job_id: str) -> Path: return training.JOBS_ROOT/job_id/"full-training-authorization.json"


def authorize_full_training(job_id: str, acknowledgement: str) -> dict[str,Any]:
    job=training.get_job(job_id)
    if acknowledgement != f"I agree to start FULL TRAINING for job {job_id}": raise training.TrainingControlError("AUTHORIZATION_ACK_REQUIRED","Explicit acknowledgement text does not match",status=409)
    if job.get("status")!="READY" or not job.get("production_mode"): raise training.TrainingControlError("JOB_NOT_READY","Production READY job required",status=409)
    smoke=(job.get("provenance") or {}).get("smoke_reference") or {}; smoke_result=training.JOBS_ROOT/str(smoke.get("job_id"))/"attempts"/str(smoke.get("attempt_id"))/"result.json"
    if not smoke_result.is_file() or json.loads(smoke_result.read_text(encoding="utf-8")).get("status")!="PASSED": raise training.TrainingControlError("SMOKE_REFERENCE_INVALID","Approved Smoke is not PASSED",status=409)
    gate=execution_gate(job_id)
    if gate["status"] not in {"PASS","PASS_WITH_WARNINGS"}: raise training.TrainingControlError("EXECUTION_GATE_BLOCKED","Execution Gate blocks authorization",status=409)
    recalculated=training.calculate_plan(int(job["dataset_counts"]["training"]),job["training_config"])
    if recalculated!=job.get("calculated_steps"): raise training.TrainingControlError("TRAINING_PLAN_STALE","Stored training plan differs from recalculation",status=409)
    manifest_path=training.JOBS_ROOT/job_id/"execution-manifest.json"
    if not manifest_path.is_file(): raise training.TrainingControlError("DRY_RUN_REQUIRED","Full Dry Run required",status=409)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("attempt_type")!="FULL" or manifest.get("job_fingerprint")!=gate["job_fingerprint"] or manifest.get("runtime_fingerprint")!=gate["runtime_fingerprint"]: raise training.TrainingControlError("EXECUTION_MANIFEST_STALE","Full execution manifest is stale",status=409)
    token=secrets.token_urlsafe(32); now=datetime.now(timezone.utc); expires=now.timestamp()+AUTH_TTL_SECONDS
    binding={"job_id":job_id,"job_fingerprint":gate["job_fingerprint"],"dataset_fingerprint":job["dataset_fingerprint"],"staged_fingerprint":gate["checks"]["staging"]["manifest"]["source_fingerprint"],"model_fingerprint":manifest["model_identity"].get("config_sha256"),"runtime_id":manifest["runtime_id"],"runtime_fingerprint":manifest["runtime_fingerprint"],"adapter_sha256":manifest.get("adapter_sha256"),"tokenizer_fingerprint":manifest.get("tokenizer_fingerprint"),"chat_template_sha256":manifest.get("chat_template_sha256"),"execution_manifest_sha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    record={"schema_version":1,"token_sha256":hashlib.sha256(token.encode()).hexdigest(),"issued_at":now.isoformat().replace("+00:00","Z"),"expires_at":datetime.fromtimestamp(expires,timezone.utc).isoformat().replace("+00:00","Z"),"used_at":None,"binding":binding}
    training._atomic_json(_authorization_path(job_id),record); return {"job_id":job_id,"token":token,"expires_at":record["expires_at"],"single_use":True,"binding":binding}


def start_full_training(job_id: str, token: str) -> dict[str,Any]:
    job=training.get_job(job_id); path=_authorization_path(job_id)
    if not path.is_file(): raise training.TrainingControlError("AUTHORIZATION_REQUIRED","Full Training authorization required",status=403)
    auth=json.loads(path.read_text(encoding="utf-8"))
    if auth.get("used_at"): raise training.TrainingControlError("AUTHORIZATION_ALREADY_USED","Authorization token already used",status=409)
    if _parse_time(auth.get("expires_at")) < datetime.now(timezone.utc): raise training.TrainingControlError("AUTHORIZATION_EXPIRED","Authorization expired",status=409)
    if not secrets.compare_digest(auth.get("token_sha256",""),hashlib.sha256(str(token).encode()).hexdigest()): raise training.TrainingControlError("AUTHORIZATION_JOB_MISMATCH","Authorization token invalid for this job",status=403)
    gate=execution_gate(job_id); manifest_path=training.JOBS_ROOT/job_id/"execution-manifest.json"; manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    binding=auth["binding"]
    current={"job_id":job_id,"job_fingerprint":gate["job_fingerprint"],"dataset_fingerprint":job["dataset_fingerprint"],"staged_fingerprint":gate["checks"]["staging"].get("manifest",{}).get("source_fingerprint"),"model_fingerprint":manifest.get("model_identity",{}).get("config_sha256"),"runtime_id":manifest.get("runtime_id"),"runtime_fingerprint":gate["runtime_fingerprint"],"adapter_sha256":((((get_runtime_result(manifest.get("runtime_id")) or {}).get("detected") or {}).get("paths") or {}).get("script") or {}).get("sha256"),"tokenizer_fingerprint":manifest.get("tokenizer_fingerprint"),"chat_template_sha256":manifest.get("chat_template_sha256"),"execution_manifest_sha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    if gate["status"] not in {"PASS","PASS_WITH_WARNINGS"} or current!=binding: raise training.TrainingControlError("EXECUTION_STATE_CHANGED","Execution state changed; repeat Dry Run and authorization",status=409)
    runtime=get_runtime(_runtime_for_job(job)); attempts=training.JOBS_ROOT/job_id/"attempts"; attempts.mkdir(exist_ok=True); used={p.name for p in attempts.iterdir() if p.is_dir()}
    recovery=(job.get("provenance") or {}).get("recovery")
    if recovery:
        if "attempt-002" in used: raise training.TrainingControlError("RECOVERY_ATTEMPT_LIMIT","Only one recovery attempt is permitted",status=409)
        attempt_id="attempt-002"; number=2
    else:
        number=next(i for i in range(1,1000) if f"attempt-{i:03d}" not in used); attempt_id=f"attempt-{number:03d}"
    directory=_attempt_dir(job_id,attempt_id); directory.mkdir()
    command=build_training_command(job,runtime,mode="full",attempt_id=attempt_id); expected=int(job["calculated_steps"]["estimated_total_optimizer_steps"])
    attempt={"attempt_id":attempt_id,"attempt_type":"FULL","status":"QUEUED","job_id":job_id,"created_at":training._now(),"expected_steps":expected,"command":command,"full_training":True,"resume_from":None,"from_scratch":True,"parent_attempt":None}
    training._atomic_json(directory/"attempt.json",attempt); training._atomic_json(directory/"execution-manifest.json",{**manifest,"attempt_id":attempt_id,"attempt_type":"FULL","command":command}); training._atomic_json(directory/"runtime-snapshot.json",get_runtime_result(runtime["id"]))
    auth["used_at"]=training._now(); auth["attempt_id"]=attempt_id; training._atomic_json(path,auth)
    job["latest_attempt_id"]=attempt_id; job["attempt_count"]=number; job["status"]="QUEUED"; job["full_training_status"]="QUEUED"; job["updated_at"]=training._now(); training._atomic_json(training._job_path(job_id),job); set_worker_state(runtime["id"],"BUSY",current_job_id=job_id)
    threading.Thread(target=_run_smoke_thread,args=(job_id,attempt_id,command,runtime),daemon=True).start(); return attempt


def validate_trained_adapter(job_id: str, attempt_id: str) -> dict[str,Any]:
    job=training.get_job(job_id); attempt=get_attempt(job_id,attempt_id)
    if attempt.get("attempt_type")!="FULL" or attempt.get("status")!="COMPLETED": raise training.TrainingControlError("FULL_ATTEMPT_NOT_COMPLETE","Completed FULL attempt required",status=409)
    adapter=((attempt.get("result") or {}).get("adapter_result") or {}); adapter_path=adapter.get("adapter_path")
    runtime=get_runtime(_runtime_for_job(job)); script="""import hashlib,json,os,sys
p=sys.argv[1]; required=['adapter_config.json','adapter_model.safetensors','tokenizer_config.json']; missing=[x for x in required if not os.path.isfile(os.path.join(p,x))]
cfg=None
if not missing:
 cfg=json.load(open(os.path.join(p,'adapter_config.json'),encoding='utf-8'))
print(json.dumps({'exists':os.path.isdir(p),'missing':missing,'adapter_config_valid':isinstance(cfg,dict) and bool(cfg.get('peft_type')),'files':sorted(os.listdir(p)) if os.path.isdir(p) else []}))"""
    checked=_wsl(runtime,[runtime["python_path"],"-c",script,str(adapter_path)],30)
    if checked.returncode!=0: raise training.TrainingControlError("ADAPTER_VALIDATION_FAILED",checked.stderr[-2000:],status=409)
    files=json.loads(checked.stdout.strip().splitlines()[-1]); gate=training.quality_gate(job["dataset_version"]); runtime_result=get_runtime_result(runtime["id"]); model_fp=((runtime_result or {}).get("detected",{}).get("paths",{}).get("model",{}) or {}).get("config_sha256")
    valid=files["exists"] and not files["missing"] and files["adapter_config_valid"] and not adapter.get("nan_or_inf") and adapter.get("global_step")==attempt.get("expected_steps") and gate.get("dataset_fingerprint")==job.get("dataset_fingerprint") and model_fp==adapter.get("model_config_sha256")
    result={"status":"PASS" if valid else "FAIL","job_id":job_id,"attempt_id":attempt_id,"adapter_path":adapter_path,"files":files,"dataset_unchanged":gate.get("dataset_fingerprint")==job.get("dataset_fingerprint"),"base_model_unchanged":model_fp==adapter.get("model_config_sha256"),"history_finite":not adapter.get("nan_or_inf"),"steps_complete":adapter.get("global_step")==attempt.get("expected_steps"),"validated_at":training._now(),"phase3_started":False}
    training._atomic_json(_attempt_dir(job_id,attempt_id)/"adapter-validation.json",result); job["adapter_validation_status"]=result["status"]; training._atomic_json(training._job_path(job_id),job); return result


def full_training_disabled() -> None:
    raise training.TrainingControlError("FULL_TRAINING_NOT_ENABLED","Full Training is locked pending explicit future approval",status=403)
