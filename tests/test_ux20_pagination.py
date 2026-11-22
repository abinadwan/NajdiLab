"""UX-20: bounded server-side paging that never drops or duplicates records."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app import server, service
from app.chat_history import saved_sessions_page
from app.chat_workspace import ChatWorkspace
from app.integrations import IntegrationManager
from tests.http_client import urlopen
from tests.test_review_management import add_pending, fixture_db


def _approve_all(db: Path, ids: list[int], updated_at: str = "2026-01-01T00:00:00Z") -> None:
    # Identical timestamps force the id tie-breaker to decide page boundaries.
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "UPDATE reviews SET review_status='APPROVED', reviewer='human', updated_at=? WHERE id=?",
            [(updated_at, i) for i in ids],
        )


def _pages(fetch, limit: int) -> list[dict]:
    pages, offset = [], 0
    while True:
        page = fetch({"limit": str(limit), "offset": str(offset)})
        pages.append(page)
        if not page["page"]["has_more"]:
            return pages
        offset += limit


@pytest.mark.parametrize("query, expected", [
    ({}, (service.PAGE_DEFAULT_LIMIT, 0)),
    ({"limit": "1", "offset": "0"}, (1, 0)),
    ({"limit": str(service.PAGE_MAX_LIMIT), "offset": "7"}, (service.PAGE_MAX_LIMIT, 7)),
    ({"limit": "", "offset": ""}, (service.PAGE_DEFAULT_LIMIT, 0)),
])
def test_page_request_accepts_bounded_values(query, expected):
    assert service.page_request(query) == expected


@pytest.mark.parametrize("query", [
    {"limit": "0"}, {"limit": str(service.PAGE_MAX_LIMIT + 1)}, {"limit": "-5"}, {"limit": "abc"},
    {"limit": "1.5"}, {"offset": "-1"}, {"offset": "x"},
])
def test_page_request_rejects_out_of_range_values_instead_of_clamping(query):
    with pytest.raises(service.ValidationError):
        service.page_request(query)


def test_reviewed_pages_cover_every_record_exactly_once(tmp_path):
    db = fixture_db(tmp_path)
    ids = [add_pending(db, f"r{i}") for i in range(7)]
    _approve_all(db, ids)
    pages = _pages(lambda q: service.reviewed_page(q, db), 3)
    assert [p["page"]["returned"] for p in pages] == [3, 3, 1]
    assert all(p["page"]["total"] == 7 for p in pages)
    seen = [item["id"] for p in pages for item in p["items"]]
    assert sorted(seen) == sorted(ids) and len(seen) == len(set(seen))
    assert seen == sorted(ids, reverse=True), "ties are ordered deterministically by id"


def test_reviewed_filters_apply_to_total_and_pages(tmp_path):
    db = fixture_db(tmp_path)
    ids = [add_pending(db, f"f{i}") for i in range(4)]
    _approve_all(db, ids)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE reviews SET training_eligible=1 WHERE id IN (?,?)", (ids[0], ids[1]))
    page = service.reviewed_page({"training_eligible": "1", "limit": "1"}, db)
    assert page["page"]["total"] == 2 and page["page"]["returned"] == 1 and page["page"]["has_more"]


def test_core_list_contracts_are_unchanged(tmp_path):
    db = fixture_db(tmp_path)
    ids = [add_pending(db, f"k{i}") for i in range(3)]
    _approve_all(db, ids)
    assert isinstance(service.list_reviewed({}, db), list) and len(service.list_reviewed({}, db)) == 3
    assert isinstance(service.list_conversations(db), list) and len(service.list_conversations(db)) == 3


def test_conversation_pages_cover_every_record_exactly_once(tmp_path):
    db = fixture_db(tmp_path)
    for i in range(5):
        add_pending(db, f"c{i}")
    pages = _pages(lambda q: service.conversations_page(q, db), 2)
    seen = [item["id"] for p in pages for item in p["items"]]
    assert len(seen) == 5 == len(set(seen)) and pages[0]["page"]["total"] == 5
    assert pages[-1]["page"]["has_more"] is False


def test_conversation_search_counts_only_matching_records(tmp_path):
    db = fixture_db(tmp_path)
    for suffix in ("alpha", "beta", "alphabet"):
        add_pending(db, suffix)
    page = service.conversations_page({"search": "alpha"}, db)
    assert page["page"]["total"] == 2 and {i["external_conversation_id"] for i in page["items"]} == {"c-alpha", "c-alphabet"}


def test_manual_data_pages_while_summary_covers_all_records(tmp_path):
    db = fixture_db(tmp_path)
    for i in range(5):
        service.add_direct_text({"text": f"نص {i}", "language_layer": "najdi_riyadh", "source_type": "human_written"}, db)
    first = service.list_manual_data({"limit": "2"}, db)
    assert first["summary"]["total"] == 5 and len(first["items"]) == 2
    assert first["page"] == {"total": 5, "limit": 2, "offset": 0, "returned": 2, "has_more": True,
                             "max_limit": service.PAGE_MAX_LIMIT}
    seen = [i["id"] for p in _pages(lambda q: service.list_manual_data(q, db), 2) for i in p["items"]]
    assert len(seen) == 5 == len(set(seen))


def test_page_past_the_end_is_empty_but_reports_total(tmp_path):
    db = fixture_db(tmp_path)
    add_pending(db, "only")
    page = service.conversations_page({"offset": "50"}, db)
    assert page["items"] == [] and page["page"]["total"] == 1 and page["page"]["has_more"] is False


def test_chat_sessions_are_paged_and_archived_sessions_excluded(tmp_path):
    db = fixture_db(tmp_path)
    rows = [(f"00000000-0000-0000-0000-00000000000{i}", "ollama", "m", 4096, 512,
             "ARCHIVED" if i == 0 else "OPEN", "2026-01-01T00:00:00Z") for i in range(6)]
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO chat_sessions(id,provider,model,context_budget,reply_reserve,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)", [(*r, r[-1]) for r in rows])
    seen, offset = [], 0
    while True:
        items, total = saved_sessions_page(db, 2, offset)
        assert total == 5
        seen += [item["id"] for item in items]
        offset += 2
        if offset >= total:
            break
    assert len(seen) == 5 == len(set(seen))
    assert rows[0][0] not in seen, "archived sessions stay out of the saved list"


def _serve(db: Path):
    names = ("reviewed_page", "conversations_page", "list_manual_data")
    patches = [patch.object(server, name, lambda query, _n=name: getattr(service, _n)(query, db)) for name in names]
    for item in patches:
        item.start()
    http = server.NajdiLabHTTPServer(("127.0.0.1", 0), server.NajdiLabHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    return http, thread, patches


@pytest.mark.parametrize("path", ["/api/v1/reviewed", "/api/v1/conversations", "/api/v1/manual-data", "/api/v1/chat/sessions"])
def test_http_rejects_oversized_page_and_reports_page_metadata(tmp_path, path):
    db = fixture_db(tmp_path)
    http, thread, patches = _serve(db)
    http.chat = ChatWorkspace(IntegrationManager(home=tmp_path), db)
    base = f"http://127.0.0.1:{http.server_port}"
    try:
        with pytest.raises(HTTPError) as raised:
            urlopen(base + path + f"?limit={service.PAGE_MAX_LIMIT + 1}", timeout=10)
        assert raised.value.code == 400
        with urlopen(base + path + "?limit=5", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["page"]["limit"] == 5 and payload["page"]["total"] == 0 and payload["items"] == []
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)
        for item in patches:
            item.stop()
