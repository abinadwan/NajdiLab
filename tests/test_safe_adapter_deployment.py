from __future__ import annotations

import json
import io
import os
import shutil
import stat
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from app import runtime_control as runtime


def _error_code(exc: Exception) -> str | None:
    return getattr(exc, "code", None)


@pytest.fixture()
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    source = scripts / "najdilab_training_adapter.py"
    source.write_bytes(b"# official adapter\nprint('safe')\n")
    target_dir = tmp_path / "runtime" / "scripts"
    target_dir.mkdir(parents=True)
    target = target_dir / "najdilab_training_adapter.py"
    companion = target_dir / "train_najdi_sft.py"
    companion.write_bytes(b"# companion must not change\n")
    runtime_config = {
        "id": "test-runtime",
        "type": "WSL2",
        "enabled": True,
        "wsl_distro": "isolated-test-boundary",
        "python_path": sys.executable,
        "training_script_path": target.as_posix(),
    }
    monkeypatch.setattr(runtime.training, "PROJECT_ROOT", project)
    monkeypatch.setattr(runtime, "get_runtime", lambda runtime_id: runtime_config)
    monkeypatch.setattr(runtime, "get_worker_state", lambda runtime_id: {"state": "IDLE", "current_job_id": None})
    monkeypatch.setattr(runtime, "_active_local_training", lambda: False)
    monkeypatch.setattr(runtime, "_windows_to_wsl", lambda path: str(path))
    monkeypatch.setattr(runtime, "_posix_path", lambda value, field: str(value))

    def local_runner(command: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        index = command.index("-c")
        stdout, stderr, previous = io.StringIO(), io.StringIO(), sys.argv
        real_replace = os.replace
        real_chmod = os.chmod
        real_copyfileobj = shutil.copyfileobj
        payload = json.loads(command[-1])
        failure_stage = payload.pop("_test_failure_stage", None)
        command = [*command[:-1], json.dumps(payload)]
        code = 0
        def sandbox_replace(source, destination):
            source_path, destination_path = Path(source), Path(destination)
            if destination_path.exists(): real_chmod(destination_path, 0o666)
            destination_path.write_bytes(source_path.read_bytes())
            real_chmod(source_path, 0o666)
            source_path.unlink()
        def injected_copyfileobj(source_handle, target_handle, *args, **kwargs):
            if failure_stage == "partial_write":
                target_handle.write(b"partial")
                raise OSError("injected partial write failure")
            if failure_stage == "hash_mismatch":
                target_handle.write(b"corrupt")
                return None
            return real_copyfileobj(source_handle, target_handle, *args, **kwargs)
        def injected_chmod(path, mode, *args, **kwargs):
            if failure_stage == "after_replace" and Path(path) == Path(payload["destination"]):
                raise OSError("injected post-replace permission failure")
            return real_chmod(path, mode, *args, **kwargs)
        try:
            sys.argv = [sys.executable, *command[index + 2:]]
            os.replace = sandbox_replace
            os.chmod = injected_chmod
            shutil.copyfileobj = injected_copyfileobj
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try: exec(compile(command[index + 1], "<adapter-deploy>", "exec"), {"__name__": "__main__"})
                except SystemExit as exc: code = int(exc.code or 0)
        finally:
            sys.argv = previous
            os.replace = real_replace
            os.chmod = real_chmod
            shutil.copyfileobj = real_copyfileobj
        return subprocess.CompletedProcess(command, code, stdout.getvalue(), stderr.getvalue())

    return {"source": source, "target": target, "companion": companion, "runner": local_runner}


def _inject(runner, *, stage: str):
    def injected(command: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        payload = json.loads(command[-1])
        payload["_test_failure_stage"] = stage
        return runner([*command[:-1], json.dumps(payload)], timeout)
    return injected


def test_production_deploy_is_single_file_verified_secure_and_preserves_backups(deployment):
    target = deployment["target"]
    target.write_bytes(b"# old adapter\n")
    os.chmod(target, 0o666)
    historical = target.with_name(target.name + ".backup-attempt-001")
    historical.write_bytes(b"original attempt-001 backup")
    companion_before = deployment["companion"].read_bytes()

    result = runtime.deploy_adapter("test-runtime", runner=deployment["runner"])

    expected = runtime.training._sha256(deployment["source"])
    assert result["status"] == "PASS"
    assert result["action"] == "DEPLOYED"
    assert result["files"] == {target.as_posix(): expected}
    assert result["source_sha256"] == result["destination_sha256"] == expected
    assert target.read_bytes() == deployment["source"].read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) & stat.S_IWOTH == 0
    assert deployment["companion"].read_bytes() == companion_before
    assert historical.read_bytes() == b"original attempt-001 backup"
    assert Path(result["backup"]).read_bytes() == b"# old adapter\n"


def test_repeated_deployment_is_idempotent_and_creates_no_new_backup(deployment):
    first = runtime.deploy_adapter("test-runtime", runner=deployment["runner"])
    backups_before = set(deployment["target"].parent.glob("*.backup-*"))
    second = runtime.deploy_adapter("test-runtime", runner=deployment["runner"])
    assert first["action"] == "DEPLOYED"
    assert second["action"] == "UNCHANGED"
    assert second["backup"] is None
    assert set(deployment["target"].parent.glob("*.backup-*")) == backups_before


@pytest.mark.parametrize("stage", ["partial_write", "hash_mismatch"])
def test_pre_replace_failures_leave_original_untouched_and_clean_temp_files(deployment, stage):
    deployment["target"].write_bytes(b"# original\n")
    with pytest.raises(runtime.training.TrainingControlError) as caught:
        runtime.deploy_adapter("test-runtime", runner=_inject(deployment["runner"], stage=stage))
    assert _error_code(caught.value) == "ADAPTER_DEPLOY_FAILED"
    assert deployment["target"].read_bytes() == b"# original\n"
    assert not list(deployment["target"].parent.glob("*.tmp-*"))


def test_failure_after_atomic_replace_rolls_back_and_retains_backup(deployment):
    deployment["target"].write_bytes(b"# rollback original\n")
    with pytest.raises(runtime.training.TrainingControlError):
        runtime.deploy_adapter("test-runtime", runner=_inject(deployment["runner"], stage="after_replace"))
    assert deployment["target"].read_bytes() == b"# rollback original\n"
    backups = list(deployment["target"].parent.glob("*.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"# rollback original\n"


def test_concurrent_deployment_is_rejected_without_removing_owner_lock(deployment):
    lock = Path(str(deployment["target"]) + ".deploy.lock")
    lock.mkdir()
    with pytest.raises(runtime.training.TrainingControlError) as caught:
        runtime.deploy_adapter("test-runtime", runner=deployment["runner"])
    assert "DEPLOYMENT_IN_PROGRESS" in str(caught.value)
    assert lock.is_dir(), "the rejected contender must not remove the owner's lock"


@pytest.mark.parametrize(
    "worker,local_active",
    [({"state": "BUSY", "current_job_id": "job-1"}, False), ({"state": "IDLE", "current_job_id": None}, True)],
)
def test_active_training_rejected_before_wsl(monkeypatch, deployment, worker, local_active):
    called = False
    monkeypatch.setattr(runtime, "get_worker_state", lambda runtime_id: worker)
    monkeypatch.setattr(runtime, "_active_local_training", lambda: local_active)

    def forbidden_runner(command, timeout):
        nonlocal called
        called = True
        raise AssertionError("WSL boundary must not be reached")

    with pytest.raises(runtime.training.TrainingControlError) as caught:
        runtime.deploy_adapter("test-runtime", runner=forbidden_runner)
    assert _error_code(caught.value) == "ACTIVE_TRAINING"
    assert not called


def test_live_process_detection_from_boundary_is_propagated(deployment):
    failure = {"status": "FAIL", "error": "ACTIVE_TRAINING_PROCESS: {\"pid\":42}"}
    runner = lambda command, timeout: subprocess.CompletedProcess(command, 1, "", json.dumps(failure))
    with pytest.raises(runtime.training.TrainingControlError) as caught:
        runtime.deploy_adapter("test-runtime", runner=runner)
    assert _error_code(caught.value) == "ACTIVE_TRAINING"


def test_invalid_runtime_target_is_rejected(monkeypatch, deployment):
    monkeypatch.setattr(runtime, "get_runtime", lambda runtime_id: {
        "id": runtime_id, "type": "WSL2", "enabled": True,
        "python_path": "/usr/bin/python3", "training_script_path": "/tmp/unexpected.py",
    })
    with pytest.raises(runtime.training.TrainingControlError) as caught:
        runtime.deploy_adapter("test-runtime", runner=deployment["runner"])
    assert _error_code(caught.value) == "INVALID_RUNTIME"
