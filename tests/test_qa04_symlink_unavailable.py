"""QA-04: symlink and junction refusal is proven without creating real links.

Real-link tests skip where the account cannot create symlinks (common on Windows). These
tests simulate link metadata, so the refusal logic runs on every platform, including the
Windows junction branch that Linux cannot otherwise reach.
"""
from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import integrations

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = stat.S_IFDIR | 0o755
LINK = stat.S_IFLNK | 0o777


@pytest.fixture
def fake_lstat(monkeypatch):
    """Make chosen paths report given metadata; everything else is a plain local directory."""
    overrides: dict[Path, object] = {}

    def lstat(self):
        value = overrides.get(Path(self))
        if isinstance(value, BaseException):
            raise value
        return value or SimpleNamespace(st_mode=DIRECTORY, st_file_attributes=0)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(integrations, "local_filesystem", lambda path: True)
    return overrides


def test_plain_local_marker_is_detected(fake_lstat, tmp_path):
    assert integrations.marker_present(tmp_path, ".lmstudio") is True


def test_marker_that_is_a_symlink_is_refused(fake_lstat, tmp_path):
    fake_lstat[tmp_path / ".lmstudio"] = SimpleNamespace(st_mode=LINK, st_file_attributes=0)
    assert integrations.marker_present(tmp_path, ".lmstudio") is False


def test_symlink_anywhere_in_the_parent_chain_is_refused(fake_lstat, tmp_path):
    fake_lstat[tmp_path] = SimpleNamespace(st_mode=LINK, st_file_attributes=0)
    assert integrations.marker_present(tmp_path, ".lmstudio") is False


def test_windows_junction_reparse_point_is_refused(fake_lstat, tmp_path):
    fake_lstat[tmp_path / ".ollama"] = SimpleNamespace(
        st_mode=DIRECTORY, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
    assert integrations.marker_present(tmp_path, ".ollama") is False


def test_marker_that_is_a_file_is_refused(fake_lstat, tmp_path):
    fake_lstat[tmp_path / ".ollama"] = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_file_attributes=0)
    assert integrations.marker_present(tmp_path, ".ollama") is False


@pytest.mark.parametrize("error", [PermissionError("denied"), FileNotFoundError("gone"), OSError("io")])
def test_unreadable_metadata_is_refused_not_raised(fake_lstat, tmp_path, error):
    fake_lstat[tmp_path / ".lmstudio"] = error
    assert integrations.marker_present(tmp_path, ".lmstudio") is False


def test_network_and_unknown_filesystems_are_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(integrations, "local_filesystem", lambda path: False)
    assert integrations.marker_present(tmp_path, ".lmstudio") is False
    assert integrations.marker_present(Path("//server/share"), ".lmstudio") is False


def test_discovery_reports_not_detected_for_a_simulated_symlink(fake_lstat, tmp_path):
    manager = integrations.IntegrationManager(home=tmp_path)
    marker = integrations.CONNECTORS["lmstudio"].marker
    fake_lstat[tmp_path / marker] = SimpleNamespace(st_mode=LINK, st_file_attributes=0)
    service = next(item for item in manager.discover()["items"] if item["id"] == "lmstudio")
    assert service["installation"] == "NOT_DETECTED"


def _builder():
    spec = importlib.util.spec_from_file_location("candidate_build", ROOT / "public_source" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_candidate_refuses_a_symlinked_source_file_without_real_links(monkeypatch, tmp_path):
    build = _builder()
    policy = json.loads((ROOT / "public_source/policy.json").read_text())
    # Isolate the symlink check from repository classification, which other tests cover.
    monkeypatch.setattr(build, "source_files", lambda root: set(policy["files"]) | set(policy["excluded"]) | {"public_source/policy.json"})
    selected = next(iter(policy["files"]))
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: Path(self) == ROOT / selected or original(self))
    with pytest.raises(ValueError, match="Unsafe source"):
        build.build(ROOT, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_source_candidate_refuses_a_symlinked_output_parent_without_real_links(monkeypatch, tmp_path):
    build = _builder()
    parent = tmp_path / "linked-parent"
    parent.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: Path(self) == parent or original(self))
    with pytest.raises(ValueError, match="Symlink output parent"):
        build.build(ROOT, parent / "candidate")
