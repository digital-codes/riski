"""Integration test: agenda-block document expansion (change:
agenda-sibling-documents). Runs a real query whose hit is a TOP-bound
document and verifies the block expansion end-to-end via /summarize."""

import json

import pytest
from fastapi.testclient import TestClient

from src.apiServer import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestAgendaBlockExpansion:
    def test_sibling_documents_join_the_answer_set(self, client):
        # file 662510 belongs to TOP 9.3 (Bauantrag Am Knittelberg 107),
        # whose meeting has 6 sibling TOPs (9.1, 9.2, ...) — a name query on
        # the agenda item must pull the whole block into the answer set
        r = client.post("/ask", json={
            "query": "Bauantrag Am Knittelberg 107", "top_k": 10,
            "summarize": False,
        })
        assert r.status_code == 200
        result = r.json()
        sid = result["sessionId"]

        # the agenda item or its documents must be among the matched entities
        matched = result.get("matched_entities", [])
        agenda_hits = [m for m in matched if m.get("type") == "AgendaItem"
                       and "knittelberg" in (m.get("name") or "").lower()]
        assert agenda_hits, "agenda item not matched by name"

        # expansion runs with the summary call; content-reference rule:
        # block documents without stored text (enrichment pending for the
        # new imports) are NOT included — the unrelated-block flood from
        # the pre-fix behavior (60 docs) must not return
        rs = client.post("/summarize", json={"session_id": sid})
        assert rs.status_code == 200
        files = rs.json().get("files", [])
        keys = [f["oparlKey"] for f in files]
        assert len(keys) == len(set(keys)), "duplicates in the answer set"
        assert len(keys) <= 60, "unrelated-block flood is back"
        for f in files:
            if f.get("via"):
                assert f["via"].startswith("TOP ")

        # /timeline (stage 2) shares the traversal — the graph carries the
        # block's agenda items and their documents as nodes
        rg = client.post("/graph", json={"session_id": sid})
        assert rg.status_code == 200
        nodes = rg.json()["graph"]["nodes"]
        agenda_nodes = [n for n in nodes
                        if n["type"] == "AgendaItem"
                        and "knittelberg" in (n.get("name") or "").lower()]
        assert agenda_nodes, "agenda item missing from the graph"
        aux_nodes = [n for n in nodes if n["type"] == "AuxFile"]
        assert aux_nodes, "agenda-block documents missing from the graph"

    def test_expansion_is_idempotent_per_session(self, client):
        r = client.post("/ask", json={
            "query": "Bauantrag Am Knittelberg 107", "top_k": 10,
            "summarize": False,
        })
        sid = r.json()["sessionId"]
        client.post("/summarize", json={"session_id": sid})
        r1 = client.post("/summarize", json={"session_id": sid})
        n1 = len(r1.json().get("files", []))
        r2 = client.post("/summarize", json={"session_id": sid, "refine": True})
        n2 = len(r2.json().get("files", []))
        assert n1 == n2, "expansion duplicated on re-run"
