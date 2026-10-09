import json
import sqlite3

from app.platform_state import dataset_catalog, platform_status


def test_status_unknown_when_review_evidence_missing(tmp_path):
    (tmp_path / "training" / "jobs").mkdir(parents=True)
    result = platform_status(tmp_path)
    assert result["phase3"]["decision"] == "UNKNOWN"
    assert result["phase4"]["status"] == "UNKNOWN"
    assert "PHASE3_REVIEW_ARTIFACT_UNAVAILABLE" in result["warnings"]


def test_status_reject_blocks_phase4(tmp_path):
    report = tmp_path / "reports" / "phase3-train-20261006-001"
    report.mkdir(parents=True)
    (report / "human-review.json").write_text(json.dumps({"final_gate": {"final_decision": "REJECT", "phase4a": "BLOCKED"}, "summary": {"reviewed": 24, "total": 24}}), encoding="utf-8")
    (tmp_path / "training" / "jobs").mkdir(parents=True)
    result = platform_status(tmp_path)
    assert result["phase4"] == {"status": "BLOCKED", "reason": "PHASE3_REJECT"}


def test_catalog_has_one_item_and_reports_cross_root_duplicate(tmp_path):
    for root in (tmp_path / "exports", tmp_path / "datasets"):
        version = root / "gold-v001"
        version.mkdir(parents=True)
        (version / "manifest.json").write_text(json.dumps({"state": "Frozen"}), encoding="utf-8")
    db = tmp_path / "fixture.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE dataset_versions(version TEXT, export_path TEXT, manifest_json TEXT)")
        conn.execute("INSERT INTO dataset_versions VALUES(?,?,?)", ("gold-v001", str(tmp_path / "exports" / "gold-v001"), '{"state":"Frozen"}'))
    result = dataset_catalog(tmp_path, db)
    assert [item["version"] for item in result["items"]] == ["gold-v001"]
    assert result["conflicts"] == ["gold-v001"]
    assert "DUPLICATE_FILESYSTEM_ID" in result["items"][0]["conflict_reasons"]
