"""Guard/metadata proof only. A blocked native collector earns no capture PASS."""
import builtins
import copy
import os
import sqlite3
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app.native_capture import NativeCaptureDiagnostics, NativeCaptureError

KEYS = ("hermes", "lmstudio", "ollama")


@pytest.fixture
def sources(tmp_path):
    paths = {"hermes": tmp_path / ".hermes/state.db", "lmstudio": tmp_path / ".lmstudio/conversations", "ollama": tmp_path / "AppData/Local/Ollama/db.sqlite"}
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "lmstudio":
            path.mkdir()
            (path / "synthetic.json").write_text('{"user":"synthetic private history","assistant":"not a proven completed turn","token":"sentinel-never-read"}', encoding="utf-8")
        else:
            # Deliberately not claiming these are compatible upstream schemas.
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE synthetic_private_history(user TEXT, assistant TEXT)")
                db.execute("INSERT INTO synthetic_private_history VALUES ('old synthetic prompt','old synthetic response')")
                db.execute("PRAGMA user_version=999")
            db.close()
            for suffix in ("-wal", "-shm"):
                path.with_name(path.name + suffix).write_bytes(b"synthetic-sidecar-secret-never-read")
    return paths


@pytest.fixture
def native(tmp_path):
    return NativeCaptureDiagnostics(home=tmp_path, local_app_data=tmp_path / "AppData/Local", platform="win32")


def block_content_reads():
    real_open = builtins.open

    def guard(file, *args, **kwargs):
        # Shared Linux locality validation may read bounded kernel mount metadata.
        if str(file) == "/proc/self/mountinfo":
            return real_open(file, *args, **kwargs)
        raise AssertionError("No source content may be opened")

    return patch("builtins.open", guard)


def fingerprints(paths):
    result = {}
    for path in paths.values():
        files = [path / "synthetic.json"] if path.is_dir() else [path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")]
        for file in files:
            info = file.stat()
            result[str(file)] = (file.read_bytes(), info.st_size, info.st_mtime_ns)
    return result


def test_snapshot_is_passive_and_defaults_to_off(native):
    with patch.object(Path, "lstat", side_effect=AssertionError("Snapshot must be passive")):
        for key in KEYS:
            state = native.snapshot(key)
            assert state["enabled"] is False
            assert state["connection"] == "DISCONNECTED"
            assert state["last_capture_at"] is None
            assert state["version"] == "NOT_VERIFIED"
            assert state["source_status"] == "NOT_CHECKED"


@pytest.mark.parametrize("key", KEYS)
def test_discovery_is_metadata_only_never_reads_source_or_opens_sqlite(native, sources, key):
    before = fingerprints(sources)
    with block_content_reads(), patch.object(Path, "open", side_effect=AssertionError("No file contents")), patch.object(Path, "iterdir", side_effect=AssertionError("No chat enumeration")), patch.object(sqlite3, "connect", side_effect=AssertionError("No source SQL")):
        native.discover()
        state = native.snapshot(key)
    assert state["source_status"] == "DETECTED"
    assert state["capability"] in {"BLOCKED", "UNSUPPORTED"}
    assert state["enabled"] is False
    assert state["format_verification"] == "NOT_TESTED"
    assert str(sources[key]) not in str(state)
    assert "sentinel" not in str(state)
    assert fingerprints(sources) == before


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("action", ["connect", "enable", "disable", "disconnect", "path"])
@pytest.mark.parametrize("approved", [None, False, 1, "true"])
def test_native_actions_require_separate_exact_consent(native, key, action, approved):
    with pytest.raises(NativeCaptureError) as exc:
        native.action(key, action, {"approved": approved})
    assert exc.value.code == "APPROVAL_REQUIRED"
    assert native.snapshot(key)["enabled"] is False


@pytest.mark.parametrize("key", KEYS)
def test_even_plausible_or_corrupt_source_cannot_enable_capture(native, sources, key):
    native.discover()
    for action in ("connect", "enable"):
        with block_content_reads(), patch.object(sqlite3, "connect", side_effect=AssertionError("No source SQL")):
            with pytest.raises(NativeCaptureError) as exc:
                native.action(key, action, {"approved": True})
        assert exc.value.status == 409
        assert exc.value.code == ("NATIVE_CAPTURE_UNSUPPORTED" if key == "lmstudio" else "NATIVE_CAPTURE_BLOCKED")
    assert native.snapshot(key)["connection"] == "DISCONNECTED"
    assert native.snapshot(key)["enabled"] is False
    assert native.snapshot(key)["last_capture_at"] is None


@pytest.mark.parametrize("key", KEYS)
def test_disable_disconnect_and_restart_preserve_sources(native, sources, tmp_path, key):
    before = fingerprints(sources)
    native.discover()
    native.action(key, "disable", {"approved": True})
    native.action(key, "disconnect", {"approved": True})
    state = native.snapshot(key)
    assert state["local_disconnect_verified"] is True
    assert state["enabled"] is False
    assert state["connection"] == "DISCONNECTED"
    assert state["last_action_at"]
    fresh = NativeCaptureDiagnostics(home=tmp_path, local_app_data=tmp_path / "AppData/Local", platform="win32")
    assert fresh.snapshot(key)["enabled"] is False
    assert fresh.snapshot(key)["last_capture_at"] is None
    assert fingerprints(sources) == before


def test_manual_path_is_only_available_after_automatic_source_is_missing(native, sources, tmp_path):
    target = tmp_path / "chosen/state.db"
    target.parent.mkdir()
    target.write_bytes(b"unknown-format-synthetic")
    with pytest.raises(NativeCaptureError) as exc:
        native.action("hermes", "path", {"approved": True, "path": str(target)})
    assert exc.value.code == "AUTO_SOURCE_AVAILABLE"
    sources["hermes"].unlink()
    with block_content_reads():
        native.action("hermes", "path", {"approved": True, "path": str(target)})
    state = native.snapshot("hermes")
    assert state["source_status"] == "DETECTED"
    assert state["source_location"] == "CUSTOM"
    assert state["version"] == "NOT_VERIFIED"
    assert state["enabled"] is False
    assert str(target) not in str(state)


@pytest.mark.parametrize("value", ["state.db", "../state.db", "http://127.0.0.1/state.db", "file:///state.db", "//server/share/state.db", "\\\\server\\share\\state.db", "\\\\?\\C:\\state.db", "C:\\state.db:secret", "C:\\bad\x00/state.db", 3, ["state.db"]])
def test_manual_path_rejects_network_device_relative_stream_and_bad_types(native, value):
    with pytest.raises(NativeCaptureError):
        native.action("hermes", "path", {"approved": True, "path": value})
    assert native.snapshot("hermes")["source_location"] == "DEFAULT"


def test_missing_inaccessible_and_unverified_local_paths_fail_closed(native, tmp_path):
    from app import local_sources
    native.discover()
    assert native.snapshot("hermes")["source_status"] == "MISSING"
    backend = "_windows_metadata" if os.name == "nt" else "_posix_metadata"
    with patch.object(local_sources, backend, create=True, side_effect=PermissionError("sensitive-private-path")):
        native.discover()
    state = native.snapshot("hermes")
    assert state["source_status"] == "INACCESSIBLE"
    assert "sensitive-private-path" not in str(state)


def test_simultaneous_source_changes_never_enable_or_import(native, sources):
    path = sources["hermes"]
    ready = threading.Barrier(2)

    def writer():
        ready.wait()
        for i in range(20):
            path.write_bytes(b"synthetic-concurrent-change-" + str(i).encode())

    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    ready.wait()
    for _ in range(20):
        native.discover()
        assert native.snapshot("hermes")["enabled"] is False
    writer_thread.join(3)
    assert not writer_thread.is_alive()
    assert native.snapshot("hermes")["last_capture_at"] is None


def test_returned_snapshot_cannot_change_guard_state(native):
    state = native.snapshot("ollama")
    state["enabled"] = True
    state["capability"] = "SUPPORTED"
    assert native.snapshot("ollama")["enabled"] is False
    assert native.snapshot("ollama")["capability"] == "BLOCKED"


def test_no_linux_ollama_desktop_db_is_invented(tmp_path):
    native = NativeCaptureDiagnostics(home=tmp_path, local_app_data=tmp_path / "unused", platform="linux")
    native.discover()
    assert native.snapshot("ollama")["source_status"] == "NOT_APPLICABLE"
    assert native.snapshot("ollama")["capability"] == "BLOCKED"


def test_source_selection_rejects_unexpected_fields_and_filename(native, tmp_path):
    for payload in ({"approved": True, "url": "http://evil"}, {"approved": True, "path": str(tmp_path / "credentials.json")}):
        with pytest.raises(NativeCaptureError):
            native.action("hermes", "path", payload)


def test_unknown_metadata_platform_fails_closed_without_path_stat(tmp_path):
    from app import local_sources
    with patch.object(local_sources.os, "name", "unknown"), patch.object(local_sources, "local_filesystem", return_value=True), patch.object(Path, "lstat", side_effect=AssertionError("Unpinned path traversal must not run")):
        assert local_sources.source_metadata(tmp_path / "state.db", "file") == "UNSAFE_PATH"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction resolution")
def test_ancestor_replaced_with_junction_is_refused_at_open(tmp_path):
    from app import local_sources
    parent, saved, outside = [tmp_path / name for name in ("parent", "saved", "outside")]
    parent.mkdir()
    outside.mkdir()
    (parent / "state.db").write_bytes(b"synthetic original")
    (outside / "state.db").write_bytes(b"synthetic outside must not be traversed")
    real_backend = local_sources._windows_metadata

    def replace_before_open(path, kind):
        assert parent.resolve().is_relative_to(tmp_path.resolve())
        assert saved.absolute().is_relative_to(tmp_path.resolve())
        parent.rename(saved)
        env = {**os.environ, "NAJDILAB_TEST_JUNCTION": str(parent), "NAJDILAB_TEST_TARGET": str(outside)}
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', 'New-Item -ItemType Junction -Path $env:NAJDILAB_TEST_JUNCTION -Target $env:NAJDILAB_TEST_TARGET -ErrorAction Stop | Out-Null'], env=env, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            pytest.fail("Isolated junction fixture creation failed; no safety skip")
        return real_backend(path, kind)

    with patch.object(local_sources, "_windows_metadata", replace_before_open):
        assert local_sources.source_metadata(parent / "state.db", "file") == "UNSAFE_PATH"
    assert (outside / "state.db").read_bytes() == b"synthetic outside must not be traversed"


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_PATH"), reason="Linux pinned metadata descriptors")
def test_ancestor_replacement_cannot_redirect_pinned_descriptor(tmp_path):
    from app import local_sources
    parent, saved, outside = [tmp_path / name for name in ("parent", "saved", "outside")]
    parent.mkdir()
    outside.mkdir()
    (parent / "state.db").write_bytes(b"synthetic original")
    (outside / "state.db").mkdir()  # Wrong type if resolution follows replacement.
    real_backend = local_sources._posix_metadata

    def replace_before_lookup(path, kind):
        parent.rename(saved)
        parent.symlink_to(outside, target_is_directory=True)
        return real_backend(path, kind)

    with patch.object(local_sources, "_posix_metadata", replace_before_lookup):
        assert local_sources.source_metadata(parent / "state.db", "file") == "UNSAFE_PATH"
    assert (saved / "state.db").read_bytes() == b"synthetic original"


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_PATH"), reason="Linux kernel mount boundary")
def test_kernel_refuses_mount_crossing_even_if_lexical_check_is_stale():
    from app import local_sources
    with patch.object(local_sources, "local_filesystem", return_value=True):
        # /proc is a distinct kernel filesystem; no content or app data is read.
        assert local_sources.source_metadata(Path("/proc"), "directory") == "UNSAFE_PATH"


def test_refused_capture_preserves_existing_pending_queue(native, sources, tmp_path):
    from app.db import apply_migrations
    from app.service import ingest_turn
    own_db = tmp_path / "najdilab-own.db"
    apply_migrations(own_db)
    # This seeds an existing queue item; it is NOT a native capture success.
    ingest_turn({"conversation_id": "fixture-existing", "user_message": "existing synthetic prompt", "assistant_response": "existing synthetic response", "demo": True}, own_db)

    def queue_state():
        db = sqlite3.connect(own_db)
        try:
            return db.execute("SELECT review_status, original_response, training_eligible FROM reviews").fetchall()
        finally:
            db.close()

    before = queue_state()
    assert before == [("PENDING", "existing synthetic response", 0)]
    with patch.object(sqlite3, "connect", side_effect=AssertionError("No database access from native guards")), block_content_reads():
        native.discover()
        for key in KEYS:
            with pytest.raises(NativeCaptureError):
                native.action(key, "enable", {"approved": True})
            native.action(key, "disable", {"approved": True})
            native.action(key, "disconnect", {"approved": True})
    assert queue_state() == before
