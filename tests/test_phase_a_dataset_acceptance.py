"""Phase A acceptance for DATA-01/02/04/05 through the real version, freeze and HTTP paths."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app import dataset_balancer as balancer
from app import dataset_platform as platform
from app import dataset_quality as quality
from app import server as server_module
from tests.http_client import urlopen

SOURCE = "gold-v007-balanced"
DRAFT = "gold-v008-acceptance"


def _row(record_id: str, conversation: str, target: str, turns: int = 1) -> dict:
    messages = []
    for index in range(turns):
        messages.extend([
            {"role": "user", "content": f"سؤال {index}"},
            {"role": "assistant", "content": target if index == turns - 1 else f"رد {index}"},
        ])
    target_index = len(messages) - 1
    return {"id": record_id, "conversation_id": conversation, "messages": messages,
            "target_message_index": target_index, "message_loss_mask": [0] * target_index + [1]}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def exports(tmp_path, monkeypatch):
    root = tmp_path / "exports"
    source = root / SOURCE
    source.mkdir(parents=True)
    _write_jsonl(source / "sft.jsonl", [_row(f"s{i}", f"c{i}", f"هدف أول {i}") for i in range(4)])
    _write_jsonl(source / "multi_turn.jsonl", [_row(f"m{i}", f"mc{i}", f"هدف متعدد {i}", 2) for i in range(4)])
    _write_jsonl(source / "text_sft_eval.jsonl", [_row("e1", "eval-c1", "هدف تقييم")])
    _write_jsonl(source / "evaluation_holdout.jsonl", [_row("h1", "holdout-c1", "هدف معزول")])
    (source / "manifest.json").write_text(json.dumps({
        "version": SOURCE, "created_at": "2026-10-04T20:43:28Z", "source_version": "gold-v006-clean",
        "files": {"sft.jsonl": 4, "multi_turn.jsonl": 4, "text_sft_eval.jsonl": 1, "evaluation_holdout.jsonl": 1},
        "loss_mask_validation": {"passed": 8, "total": 8, "failures": []},
    }), encoding="utf-8")
    monkeypatch.setattr(platform, "EXPORTS_DIR", root)
    return root


def _manifest(root: Path, version: str) -> dict:
    return json.loads((root / version / "manifest.json").read_text(encoding="utf-8"))


def _rewrite_manifest(root: Path, version: str, **drop: bool) -> None:
    manifest = _manifest(root, version)
    for key in drop:
        manifest.pop(key, None)
    (root / version / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ---------------------------------------------------------------------------
# DATA-01: a Frozen Gold export always carries matching diagnostics and loss-mask metadata
# ---------------------------------------------------------------------------

def test_data01_frozen_manifest_contains_current_diagnostics_and_loss_masks(exports):
    platform.create_derived_version(SOURCE, DRAFT)
    platform.freeze_dataset_version(DRAFT)
    manifest = _manifest(exports, DRAFT)
    directory = exports / DRAFT
    assert manifest["state"] == "Frozen"
    fingerprint = platform._training_fingerprint(directory)
    diagnostics, loss = manifest["diagnostics"], manifest["loss_mask_validation"]
    assert diagnostics["version"] == DRAFT and diagnostics["training_fingerprint"] == fingerprint
    assert set(diagnostics["artifacts"]) == {"loss-mask-validation.json", "balancing_report.json"}
    for name, digest in diagnostics["artifacts"].items():
        assert platform._sha256(directory / name) == digest
    assert loss["version"] == DRAFT and loss["training_fingerprint"] == fingerprint
    assert loss["total"] == loss["passed"] == 8 and loss["failures"] == []


@pytest.mark.parametrize("missing", ["diagnostics", "loss_mask_validation"])
def test_data01_freeze_refuses_draft_without_metadata_and_leaves_it_draft(exports, missing):
    platform.create_derived_version(SOURCE, DRAFT)
    _rewrite_manifest(exports, DRAFT, **{missing: True})
    with pytest.raises(platform.DatasetPlatformError) as raised:
        platform.freeze_dataset_version(DRAFT)
    assert raised.value.code == "INVALID_MANIFEST"
    assert _manifest(exports, DRAFT)["state"] == "Draft"


def test_data01_regenerating_diagnostics_makes_freeze_possible(exports):
    platform.create_derived_version(SOURCE, DRAFT)
    _rewrite_manifest(exports, DRAFT, diagnostics=True, loss_mask_validation=True)
    platform.regenerate_training_diagnostics(DRAFT)
    platform.freeze_dataset_version(DRAFT)
    assert _manifest(exports, DRAFT)["state"] == "Frozen"


def test_data01_freeze_refuses_stale_diagnostics_after_training_change(exports):
    platform.create_derived_version(SOURCE, DRAFT)
    rows = platform._jsonl(exports / DRAFT / "sft.jsonl")
    platform._write_jsonl(exports / DRAFT / "sft.jsonl", rows[:-1])
    with pytest.raises(platform.DatasetPlatformError, match="stale"):
        platform.freeze_dataset_version(DRAFT)
    assert _manifest(exports, DRAFT)["state"] == "Draft"


def test_data01_freeze_refuses_version_with_no_training_records(exports):
    empty = exports / "gold-v009-empty"
    empty.mkdir()
    (empty / "manifest.json").write_text(json.dumps({"version": "gold-v009-empty", "state": "Draft", "sha256": {}}), encoding="utf-8")
    with pytest.raises(platform.DatasetPlatformError, match="no training records"):
        platform.freeze_dataset_version("gold-v009-empty")


# ---------------------------------------------------------------------------
# DATA-02: a valid dataset is READY; absent diagnostics give an actionable reason
# ---------------------------------------------------------------------------

def test_data02_valid_draft_is_ready_with_valid_diagnostics(exports):
    platform.create_derived_version(SOURCE, DRAFT)
    health = platform.dataset_health(DRAFT)
    assert health["training_readiness"]["status"] == "READY"
    assert health["diagnostics"]["valid"] is True
    assert "stale_diagnostics" not in {w["code"] for w in health["warnings"]}


def test_data02_draft_without_diagnostics_explains_how_to_recover(exports):
    platform.create_derived_version(SOURCE, DRAFT)
    _rewrite_manifest(exports, DRAFT, diagnostics=True)
    health = platform.dataset_health(DRAFT)
    assert health["training_readiness"]["status"] == "NOT_READY"
    assert "not been generated" in health["diagnostics"]["error"]
    assert "Regenerate Diagnostics" in health["diagnostics"]["error"]


def test_data02_legacy_version_without_diagnostics_is_not_downgraded(exports):
    """Versions without a Draft/Frozen state (pre-diagnostics releases) keep their READY status."""
    health = platform.dataset_health(SOURCE)
    assert health["training_readiness"]["status"] == "READY"


# ---------------------------------------------------------------------------
# DATA-04: Health, Balancer, Quality and Unsloth export agree on the version file set
# ---------------------------------------------------------------------------

def test_data04_holdout_and_native_files_are_supported_by_balancer_and_quality(exports):
    version = exports / SOURCE
    native = _row("n1", "native-c1", "هدف أداة")
    native["messages"].insert(1, {"role": "tool", "content": "{}"})
    _write_jsonl(version / platform.NATIVE_TRAIN_FILE, [native])

    balance = balancer.analyze_dataset_balance(SOURCE)
    assert "UNSUPPORTED_RECORDS" not in {w["code"] for w in balance["warnings"]}
    assert balance["record_types"]["counts"].get("unknown", 0) == 0
    assert balance["record_types"]["counts"]["evaluation"] == 2
    assert balance["record_types"]["counts"]["native_tool_use"] == 1

    names = set(quality.EVAL_FILES) | set(quality.KNOWN_FILES)
    assert {"evaluation_holdout.jsonl", "text_sft_eval.jsonl"} <= names


def test_data04_unknown_file_is_still_reported(exports):
    _write_jsonl(exports / SOURCE / "unexpected.jsonl", [_row("x1", "x", "غير معروف")])
    balance = balancer.analyze_dataset_balance(SOURCE)
    assert "UNSUPPORTED_RECORDS" in {w["code"] for w in balance["warnings"]}


# ---------------------------------------------------------------------------
# DATA-05: an empty installation reports "no versions", not an error or endless loading
# ---------------------------------------------------------------------------

def test_data05_empty_installation_returns_empty_catalog_over_http(tmp_path):
    missing = tmp_path / "fresh-install" / "exports"
    datasets = tmp_path / "fresh-install" / "datasets"
    with patch.object(platform, "EXPORTS_ROOT", missing), patch.object(platform, "EXPORTS_DIR", missing), \
            patch.object(platform, "DATASETS_ROOT", datasets):
        server = server_module.NajdiLabHTTPServer(("127.0.0.1", 0), server_module.NajdiLabHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/v1/dataset-versions", timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    assert payload == {"items": []}
    assert missing.is_dir()


def test_data05_ui_renders_terminal_empty_state_for_empty_catalog():
    source = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    assert "if(!state.datasetVersions.length){select.innerHTML='';button.disabled=true;$('#health-state').textContent='No dataset versions are available to check.';return;}" in source
    assert "$('#balance-state').textContent='No dataset versions.';return;}" in source
