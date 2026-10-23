"""Integration tests for the search API (src.apiServer).

Runs against the live database; /search uses the real embedding endpoint
(cheap), reranking is pass-through when unconfigured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.apiServer import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestHealthAndFacets:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_facets(self, client):
        r = client.get("/facets")
        assert r.status_code == 200
        body = r.json()
        assert "Beschlussvorlage" in body["paperType"]
        assert body["result"]
        assert body["organization"]


class TestSearch:
    def test_search_returns_contract_sections(self, client):
        r = client.post("/search", json={"query": "Digitalstrategie der Stadt Karlsruhe", "top_k": 5})
        assert r.status_code == 200
        body = r.json()
        for key in ("query", "top_files", "timeline", "graph", "matched_entities",
                    "facets", "applied_filters", "sessionId"):
            assert key in body, f"missing {key}"
        assert body["graph"]["nodes"]
        assert body["graph"]["edges"]
        # session was created
        r2 = client.get(f"/sessions/{body['sessionId']}")
        assert r2.status_code == 200
        assert r2.json()["query"].startswith("Digitalstrategie")

    def test_search_invalid_filter_422(self, client):
        r = client.post("/search", json={"query": "x", "filters": [{"facet": "mood"}]})
        assert r.status_code == 422

    def test_search_filter_echoed(self, client):
        filters = [{"facet": "paperType", "op": "in", "values": ["Antrag"]}]
        r = client.post("/search", json={"query": "Digitalstrategie der Stadt Karlsruhe",
                                         "top_k": 3, "filters": filters})
        assert r.status_code == 200
        assert r.json()["applied_filters"] == filters


class TestSummarize:
    def test_summarize_after_search(self, client):
        r = client.post("/search", json={"query": "Digitalstrategie der Stadt Karlsruhe",
                                         "top_k": 3, "summarize": False})
        assert r.status_code == 200
        body = r.json()
        assert "summary" not in body  # async path: search returns without summary
        r2 = client.post("/summarize", json={"session_id": body["sessionId"]})
        assert r2.status_code == 200
        assert r2.json()["summary"]

    def test_summarize_unknown_session_404(self, client):
        r = client.post("/summarize", json={"session_id": "does-not-exist"})
        assert r.status_code == 404


class TestExpand:
    def test_expand_known_node(self, client):
        r = client.post("/expand", json={"node_id": "Paper_46236"})
        assert r.status_code == 200
        body = r.json()
        assert body["nodes"] and body["edges"]
        ids = {n["id"] for n in body["nodes"]}
        assert "Paper_46236" in ids
        for e in body["edges"]:
            assert e["source"] in ids and e["target"] in ids

    def test_expand_file_finds_papers(self, client):
        r = client.post("/expand", json={"node_id": "File_635289"})
        assert r.status_code == 200
        triples = {(e["source"], e["relation"], e["target"]) for e in r.json()["edges"]}
        assert ("Paper_46236", "auxiliaryFile", "File_635289") in triples

    def test_expand_unknown_node_404(self, client):
        r = client.post("/expand", json={"node_id": "Paper_999999999"})
        assert r.status_code == 404

    def test_expand_malformed_id_404(self, client):
        r = client.post("/expand", json={"node_id": "garbage"})
        assert r.status_code == 404
