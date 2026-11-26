"""Unit tests for kgFollowups answer degradation (change:
followup-grounding-degrade): a malformed LLM JSON payload must not break
the follow-up turn or the sealed-state chain — questions degrade to a
deterministic salvage instead, and the callers still seal the fresh token.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.kg import kgFollowups as kf

pytestmark = pytest.mark.unit


class _FakeRemote:
    # generate_followups probes chat_json: callable (even returning None)
    # → remote is the client (its .chat method is used, no real LLM call)
    chat_json = lambda *a, **k: None  # noqa: E731

    def __init__(self, raw=None, exc=None):
        self.raw = raw
        self.exc = exc

    def chat(self, messages, model=None, **kwargs):
        if self.exc:
            raise self.exc
        return self.raw


class TestFollowupParseDegradation:
    def test_valid_json(self):
        out = kf.generate_followups("A.", statements=None, topics=[],
                                    remote=_FakeRemote('{"questions": ["Q1?", "Q2?"]}'))
        assert out["questions"] == ["Q1?", "Q2?"]

    def test_suendenfall_broken_json_salvages_questions(self):
        # the reported failure mode: unescaped inner quote terminates the
        # string early ("Expecting ',' delimiter") — brace fallback fails
        # too, salvage recovers the question strings
        raw = ('Hier die Fragen:\n{"questions": ["Wann konnte das gelöst " '
               '"werden? "Warum fehlt es?" "Was kostet alles?"], "topics": ["umwelt"]}')
        out = kf.generate_followups("A.", statements=None, topics=[],
                                    remote=_FakeRemote(raw))
        assert out["questions"]
        assert all(q.endswith("?") for q in out["questions"])
        assert len(out["questions"]) <= kf.FOLLOWUP_MAX

    def test_broken_json_without_question_strings_degrades_empty(self):
        out = kf.generate_followups("A.", statements=None, topics=[],
                                    remote=_FakeRemote("garbage, no JSON here"))
        assert out["questions"] == []

    def test_bare_list_payload(self):
        out = kf.generate_followups("A.", statements=None, topics=[],
                                    remote=_FakeRemote('["Q1?", "Q2?"]'))
        assert out["questions"] == ["Q1?", "Q2?"]

    def test_json_region_with_prose(self):
        out = kf.generate_followups("A.", statements=None, topics=[],
                                    remote=_FakeRemote(
                                        'Sure! {"questions": ["Q1?"]} hope it helps'))
        assert out["questions"] == ["Q1?"]


class TestSearchEnrichSealContinuity:
    def test_generation_failure_still_seals_state(self, monkeypatch):
        monkeypatch.setattr(
            "src.kg.kgFollowups.related_by_tags", lambda top, **k: [], raising=False)
        monkeypatch.setattr(
            "src.kg.kgQueries.related_by_tags", lambda top, **k: [])
        monkeypatch.setattr(
            "src.kg.kgFollowups.generate_followups",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM down")))

        from src.search.apiServer import _kg_enrich
        result = {"top_files": [{"oparlKey": "f1"}],
                  "summary": "Zusammenfassung über Wohnen."}
        _kg_enrich(result, "Wohnbau in Karlsruhe", "sid-fixture-1")
        assert result.get("state")  # token chain survives the LLM outage
        assert result.get("followups") is None  # questions dropped, no raise


class TestFollowupEndpointSealContinuity:
    def test_generation_failure_keeps_fresh_token(self, monkeypatch):
        from fastapi.testclient import TestClient
        from src.search import apiServer

        state = {"q0": "wohnen", "top_docs": ["f1"], "topics": ["umwelt"]}
        sealed_old = kf.seal_state(state, "sid-fix-2")

        monkeypatch.setattr(apiServer, "get_db_session", lambda: _DummySession())
        monkeypatch.setattr(apiServer, "search_stage",
                            lambda session, q, top_k=10: {"top_files": [{"oparlKey": "f2"}]})
        monkeypatch.setattr(apiServer, "_run_summarizer", lambda s, r: None)
        monkeypatch.setattr("src.kg.kgFollowups.open_state", lambda t, s: dict(state))
        monkeypatch.setattr("src.kg.kgQueries.file_sid_for_key", lambda ks: {"f1": 11})
        monkeypatch.setattr("src.kg.kgQueries.statements_for_papers", lambda sids: {})

        def _boom(*a, **k):
            raise RuntimeError("malformed LLM JSON")

        monkeypatch.setattr("src.kg.kgFollowups.generate_followups", _boom)

        def _seal(payload, sid):
            return kf.seal_state(payload, sid)

        monkeypatch.setattr("src.kg.kgFollowups.seal_state_or_none", _seal)

        with TestClient(apiServer.app) as client:
            r = client.post("/followup", json={
                "question": "mehr dazu", "state": sealed_old, "session_id": "sid-fix-2"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("state") and body["state"] != sealed_old
        assert body.get("state_refreshed") is True
        assert body.get("followups") == []  # questions lost, chain intact


class _DummySession:
    def close(self):
        pass


class TestFreshRequestNoFollowups:
    """change: fix-followup-deixis principle — follow-up questions exist
    only for follow-up turns; a fresh request seals its state but carries
    no followup chips."""

    def test_enrich_without_followup_flag(self, monkeypatch):
        called = []
        monkeypatch.setattr("src.kg.kgFollowups.generate_followups",
                            lambda *a, **k: called.append(1) or {"questions": ["q?"]})
        from src.search.apiServer import _kg_enrich
        result = {"top_files": [{"oparlKey": "f1"}],
                  "summary": "Zusammenfassung über Wohnen."}
        _kg_enrich(result, "Wohnbau in Karlsruhe", "sid-fresh-1", followup=False)
        assert not called            # generation never runs for a fresh turn
        assert "followups" not in result
        assert result.get("state")   # state still sealed (thread hydration)

    def test_enrich_with_followup_flag(self, monkeypatch):
        monkeypatch.setattr("src.kg.kgFollowups.generate_followups",
                            lambda *a, **k: {"questions": ["Wie teuer war das?"]})
        from src.search.apiServer import _kg_enrich
        result = {"top_files": [{"oparlKey": "f1"}],
                  "summary": "Zusammenfassung über Wohnen."}
        _kg_enrich(result, "und wie teuer war das", "sid-fu-1", followup=True)
        assert result.get("followups") == ["Wie teuer war das?"]
        assert result.get("state")

    def _search_client(self, monkeypatch, concatenated):
        from fastapi.testclient import TestClient
        from src.search import apiServer
        import src.kg.kgFollowups as kf

        monkeypatch.setattr(apiServer, "get_db_session", lambda: _DummySession())
        monkeypatch.setattr(apiServer, "search_stage",
                            lambda session, q, top_k=10, **k: {
                                "top_files": [{"oparlKey": "f1"}],
                                "matched_entities": [{"score": 0.5}],
                                "summary": "Zusammenfassung über Wohnen."})
        monkeypatch.setattr(apiServer, "_run_summarizer", lambda s, r: None)
        monkeypatch.setattr("src.kg.kgQueries.topic_focus_for_query", lambda q: None)
        monkeypatch.setattr(
            apiServer, "_thread_turn",
            lambda session, q, t, model_followup=None: {
                "thread": kf.new_thread(origin="search"),
                "session_id": "sid-search-test",
                "effective_query": q,
                "forced_break": False,
                "concatenated": concatenated,
                "classification": {"action": "followup" if concatenated else "new topic"},
            })
        monkeypatch.setattr("src.kg.kgFollowups.generate_followups",
                            lambda *a, **k: {"questions": ["Wie teuer war das?"]})
        return TestClient(apiServer.app)

    def test_search_fresh_no_followup_questions(self, monkeypatch):
        monkeypatch.setattr(apiServer_module().app.state, "kg_app_integration", True, raising=False)
        client = self._search_client(monkeypatch, concatenated=False)
        r = client.post("/search", json={"query": "sanierung staatstheater"})
        assert r.status_code == 200
        assert "followups" not in r.json()

    def test_search_followup_turn_has_questions(self, monkeypatch):
        monkeypatch.setattr(apiServer_module().app.state, "kg_app_integration", True, raising=False)
        client = self._search_client(monkeypatch, concatenated=True)
        r = client.post("/search", json={"query": "und wie teuer war das"})
        assert r.status_code == 200
        assert r.json().get("followups") == ["Wie teuer war das?"]


def apiServer_module():
    from src.search import apiServer
    return apiServer


class TestFollowupKeepsSearchType:
    """change: followup-keeps-search-type — a follow-up can never change
    the search type: the routed intent is pinned to the thread's origin
    (default topic search), even when the follow-up text decodes to
    another intent (live: "sanierung staatstheater" → "wer hat das
    beschlossen" flipped the flow to the gremien intent)."""

    def _sealed_prior(self, sid, intent="search_topic"):
        return kf.seal_state({"q0": "sanierung staatstheater", "intent": intent,
                              "top_docs": ["f1"],
                              "thread": {"thread_id": "t", "turns": ["sanierung staatstheater"],
                                         "turn_count": 1, "origin": "search"}}, sid)

    def test_followup_turn_pins_origin_intent(self, monkeypatch):
        from fastapi.testclient import TestClient
        from src.search import apiServer
        from src.pgIntentRouter import _FORCE

        captured = {}

        def _fake_route_ask(session, query, **k):
            captured["ctx"] = dict(_FORCE.get("ctx") or {})
            # not forced → the decode may pick any search type (gremium)
            intent = (captured["ctx"].get("forced_intent")
                      or "ask_gremium_recent")
            return {"intent": intent, "top_files": [{"oparlKey": "f1"}],
                    "matched_entities": [{"score": 0.5}]}

        monkeypatch.setattr(apiServer_module().app.state, "kg_app_integration", True, raising=False)
        monkeypatch.setattr(apiServer, "get_db_session", lambda: _DummySession())
        monkeypatch.setattr(apiServer, "_run_summarizer", lambda s, r: None)
        monkeypatch.setattr("src.pgIntentRouter.ask", _fake_route_ask)

        class _FakeRouter:
            def __init__(self, *a, **k):
                pass
            def decode(self, q, prev_query=None):
                # the follow-up text alone decodes to the gremium intent
                return {"intent": "ask_gremium_recent", "slots": {}, "scores": {}}

        monkeypatch.setattr("src.pgIntentRouter.IntentRouter", _FakeRouter)
        monkeypatch.setattr(
            apiServer, "_thread_turn",
            lambda session, q, t, model_followup=None: {
                "thread": kf.new_thread(origin="search"),
                "session_id": "sid-pin-1", "effective_query":
                    "sanierung staatstheater · wer hat das beschlossen",
                "forced_break": False, "concatenated": True,
                "classification": {"action": "followup"},
            })
        monkeypatch.setattr("src.kg.kgFollowups.generate_followups",
                            lambda *a, **k: {"questions": ["Wann war das?"]})

        prior = self._sealed_prior("sid-pin-1")
        with TestClient(apiServer.app) as client:
            r = client.post("/ask", json={
                "query": "wer hat das beschlossen",
                "thread": {"state": prior, "session_id": "sid-pin-1"}})
        assert r.status_code == 200
        # the search type stayed topic search despite the gremium decode
        assert captured["ctx"]["forced_intent"] == "search_topic"
        body = r.json()
        assert body.get("intent") == "search_topic"
        # the origin intent is re-sealed for the next turn
        assert kf.open_state(body["state"], "sid-pin-1").get("intent") == "search_topic"

    def test_fresh_request_keeps_decoded_intent(self, monkeypatch):
        """Only FOLLOWUP turns pin the intent — a fresh request may change
        the search type via its own decode."""
        from fastapi.testclient import TestClient
        from src.search import apiServer
        from src.pgIntentRouter import _FORCE

        captured = {}

        def _fake_route_ask(session, query, **k):
            captured["ctx"] = dict(_FORCE.get("ctx") or {})
            # not forced → the decode may pick any search type (gremium)
            intent = (captured["ctx"].get("forced_intent")
                      or "ask_gremium_recent")
            return {"intent": intent, "top_files": [{"oparlKey": "f1"}],
                    "matched_entities": [{"score": 0.5}]}

        monkeypatch.setattr(apiServer_module().app.state, "kg_app_integration", True, raising=False)
        monkeypatch.setattr(apiServer, "get_db_session", lambda: _DummySession())
        monkeypatch.setattr(apiServer, "_run_summarizer", lambda s, r: None)
        monkeypatch.setattr("src.pgIntentRouter.ask", _fake_route_ask)

        class _FakeRouter:
            def __init__(self, *a, **k):
                pass
            def decode(self, q, prev_query=None):
                return {"intent": "ask_gremium_recent", "slots": {}, "scores": {}}

        monkeypatch.setattr("src.pgIntentRouter.IntentRouter", _FakeRouter)
        monkeypatch.setattr(
            apiServer, "_thread_turn",
            lambda session, q, t, model_followup=None: {
                "thread": kf.new_thread(origin="search"),
                "session_id": "sid-pin-2", "effective_query": q,
                "forced_break": False, "concatenated": False,
                "classification": {"action": "new topic"},
            })

        with TestClient(apiServer.app) as client:
            r = client.post("/ask", json={"query": "wer hat das beschlossen"})
        assert r.status_code == 200
        # fresh request: NOT pinned — route_ask may decode any search type
        assert "forced_intent" not in captured["ctx"]
        assert r.json().get("intent") == "ask_gremium_recent"
