"""Unit tests for the staged pipeline split (change:
progressive-frontend-rendering): recall (search_stage), timeline
(timeline_stage) and graph (graph_stage) with a single traversal."""

import pytest

from src import pgTimeline as tl

pytestmark = pytest.mark.unit


class _FakeSession:
    """Session stub. ``get_bind`` returns a dummy — the geo lookup is
    monkeypatched in these tests, so the engine is never used."""

    def get_bind(self):
        return object()


def _fake_related():
    return {
        "Meeting": [{"sid": 1, "id": 1, "oparlKey": "1",
                     "oparlId": "https://x/m/1", "name": "Rat",
                     "start_date": None, "end_date": None}],
        "AgendaItem": [], "Paper": [], "Consultation": [],
        "Organization": [], "Person": [], "Body": [],
        "Location": [], "AuxFile": [],
        "edges": [{"source": "Meeting_1", "target": "AgendaItem_7",
                   "relation": "agendaItem", "via": "FK"}],
    }


def _stage1(top_files):
    return {"query": "q", "top_files": top_files,
            "matched_entities": [], "facets": {}, "applied_filters": []}


class TestTimelineStage:
    def test_empty_recall_short_circuits(self):
        out = tl.timeline_stage(_FakeSession(), _stage1([]))
        assert out["timeline"] == []
        assert out["related_objects"] is None

    def test_single_traversal_feeds_timeline(self, monkeypatch):
        calls = []

        def fake_find(session, file_sids):
            calls.append(file_sids)
            return _fake_related()

        monkeypatch.setattr(tl, "find_related_objects", fake_find)
        stage1 = _stage1([{"sid": 10, "oparlKey": "k1", "name": "f"}])
        out = tl.timeline_stage(_FakeSession(), stage1)
        assert calls == [{"k1": 10}]  # exactly one traversal
        # edge log is not turned into timeline events
        assert all(e["type"] != "edges" for g in out["timeline"]
                   for e in g["events"])


class TestGraphStage:
    def test_empty_recall_short_circuits(self):
        out = tl.graph_stage(_FakeSession(), _stage1([]),
                             {"timeline": [], "related_objects": None})
        assert out["graph"] == {"nodes": [], "edges": []}
        assert out["geo_available"] is False

    def test_graph_reuses_traversal_without_mutation(self, monkeypatch):
        """Regression for the shared-mutation hazard: the edge log stays
        in the traversal payload (copied, not popped), so a timeline stage
        run before the graph stage still sees the edges and vice versa."""
        related = _fake_related()

        monkeypatch.setattr(tl, "find_related_objects", lambda s, f: related)
        import src.pgGeo as geo_mod
        monkeypatch.setattr(geo_mod, "geo_available_for_keys", lambda *a, **k: True)

        stage1 = _stage1([{"sid": 10, "oparlKey": "k1", "name": "f",
                           "downloadurl": "u", "fileName": "f.pdf"}])
        stage2 = tl.timeline_stage(_FakeSession(), stage1)
        stage3 = tl.graph_stage(_FakeSession(), stage1, stage2)

        # graph was serialized from the same traversal
        assert stage3["graph"]["nodes"], "graph stage produced no nodes"
        assert any(e["relation"] == "agendaItem"
                   for e in stage3["graph"]["edges"])
        # traversal payload was not mutated by the graph stage
        assert related["edges"]
        # ...and a second timeline stage still works (idempotent re-entry)
        stage2b = tl.timeline_stage(_FakeSession(), stage1)
        assert stage2b["timeline"] == stage2["timeline"]


class TestCompositionParity:
    def test_stages_match_monolith_keys(self, monkeypatch):
        """The composed search_and_build_timeline returns the same
        contract as before the split (stage-wise vs monolithic keys)."""
        related = _fake_related()

        monkeypatch.setattr(tl, "find_related_objects", lambda s, f: related)
        import src.pgGeo as geo_mod
        monkeypatch.setattr(geo_mod, "geo_available_for_keys", lambda *a, **k: False)

        top_files = [{"sid": 10, "oparlKey": "k1", "name": "f",
                      "fileName": "f.pdf", "downloadurl": "u",
                      "oparlId": "o", "date": None, "distance": 0.1,
                      "match": None}]
        stage1 = {"query": "q", "top_files": top_files,
                  "matched_entities": [{"id": "e1"}], "facets": {"p": {}},
                  "applied_filters": []}
        monkeypatch.setattr(tl, "search_stage", lambda s, q, **kw: stage1)

        result = tl.search_and_build_timeline(_FakeSession(), "q")

        # composed result carries exactly the monolithic contract keys
        assert set(result.keys()) == {
            "query", "top_files", "timeline", "graph", "geo_available",
            "matched_entities", "facets", "applied_filters", "stats",
        }
        assert result["top_files"] == top_files
        assert result["graph"]["nodes"], "graph stage produced no nodes"
        assert result["geo_available"] is False
        assert result["stats"]["total_files"] == 1
        assert result["stats"]["total_events"] == len(
            [e for g in result["timeline"] for e in g["events"]])
        assert "message" not in result
