"""Integration test for the /summarize refine flow (summary-refine-file-control).

Runs the FastAPI app with a real DB session (read-only access to the live
`File` table — no writes happen) and a stubbed chat client (no real LLM
call). Skips when the live DB or a real File row is unavailable.
"""

import pytest
from fastapi.testclient import TestClient

import src.search.apiServer as api
import src.remote as remote_mod

pytestmark = pytest.mark.integration


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture()
def live_file_rows():
    """Two real rows from the live File table — skipped when the DB is
    unreachable."""
    try:
        from sqlalchemy import text
        db = api.get_db_session()
        try:
            rows = db.execute(text(
                'SELECT "oparlKey", name, filename FROM "File" '
                'WHERE content IS NOT NULL ORDER BY sid DESC LIMIT 2'
            )).all()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - DB down
        pytest.skip(f"live DB unavailable: {exc}")
    if len(rows) < 2:
        pytest.skip("live File table has fewer than 2 rows with content")
    return rows


def test_refine_flow_updates_session_result(client, live_file_rows, monkeypatch):
    (key_a, name_a, file_a), (key_b, name_b, file_b) = live_file_rows
    api._sessions.clear()
    session_id = "test-refine-1"
    api._sessions[session_id] = {"result": {
        "query": "Testfrage",
        "top_files": [
            {"oparlKey": key_a, "name": name_a, "fileName": file_a},
            {"oparlKey": key_b, "name": name_b, "fileName": file_b},
        ],
    }}

    llm_calls = []

    def fake_chat(messages, **kwargs):
        llm_calls.append(messages[1]["content"])
        return {"content": "Zusammenfassung.", "model": "stub",
                "endpoint": "http://stub", "usage": {"total_tokens": 10}}

    monkeypatch.setattr(remote_mod, "chat", fake_chat)

    # 1) automatic (teaser) pass
    r1 = client.post("/summarize", json={"session_id": session_id})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["summary"]
    assert [f["oparlKey"] for f in body1["files"]] == [key_a, key_b]
    assert "Dokumente (Teaser):" in llm_calls[0]
    assert name_a in llm_calls[0] and name_b in llm_calls[0]
    # the stored summary is clean of the document list (frontend renders it
    # from the structured metadata)
    assert "**Dokumente:**" not in body1["summary"]
    assert body1["files"][0]["downloadUrl"] is not None

    # 2) non-refine repeat returns the stored summary without an LLM call
    calls_before = len(llm_calls)
    r2 = client.post("/summarize", json={"session_id": session_id})
    assert r2.json()["summary"] == body1["summary"]
    assert len(llm_calls) == calls_before

    # 3) refine re-runs with full content and keeps the result in the session
    r3 = client.post("/summarize", json={"session_id": session_id, "refine": True})
    assert r3.status_code == 200
    assert "Dokumente (Volltext):" in llm_calls[-1]
    assert len(llm_calls) == calls_before + 1
    stored = api._sessions[session_id]["result"]
    assert stored["summary_refused"] == []

    # 4) exclude persists in the session and is honoured by a re-run:
    #    the summarizer's document list matches the selection exactly
    r4 = client.post("/summarize", json={"session_id": session_id,
                                         "refine": True, "exclude": [key_a]})
    assert r4.status_code == 200
    files4 = {f["oparlKey"]: f for f in r4.json()["files"]}
    assert files4[key_a]["excluded"] is True and files4[key_b]["excluded"] is False
    stored = api._sessions[session_id]["result"]
    assert stored["summary_excluded"] == [key_a]
    # the excluded file did NOT enter the prompt; the other one did
    assert name_a not in llm_calls[-1]
    assert name_b in llm_calls[-1]
    calls_after_exclude = len(llm_calls)

    # 5) re-including the file (user clicks it back on) must REMOVE it from
    #    the exclusion set — replace, not union (user finding: the file
    #    snapped back and never entered the summarizer)
    r5 = client.post("/summarize", json={"session_id": session_id,
                                         "refine": True, "exclude": []})
    assert r5.status_code == 200
    files5 = {f["oparlKey"]: f for f in r5.json()["files"]}
    assert files5[key_a]["excluded"] is False
    stored = api._sessions[session_id]["result"]
    assert stored["summary_excluded"] == []
    # the summarizer now sees the re-included document again
    assert name_a in llm_calls[-1] and name_b in llm_calls[-1]
    # exactly ONE summarizer run per click — no queued second run
    assert len(llm_calls) == calls_after_exclude + 1

    api._sessions.clear()
