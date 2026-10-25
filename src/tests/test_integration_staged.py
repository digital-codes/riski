"""Integration tests for the staged search contract (change:
progressive-frontend-rendering).

Runs against the live database: /search runs the recall stage, /timeline
and /graph serve stages 2 and 3 for the session."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.apiServer import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def session_id(client):
    r = client.post("/search", json={
        "query": "Digitalstrategie der Stadt Karlsruhe", "top_k": 5,
        "summarize": False,
    })
    assert r.status_code == 200
    return r.json()["sessionId"]


class TestStagedFlow:
    def test_graph_before_timeline_out_of_order(self, client, session_id):
        """Requesting the graph first must compute stage 2 on the way; a
        subsequent /timeline call returns the same session's timeline."""
        rg = client.post("/graph", json={"session_id": session_id})
        assert rg.status_code == 200
        graph_body = rg.json()
        assert graph_body["graph"]["nodes"]
        assert graph_body["graph"]["edges"]
        assert "geo_available" in graph_body

        rt = client.post("/timeline", json={"session_id": session_id})
        assert rt.status_code == 200
        assert isinstance(rt.json()["timeline"], list)

    def test_timeline_endpoint(self, client, session_id):
        rt = client.post("/timeline", json={"session_id": session_id})
        assert rt.status_code == 200
        body = rt.json()
        assert isinstance(body["timeline"], list)

    def test_unknown_session_404(self, client):
        assert client.post("/timeline", json={"session_id": "nope"}).status_code == 404
        assert client.post("/graph", json={"session_id": "nope"}).status_code == 404

    def test_full_staged_flow_matches_monolith(self, client, session_id):
        """search → timeline → graph → summarize → geo: the staged
        pipeline produces the same graph/timeline as the composed
        monolith, and /summarize + /geo work off the staged payload."""
        from src.pgTimeline import get_db_session, search_and_build_timeline

        rs = client.post("/search", json={
            "query": "Digitalstrategie der Stadt Karlsruhe", "top_k": 5,
            "summarize": False,
        })
        sid = rs.json()["sessionId"]
        assert "graph" not in rs.json() and "timeline" not in rs.json()

        rt = client.post("/timeline", json={"session_id": sid})
        assert rt.status_code == 200
        timeline = rt.json()["timeline"]

        rg = client.post("/graph", json={"session_id": sid})
        assert rg.status_code == 200
        graph = rg.json()["graph"]
        geo_available = rg.json()["geo_available"]

        rsum = client.post("/summarize", json={"session_id": sid})
        assert rsum.status_code == 200

        rgeo = client.get(f"/geo/{sid}")
        assert rgeo.status_code == 200
        assert "features" in rgeo.json()

        # parity with the monolithic composition on the same query
        session = get_db_session()
        try:
            mono = search_and_build_timeline(
                session, "Digitalstrategie der Stadt Karlsruhe", top_k=5,
            )
        finally:
            session.close()

        def normalize(obj):
            """JSON round-trip equivalence: datetimes serialize to ISO
            strings in API responses."""
            import datetime as dt

            if isinstance(obj, (dt.datetime, dt.date)):
                return obj.isoformat()
            if isinstance(obj, list):
                return [normalize(x) for x in obj]
            if isinstance(obj, dict):
                return {k: normalize(v) for k, v in obj.items()}
            return obj

        assert [f["oparlKey"] for f in mono["top_files"]] == [
            f["oparlKey"] for f in rs.json()["top_files"]]
        assert normalize(mono["timeline"]) == timeline
        assert {n["id"] for n in mono["graph"]["nodes"]} == {
            n["id"] for n in graph["nodes"]}
        assert {(e["source"], e["relation"], e["target"])
                for e in mono["graph"]["edges"]} == {
            (e["source"], e["relation"], e["target"])
            for e in graph["edges"]}
        assert mono["geo_available"] == geo_available
