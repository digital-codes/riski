"""Unit tests for location intent wiring (src.pgIntentRouter +
src.pgLocationSearch, change: add-location-intent). DB-touching paths live
in test_integration_location.py."""

from __future__ import annotations

import pytest

import src.pgIntentRouter as ir
from src.pgIntentRouter import (
    IntentRouter,
    load_intents_config,
    resolve_location,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def cfg():
    return load_intents_config()


class _FakeSession:
    class _None:
        bind = None


class TestLocationSpec:
    def test_trigram_spec_extracted(self, cfg):
        intent = ir.find_intent(cfg, "ask_location")
        spec = ir._location_slot_spec(intent)
        assert spec.get("tables") == ["Street", "District"]
        assert spec.get("column") == "name"
        assert "threshold" in spec

    def test_no_spec_without_location_slot(self, cfg):
        assert ir._location_slot_spec(ir.find_intent(cfg, "search_topic")) == {}


class TestSuffixDetection:
    def test_suffix_hit(self):
        assert ir._query_has_suffix("was passiert am friedrichsplatz",
                                    ir.DEFAULT_LOCATION_SUFFIXES)
        assert ir._query_has_suffix("kaiserstrasse", ["strasse"])

    def test_suffix_is_word_scoped(self):
        # 'hof' must not fire inside 'bahnhofstrasse' for the *prefix* rule,
        # but 'strasse' as suffix word part does
        assert ir._query_has_suffix("bahnhofstrasse", ["strasse"])
        assert not ir._query_has_suffix("hofensterne", ["hof"])

    def test_no_suffix(self):
        assert not ir._query_has_suffix("durlach",
                                        ir.DEFAULT_LOCATION_SUFFIXES)


class TestResolveLocationWiring:
    def test_resolve_attaches_location(self, cfg, monkeypatch):
        loc = {"locations": [{"type": "street", "id": 542,
                              "name": "Friedrichsplatz", "score": 0.7}],
               "alternates": [], "note": "", "threshold": 0.4}
        monkeypatch.setattr(ir, "resolve_location", lambda s, q, i: loc)
        router = IntentRouter(cfg=cfg)
        out = router.resolve("ask_location", {}, _FakeSession(), query="x")
        assert out["handler"] == "location_scoped_search"
        assert out["location"] == loc
        assert out["notes"] == []

    def test_unresolved_location_appends_note(self, cfg, monkeypatch):
        loc = {"locations": [], "alternates": [], "note": "kein Ort",
               "threshold": 0.5}
        monkeypatch.setattr(ir, "resolve_location", lambda s, q, i: loc)
        router = IntentRouter(cfg=cfg)
        out = router.resolve("ask_location", {}, _FakeSession(), query="x")
        assert out["location"] == loc
        assert "kein ort" in out["notes"][0].lower()

    def test_other_intents_have_no_location(self, cfg):
        out = IntentRouter(cfg=cfg).resolve("search_topic", {},
                                            _FakeSession())
        assert out["location"] is None


class TestLocationRunSearch:
    def _resolved(self, cfg, locations):
        return {
            "intent": "ask_location",
            "handler": "location_scoped_search",
            "answer_mode": "summary",
            "filters": [],
            "gremium": None,
            "location": {"locations": locations, "alternates": [],
                         "note": "", "threshold": 0.4},
            "notes": [],
        }

    def test_location_handler_bypasses_search_fn(self, cfg, monkeypatch):
        import src.pgLocationSearch as locmod
        import src.pgTimeline as tl

        def boom(*a, **kw):
            raise AssertionError("search_fn called despite resolved location")

        monkeypatch.setattr(tl, "search_and_summarize", boom)
        calls = {}

        def fake_stage(session, query, locations, top_k=10, summarize=True):
            calls["locations"] = locations
            return {"query": query, "top_files": [{"oparlKey": "f1"}],
                    "matched_entities": [], "facets": {},
                    "applied_filters": []}

        monkeypatch.setattr(locmod, "location_search_stage", fake_stage)
        router = IntentRouter(cfg=cfg)
        out = router.run_search(
            _FakeSession(), "friedrichsplatz",
            self._resolved(cfg, [{"type": "street", "id": 542}]),
            summarize=False)
        assert calls["locations"] == [{"type": "street", "id": 542}]
        assert out["top_files"] == [{"oparlKey": "f1"}]
        assert "graph" not in out and "timeline" not in out
        assert out["intent"] == "ask_location"
        assert out["location"]["locations"]

    def test_empty_scope_retries_unscoped(self, cfg, monkeypatch):
        import src.pgLocationSearch as locmod

        def fake_stage(session, query, locations, top_k=10, summarize=True):
            return {"query": query, "top_files": [], "matched_entities": [],
                    "facets": {}, "applied_filters": []}

        monkeypatch.setattr(locmod, "location_search_stage", fake_stage)
        calls = []

        def fake_search(session, query, top_k=10, filters=None, signals=None,
                        summarize=True):
            calls.append(filters)
            return {"query": query, "top_files": [{"oparlKey": "f2"}],
                    "matched_entities": [], "applied_filters": filters}

        import src.pgTimeline as tl

        monkeypatch.setattr(tl, "search_and_summarize", fake_search)
        router = IntentRouter(cfg=cfg)
        out = router.run_search(
            _FakeSession(), "friedrichsplatz",
            self._resolved(cfg, [{"type": "street", "id": 542}]),
            summarize=False)
        assert calls == [None]  # unscoped retry
        assert out["top_files"] == [{"oparlKey": "f2"}]
        assert any("ortsscope" in n.lower() for n in out["fallback_notes"])

    def test_unresolved_location_falls_through_to_search(self, cfg, monkeypatch):
        import src.pgLocationSearch as locmod

        def boom(*a, **kw):
            raise AssertionError("location stage called without locations")

        monkeypatch.setattr(locmod, "location_search_stage", boom)
        calls = []

        def fake_search(session, query, top_k=10, filters=None, signals=None,
                        summarize=True):
            calls.append(filters)
            return {"query": query, "top_files": [{"oparlKey": "f3"}],
                    "matched_entities": [], "applied_filters": filters}

        import src.pgTimeline as tl

        monkeypatch.setattr(tl, "search_and_summarize", fake_search)
        router = IntentRouter(cfg=cfg)
        resolved = self._resolved(cfg, [])
        resolved["notes"] = ["kein Ort in der Anfrage erkannt"]
        out = router.run_search(_FakeSession(), "irgendwas", resolved,
                                summarize=False)
        assert calls == [None]
        assert out["top_files"] == [{"oparlKey": "f3"}]
        assert out["location"]["locations"] == []
