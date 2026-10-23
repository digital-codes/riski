"""Unit tests for src.pgTimeline – pure logic with mocked model calls."""

import importlib.util
import pathlib
import sys
from datetime import datetime

import pytest

from src import pgTimeline as tl


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestFilterByThreshold:
    def test_filters_above_threshold(self):
        data = [("a", 0.1), ("b", 0.5), ("c", 0.39)]
        assert tl.filter_by_threshold(data, threshold=0.4) == [("a", 0.1), ("c", 0.39)]

    def test_keeps_boundary(self):
        assert tl.filter_by_threshold([("a", 0.4)], threshold=0.4) == [("a", 0.4)]


class TestBuildTimeline:
    def test_meeting_uses_start_date(self):
        events = tl.build_timeline({
            "Meeting": [{
                "id": 1, "oparlKey": "1", "oparlId": "https://x/m/1",
                "name": "Rat", "start_date": datetime(2024, 5, 1), "end_date": None,
                "sid": 10,
            }]
        })
        assert len(events) == 1
        assert events[0]["type"] == "Meeting"
        assert events[0]["date"] == datetime(2024, 5, 1)
        assert events[0]["name"] == "Rat"
        assert "start_date" not in events[0]["details"]

    def test_paper_uses_date(self):
        events = tl.build_timeline({
            "Paper": [{
                "id": 2, "oparlKey": "2", "oparlId": "https://x/p/2",
                "name": "Vorlage", "date": datetime(2024, 6, 10),
            }]
        })
        assert events[0]["date"] == datetime(2024, 6, 10)

    def test_consultation_skipped(self):
        events = tl.build_timeline({"Consultation": [{"id": 3, "oparlKey": "3"}]})
        assert events == []

    def test_missing_date_skipped(self):
        events = tl.build_timeline({"Meeting": [{"id": 4, "oparlKey": "4", "name": "x"}]})
        assert events == []

    def test_sorted_by_date(self):
        events = tl.build_timeline({
            "Paper": [
                {"id": 1, "date": datetime(2024, 3, 1), "name": "b"},
                {"id": 2, "date": datetime(2024, 1, 1), "name": "a"},
            ]
        })
        assert [e["name"] for e in events] == ["a", "b"]


class TestGroupTimelineEvents:
    def test_empty(self):
        assert tl.group_timeline_events([]) == []

    def test_single_group_within_window(self):
        events = [
            {"date": datetime(2024, 1, 1), "type": "Meeting", "name": "a"},
            {"date": datetime(2024, 1, 20), "type": "Paper", "name": "b"},
            {"date": datetime(2024, 1, 30), "type": "Meeting", "name": "c"},
        ]
        groups = tl.group_timeline_events(events, window_days=30)
        assert len(groups) == 1
        assert len(groups[0]["events"]) == 3
        assert groups[0]["start_date"] == datetime(2024, 1, 1)
        assert groups[0]["end_date"] == datetime(2024, 1, 30)

    def test_split_beyond_window(self):
        events = [
            {"date": datetime(2024, 1, 1), "type": "Meeting", "name": "a"},
            {"date": datetime(2024, 3, 1), "type": "Paper", "name": "b"},
        ]
        groups = tl.group_timeline_events(events, window_days=30)
        assert len(groups) == 2

    def test_default_window_is_30_days(self):
        assert tl.TIMELINE_WINDOW_DAYS == 30


class TestRerankingFallback:
    def test_no_reranker_configured_returns_default_scores(self, monkeypatch):
        monkeypatch.setattr(tl, "RERANKING_API_URL", None)
        assert tl.call_reranking_model("q", ["a", "b"]) == [1.0, 1.0]
        assert tl.call_reranking_chat_model("q", "c") == 1.0

    def test_rerank_endpoint_scores_reordered(self, monkeypatch):
        monkeypatch.setattr(tl, "RERANKING_API_URL", "http://rerank.example/v1/rerank")
        monkeypatch.setattr(tl, "RERANKING_MODEL", "test-model")
        monkeypatch.setattr(tl, "RERANKING_API_KEY", None)

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "results": [
                        {"index": 1, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.2},
                    ]
                }

        monkeypatch.setattr(tl.requests, "post", lambda url, json=None, headers=None: Resp())
        scores = tl.call_reranking_model("q", ["doc0", "doc1"])
        assert scores == [0.2, 0.9]

    def test_rerank_429_retry(self, monkeypatch):
        monkeypatch.setattr(tl, "RERANKING_API_URL", "http://rerank.example/v1/rerank")
        monkeypatch.setattr(tl, "RERANKING_MODEL", "test-model")
        monkeypatch.setattr(tl, "RERANKING_API_KEY", None)
        sleeps = []
        monkeypatch.setattr(tl.time, "sleep", lambda s: sleeps.append(s))
        calls = {"n": 0}

        class Resp:
            def __init__(self, status):
                self.status_code = status
                self.headers = {"Retry-After": "0"}

            def raise_for_status(self):
                assert self.status_code == 200

            def json(self):
                return {"results": [{"index": 0, "relevance_score": 0.5}]}

        def fake_post(url, json=None, headers=None):
            calls["n"] += 1
            return Resp(429 if calls["n"] == 1 else 200)

        monkeypatch.setattr(tl.requests, "post", fake_post)
        assert tl.call_reranking_model("q", ["d"]) == [0.5]
        assert calls["n"] == 2


class TestEmbeddingRoute:
    def test_call_embedding_model_uses_shared_client(self, monkeypatch):
        import numpy as np

        captured = {}

        def fake_embed(text, model=None):
            captured["text"] = text
            captured["model"] = model
            v = np.zeros(4)
            v[0] = 2.0
            return v / np.linalg.norm(v)

        monkeypatch.setattr(tl.remote, "embed", fake_embed)
        vec = tl.call_embedding_model("hello")
        assert captured["text"] == "hello"
        assert len(vec) == 4
        assert abs(sum(x * x for x in vec) - 1.0) < 1e-9


class TestGetDbSession:
    def test_default_session_uses_shared_readonly_engine(self):
        from src import db

        session = tl.get_db_session()
        assert session.get_bind() is db.get_engine(readonly=True)
        session.close()


# ---------------------------------------------------------------------------
# Parity with the legacy implementation on identical fixture data
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def legacy_tl():
    path = pathlib.Path(__file__).resolve().parents[2] / "src" / "pgTimeline.py"
    if not path.exists():
        pytest.skip("legacy src/pgTimeline.py not present")
    src_dir = str(path.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location("legacy_pgTimeline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParityWithLegacy:
    def test_build_timeline_same_output(self, legacy_tl):
        related = {
            "Meeting": [{
                "id": 1, "oparlKey": "1", "oparlId": "https://x/m/1",
                "name": "Rat", "start_date": datetime(2024, 5, 1), "end_date": None,
            }],
            "Paper": [{
                "id": 2, "oparlKey": "2", "oparlId": "https://x/p/2",
                "name": "Vorlage", "date": datetime(2024, 4, 15),
            }],
            "Consultation": [{"id": 3, "oparlKey": "3"}],
            "AgendaItem": [],
            "Organization": [],
            "Person": [],
            "Body": [],
            "Location": [],
            "AuxFile": [],
        }
        ours = tl.build_timeline(related)
        theirs = legacy_tl.build_timeline(related)
        assert ours == theirs

    def test_grouping_same_output(self, legacy_tl):
        events = [
            {"date": datetime(2024, 1, 1), "type": "Meeting", "name": "a"},
            {"date": datetime(2024, 1, 10), "type": "Meeting", "name": "b"},
            {"date": datetime(2024, 1, 25), "type": "Meeting", "name": "c"},
            {"date": datetime(2024, 2, 10), "type": "Meeting", "name": "d"},
        ]
        ours = tl.group_timeline_events(events, window_days=30)
        theirs = legacy_tl.group_timeline_events(events, window_days=30)
        assert ours == theirs

    def test_result_structure_same_keys(self, legacy_tl):
        """The no-results early return matches the legacy structure exactly."""
        class FakeSession:
            def get_bind(self):
                raise RuntimeError("should not touch db")

        import src.pgTimeline as mod

        monkey = pytest.MonkeyPatch()
        monkey.setattr(mod, "call_embedding_model", lambda *a, **k: [0.0])
        monkey.setattr(mod, "query_vector_similarity", lambda s, q, k: [])
        monkey.setattr(legacy_tl, "call_embedding_model", lambda *a, **k: [0.0])
        monkey.setattr(legacy_tl, "query_vector_similarity", lambda s, q, k: [])
        try:
            res = mod.search_and_build_timeline(FakeSession(), "test query")
            legacy_res = legacy_tl.search_and_build_timeline(FakeSession(), "test query")
        finally:
            monkey.undo()
        assert set(res.keys()) == set(legacy_res.keys())
        assert res["results"] == [] and res["timeline"] == []

pytestmark = pytest.mark.unit
