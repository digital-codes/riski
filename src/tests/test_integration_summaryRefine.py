"""Integration test for the /summarize refine flow (summary-refine-file-control).

Runs the FastAPI app with a real DB session (read-only access to the live
`File` table — no writes happen) and a stubbed chat client (no real LLM
call). Skips when the live DB or a real File row is unavailable.
"""

import pytest
from fastapi.testclient import TestClient

import src.apiServer as api
import src.remote as remote_mod

pytestmark = pytest.mark.integration


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture()
def live_file_row():
    """One real oparlKey from the live File table (with a download URL if
    available) — skipped when the DB is unreachable."""
    try:
        from sqlalchemy import text
        db = api.get_db_session()
        try:
            row = db.execute(text(
                'SELECT "oparlKey", name, filename FROM "File" '
                'WHERE content IS NOT NULL ORDER BY sid DESC LIMIT 1'
            )).first()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - DB down
        pytest.skip(f"live DB unavailable: {exc}")
    if row is None:
        pytest.skip("live File table is empty")
    return row


def test_refine_flow_updates_session_result(client, live_file_row, monkeypatch):
    oparl_key, name, filename = live_file_row
    api._sessions.clear()
    session_id = "test-refine-1"
    api._sessions[session_id] = {"result": {
        "query": "Testfrage",
        "top_files": [{"oparlKey": oparl_key, "name": name, "fileName": filename}],
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
    assert body1["files"][0]["oparlKey"] == oparl_key
    assert "Dokumente (Teaser):" in llm_calls[0]
    # file list above the provenance footer
    assert body1["summary"].find("**Dokumente:**") < body1["summary"].find("Endpunkt:")

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

    # 4) exclude persists in the session and is honoured by a re-run
    r4 = client.post("/summarize", json={"session_id": session_id,
                                         "refine": True, "exclude": [oparl_key]})
    assert r4.status_code == 200
    assert r4.json()["files"][0]["excluded"] is True
    stored = api._sessions[session_id]["result"]
    assert stored["summary_excluded"] == [oparl_key]

    api._sessions.clear()
