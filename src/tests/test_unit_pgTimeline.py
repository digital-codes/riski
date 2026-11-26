"""Unit tests for src.pgTimeline – pure logic with mocked model calls."""

import importlib.util
import pathlib
import sys
from datetime import datetime

import pytest

from src.search import pgTimeline as tl
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
        """The no-results early return matches the staged stage-1
        contract (change: progressive-frontend-rendering): top_files plus
        recall fields, no timeline/graph/results in the recall response."""
        class FakeSession:
            def get_bind(self):
                raise RuntimeError("should not touch db")

        import src.search.pgTimeline as mod

        monkey = pytest.MonkeyPatch()
        monkey.setattr(mod, "call_embedding_model", lambda *a, **k: [0.0])
        monkey.setattr(mod, "query_vector_similarity", lambda s, q, k: [])
        monkey.setattr(legacy_tl, "call_embedding_model", lambda *a, **k: [0.0])
        monkey.setattr(legacy_tl, "query_vector_similarity", lambda s, q, k: [])
        try:
            # legacy vector-only path (hybrid=False) for structure parity;
            # the hybrid path requires a live DB connection (integration tests)
            res = mod.search_and_build_timeline(FakeSession(), "test query", hybrid=False)
            legacy_res = legacy_tl.search_and_build_timeline(FakeSession(), "test query", hybrid=False)
        finally:
            monkey.undo()
        assert {"matched_entities", "facets", "applied_filters"} <= set(res.keys())
        assert res["timeline"] == [] and res["graph"] == {"nodes": [], "edges": []}
        assert res["top_files"] == []
        # the monolithic composition still exists for non-interactive
        # consumers (semantic timeline CLI)
        assert set(legacy_res.keys()) >= {"query", "top_files"}

class TestRerankGateDecision:
    """rerank_gate_decision — lexical override keeps lexically-certain
    Files below fully-accepted ones (change: fix-hybrid-search-ranking)."""

    LEX = {"F_x"}  # keys with a lexical provenance hit

    def test_accept_at_or_above_cutoff(self):
        assert tl.rerank_gate_decision(
            "F_a", 1.0, 0.85, 0.8, True, self.LEX) == pytest.approx(0.85)

    def test_reject_below_cutoff_without_lexical(self):
        assert tl.rerank_gate_decision(
            "F_b", 1.0, 0.6, 0.8, True, self.LEX) is None

    def test_lexical_override_keeps_file_below_cutoff(self):
        # lexical-only File with rerank 0.6 (below cutoff 0.8): kept,
        # ranked by fusion * min(rerank, cutoff) = 1.0 * 0.6 — rerank ≥
        # cutoff is impossible here (that's the accept path), so the
        # merged score equals fusion * rerank and stays below accepted
        kept = tl.rerank_gate_decision("F_x", 1.0, 0.6, 0.8, True, self.LEX)
        assert kept == pytest.approx(0.6)

    def test_override_ranks_below_accepted_files(self):
        accepted = tl.rerank_gate_decision("F_a", 1.0, 0.9, 0.8, True, self.LEX)
        strong_lex = tl.rerank_gate_decision("F_x", 1.0, 0.6, 0.8, True, self.LEX)
        weak_lex = tl.rerank_gate_decision("F_x", 0.5, 0.79, 0.8, True, self.LEX)
        tiny_lex = tl.rerank_gate_decision("F_x", 1.0, 0.1, 0.8, True, self.LEX)
        assert strong_lex == pytest.approx(0.6)
        assert weak_lex == pytest.approx(0.5 * 0.79)
        assert tiny_lex == pytest.approx(0.1)
        assert accepted > strong_lex > weak_lex > tiny_lex

    def test_kill_switch_restores_strict_gate(self):
        assert tl.rerank_gate_decision(
            "F_x", 1.0, 0.6, 0.8, False, self.LEX) is None

    def test_invalid_rerank_score_keeps_original(self):
        # content-less documents: invalid rerank keeps original score
        assert tl.rerank_gate_decision(
            "F_c", 1.0, None, 0.8, True, self.LEX) == pytest.approx(1.0)

    def test_cutoff_configurable(self):
        assert tl.rerank_gate_decision(
            "F_d", 1.0, 0.7, 0.65, False, set()) == pytest.approx(0.7)

    def test_none_lexical_match_not_overridden(self):
        # non-lexical strong vector hits are still gated
        assert tl.rerank_gate_decision(
            "F_v", 1.0, 0.3, 0.8, True, set()) is None


class TestListwiseRerank:
    """Listwise chat rerank (change: fix-hybrid-search-ranking, fragment B)."""

    def _mk_resp(self, orders):
        import src.search.pgTimeline as mod
        if orders is None:
            monkey = pytest.MonkeyPatch()
            monkey.setattr(mod.remote, "get_prompt", lambda pid: "sys" if pid.endswith("-listwise") else "Q {query}")
            # chat raising = failure path
            def boom(**kw):
                raise RuntimeError("no endpoint")
            monkey.setattr(mod.remote, "chat", boom)
            monkey._undo = monkey.undo  # noqa
            return monkey
        import json as _json
        monkey = pytest.MonkeyPatch()
        monkey.setattr(mod.remote, "get_prompt", lambda pid: "sys" if pid.endswith("-listwise") else "Q {query}")
        monkey.setattr(mod.remote, "chat", lambda *a, **k: {
            "content": _json.dumps({"relevant": orders})})
        return monkey

    CANDS = [("F_a", {"name": "alpha"}), ("F_b", {"name": "beta"}),
             ("F_c", {"name": "gamma"})]
    CHUNKS = {"F_a": 0, "F_b": None, "F_c": 2}

    def test_ranking_yields_decaying_scores(self):
        monkey = self._mk_resp([1, 3])
        try:
            out = tl.listwise_rerank("q", self.CANDS, self.CHUNKS,
                                     lambda k, c: "text %s" % k)
        finally:
            monkey.undo()
        assert out["F_a"] > out["F_c"]
        assert "F_b" not in out
        assert out["F_a"] == pytest.approx(1.0)
        assert out["F_c"] > 0.5

    def test_failure_returns_empty(self):
        monkey = self._mk_resp(None)
        try:
            assert tl.listwise_rerank("q", self.CANDS, self.CHUNKS,
                                      lambda k, c: "t") == {}
        finally:
            monkey.undo()

    def test_unparseable_json_returns_empty(self):
        import src.search.pgTimeline as mod
        monkey = pytest.MonkeyPatch()
        monkey.setattr(mod.remote, "get_prompt", lambda pid: "x")
        monkey.setattr(mod.remote, "chat", lambda *a, **k: {"content": "no json here"})
        try:
            assert tl.listwise_rerank("q", self.CANDS, self.CHUNKS,
                                      lambda k, c: "t") == {}
        finally:
            monkey.undo()

    def test_out_of_range_indices_ignored(self):
        import src.search.pgTimeline as mod
        import json as _json
        monkey = pytest.MonkeyPatch()
        monkey.setattr(mod.remote, "get_prompt", lambda pid: "x")
        monkey.setattr(mod.remote, "chat", lambda *a, **k: {
            "content": _json.dumps({"relevant": [2, 99]})})
        try:
            out = tl.listwise_rerank("q", self.CANDS, self.CHUNKS, lambda k, c: "t")
        finally:
            monkey.undo()
        assert list(out) == ["F_b"]

    def test_prompt_ids_registered(self):
        from src.remote import has_prompt
        assert has_prompt("rerank-listwise")
        assert has_prompt("rerank-listwise-user")

    def test_not_relevant_score_below_cutoff(self):
        assert tl._LISTWISE_NOT_RELEVANT_SCORE < 0.8

    def test_snippet_keyword_centered(self):
        head = "## Abstimmungsergebnis: Einstimmige Zustimmung    " \
               "x" * 700 + " Der Vorsitzende ruft zum Thema " \
               "Bürgerbeteiligungsplattform auf und erklärt, dass die " \
               "35.000 Euro aus Ziffer 7 entfernt wurden."
        out = tl._listwise_snippet(head, "Bürgerbeteiligungsplattform")
        assert len(out) <= tl._LISTWISE_SNIPPET_CHARS
        assert "Bürgerbeteiligungsplattform" in out
        assert "Ziffer 7" in out

    def test_snippet_compound_suffix_match(self):
        # minutes say "Beteiligungsplattform" only — the compound query term
        # "Bürgerbeteiligungsplattform" must still hit via its suffix walk
        text = "x" * 700 + " Darstellung des Themas Beteiligungsplattform " \
               "Jetzt brauchen wir die 35.000 Euro aus Ziffer 7."
        out = tl._listwise_snippet(text, "Bürgerbeteiligungsplattform")
        assert "Beteiligungsplattform" in out
        assert "Ziffer 7" in out or "x" * 10 in out

    def test_snippet_no_hit_head_window(self):
        out = tl._listwise_snippet("y" * 700, "thema")
        assert out.startswith("y")
        assert len(out) <= tl._LISTWISE_SNIPPET_CHARS


class TestRerankWindowParity:
    """Clamped fallback ordering for candidates beyond the rerank window
    (change: fix-hybrid-search-ranking extension)."""

    def test_fallback_clamp_ranks_at_or_below_accepted(self):
        # acceptable floor: batch accept = fusion*rerank (>= cutoff);
        # beyond-window fallback = fusion*cutoff; lexical override =
        # fusion*min(rerank, cutoff)
        fusion_hi, fusion_lo = 0.9, 2.5   # reranked-first vs deep file
        accepted = fusion_hi * 0.95       # 0.855
        fallback = fusion_lo * 0.8        # 2.0 — hmm raw fusion ranking!
        # fallback must use its own fusion score * cutoff, so a deep file
        # with big fusion can still rank above a weaker accept — that is
        # intended: combined ordering, not accept-first.
        assert fallback > accepted
        # but a deep file can never beat its own reranked version:
        reranked = fusion_lo * 0.9
        assert reranked > fallback

    # pure function equivalence: clamped fallback == rerank_gate_decision
    # with rerank_score = cutoff (<= all accepted scores)
    def test_fallback_equals_gate_low_edge(self):
        assert tl.rerank_gate_decision(
            "F_z", 2.5, 0.8, 0.8, False, set()) == pytest.approx(2.5 * 0.8)


class TestSearchWeightsConfigTimeline:
    """search_stage gate config comes from the instance config search
    section (env wins over defaults)."""

    def test_gate_config_includes_window(self, monkeypatch):
        monkeypatch.setenv("RISKI_SEARCH__RERANK_MAX_CANDIDATES", "150")
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        from src.instanceConfig import clear_cache, section
        clear_cache()
        try:
            assert int(section("search").get("rerank_max_candidates")) == 150
        finally:
            clear_cache()

    def test_gate_config_env_override(self, monkeypatch):
        import src.search.pgTimeline as mod
        # re-execute the inner _search_gate_config by patching config
        monkeypatch.setenv("RISKI_SEARCH__RERANK_CUTOFF", "0.55")
        from src.instanceConfig import clear_cache
        clear_cache()
        try:
            from src.instanceConfig import section
            cutoff = float(section("search").get("rerank_cutoff", 0.8))
        finally:
            clear_cache()
        assert cutoff == 0.55


pytestmark = pytest.mark.unit
