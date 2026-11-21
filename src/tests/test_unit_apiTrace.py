"""Unit tests for src.apiTrace (change: api-debug-logging).

All tests run with the CWD moved to a temp directory to prove the log
file is anchored at the project root, and clean the project log file
entries they produce (the file itself is gitignored).
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src import apiTrace  # noqa: E402

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(apiTrace.__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_trace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # trace must still write to the project log
    apiTrace._reset()
    monkeypatch.delenv("RISKI_API_TRACE", raising=False)
    log = apiTrace.log_file_path()
    existed = log.exists()
    if existed:
        log.unlink()  # tests re-create it; entries never accumulate
    yield
    apiTrace._reset()
    if log.exists():
        log.unlink()
    if existed and not log.exists():
        log.touch()


def _entries():
    with open(apiTrace.log_file_path(), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestDisabledByDefault:
    def test_no_env_no_file(self, monkeypatch):
        monkeypatch.delenv("RISKI_API_TRACE", raising=False)
        assert apiTrace.trace_enabled() is False
        apiTrace.trace("http_request", query="wohnen in karlsruhe")
        assert not apiTrace.log_file_path().exists()

    def test_falsy_value_no_file(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "0")
        assert apiTrace.trace_enabled() is False
        apiTrace.trace("http_request", query="wohnen")
        assert not apiTrace.log_file_path().exists()

    def test_truthy_variants(self, monkeypatch):
        for v in ("1", "true", "YES", "On"):
            monkeypatch.setenv("RISKI_API_TRACE", v)
            assert apiTrace.trace_enabled() is True, v


class TestEnabled:
    def test_single_json_line_with_core_keys(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        assert apiTrace.trace_enabled() is True
        apiTrace.trace("http_request", req="abc123def456",
                       method="POST", path="/ask")
        entries = _entries()
        assert len(entries) == 1
        e = entries[0]
        assert e["event"] == "http_request"
        assert e["req"] == "abc123def456"
        assert e["method"] == "POST"
        assert e["path"] == "/ask"
        assert e["src"] == __name__  # calling module recorded as source
        assert "T" in e["ts"]  # ISO-8601
        assert "+" in e["ts"] or e["ts"].endswith("Z")  # timezone present

    def test_each_entry_is_one_parseable_line(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.trace("a", n=1)
        apiTrace.trace("b", n=2)
        with open(apiTrace.log_file_path(), encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        assert len(lines) == 2
        for ln in lines:
            json.loads(ln)  # must not raise

    def test_file_anchored_at_project_root(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.trace("e")
        expected = _PROJECT_ROOT / "log" / "api_debug.log"
        assert apiTrace.log_file_path() == expected
        assert expected.exists()

    def test_req_defaults_to_contextvar(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.set_request_id("req_from_ctx")
        apiTrace.trace("e")
        assert _entries()[0]["req"] == "req_from_ctx"

    def test_req_null_outside_request_context(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.trace("warmup_event")
        assert _entries()[0]["req"] is None

    def test_string_and_list_truncation(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.trace("e", text="x" * 400, items=["a", "b", "c", "d", "e", "f", "g", "h"])
        e = _entries()[0]
        assert len(e["text"]) == len("x" * 300) + 1
        assert e["text"].endswith("…")
        assert e["items"][:5] == ["a", "b", "c", "d", "e"]
        assert e["items"][5] == "(+3 more)"

    def test_non_serializable_values_coerced(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")
        apiTrace.trace("e", weird=frozenset({"a"}))
        json.loads(open(apiTrace.log_file_path(), encoding="utf-8").read())

    def test_write_failure_latches_and_never_raises(self, monkeypatch):
        monkeypatch.setenv("RISKI_API_TRACE", "1")

        class Boom:
            def __getattr__(self, name):
                raise OSError("disk full")

        monkeypatch.setattr(apiTrace, "_logger", Boom())
        apiTrace.trace("e")  # must not raise
        # latched: later calls are silent even with a healthy logger
        monkeypatch.setattr(apiTrace, "_logger",
                            __import__("logging").getLogger("riski.apitrace"))
        apiTrace.trace("e2")
        assert not apiTrace.log_file_path().exists()


class TestRequestIds:
    def test_new_request_ids_unique(self):
        ids = {apiTrace.new_request_id() for _ in range(200)}
        assert len(ids) == 200
        assert all(len(i) == 12 for i in ids)


# ======================================================================
# Instrumentation (change: api-debug-logging tasks 2.1, 3.1, 4.2, 5.1)
# — every traced component writes its expected event with the request id
# ======================================================================
import contextlib  # noqa: E402

import src.pgIntentRouter as ir  # noqa: E402


class _FakeConn:
    def execute(self, *a, **k):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def connect(self):
        return _FakeConn()


def _enable(monkeypatch, req="req-1"):
    monkeypatch.setenv("RISKI_API_TRACE", "1")
    apiTrace.set_request_id(req)


def _last_event(event):
    es = [e for e in _entries() if e["event"] == event]
    assert es, f"no {event!r} entry in trace"
    return es[-1]


class TestIntentRouteTrace:
    def test_route_decision_traced_with_reasons(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setattr(ir, "get_engine", lambda readonly=False: _FakeEngine())
        monkeypatch.setattr(ir, "build_slot_vocab", lambda conn, intent, slot: [])

        class StubDecoder:
            def decode(self, query, cfg, gremium_vocab, **kwargs):
                return {"intent": "ask_decision_date",
                        "scores": {"search_topic": 0.1,
                                   "ask_decision_date": 0.9},
                        "slots": {"gremium": "gemeinderat"}}

        router = ir.IntentRouter(cfg=ir.load_intents_config())
        router._decoder = StubDecoder()
        decoded = router.decode("wann wurde beschlossen")
        assert decoded["intent"] == "ask_decision_date"
        e = _last_event("intent_route")
        assert e["req"] == "req-1"
        assert e["intent"] == "ask_decision_date"
        assert e["confidence"] == 0.9
        assert e["scores"]["ask_decision_date"] == 0.9
        assert e["slots"] == {"gremium": "gemeinderat"}
        assert e["decoder_error"] is None
        assert not [x for x in _entries() if x["event"] == "intent_fallback"]

    def test_decoder_unreachable_fallback_traced(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setattr(ir, "get_engine", lambda readonly=False: _FakeEngine())
        monkeypatch.setattr(ir, "build_slot_vocab", lambda conn, intent, slot: [])

        class BoomDecoder:
            def decode(self, query, cfg, gremium_vocab, **kwargs):
                raise ConnectionError("sysone down")

        router = ir.IntentRouter(cfg=ir.load_intents_config())
        router._decoder = BoomDecoder()
        decoded = router.decode("irgendwas")
        assert decoded["intent"] == router.cfg["fallback_intent"]
        e = _last_event("intent_fallback")
        assert e["step"] == "decoder_unreachable"
        assert e["req"] == "req-1"
        r = _last_event("intent_route")
        assert r["intent"] == router.cfg["fallback_intent"]
        assert "unreachable" in r["decoder_error"]

    def test_empty_result_fallback_traced(self, monkeypatch):
        _enable(monkeypatch)
        router = ir.IntentRouter(cfg=ir.load_intents_config())
        resolved = {"intent": "search_topic", "handler": "search",
                    "answer_mode": "summary", "filters": [], "notes": [],
                    "gremium": None}
        out = router.run_search(None, "q", resolved, summarize=False,
                                search_fn=lambda *a, **k: {"top_files": []})
        assert out["empty_response"]
        e = _last_event("intent_fallback")
        assert e["step"] == "empty_response"
        assert e["req"] == "req-1"

    def test_filters_dropped_fallback_traced(self, monkeypatch):
        _enable(monkeypatch)
        router = ir.IntentRouter(cfg=ir.load_intents_config())
        resolved = {"intent": "search_topic", "handler": "search",
                    "answer_mode": "summary",
                    "filters": [{"facet": "organization", "op": "in",
                                 "values": ["X"]}],
                    "notes": [], "gremium": None}
        calls = []

        def fake_search(session, query, top_k=10, filters=None, signals=None,
                        summarize=False):
            calls.append(filters)
            return ({"top_files": [{"oparlKey": "f1"}]} if len(calls) > 1
                    else {"top_files": []})

        out = router.run_search(None, "q", resolved, summarize=False,
                                search_fn=fake_search)
        assert len(calls) == 2
        e = _last_event("intent_fallback")
        assert e["step"] == "filters_dropped"
        assert e["filters"][0]["facet"] == "organization"


class TestThreadTurnTrace:
    def test_followup_via_deictic_proform(self, monkeypatch):
        _enable(monkeypatch)
        cls = ir.classify_thread_turn("welche umweltauswirkungen hat das",
                                      "search_topic", {}, None,
                                      recall_confident=True)
        assert cls["action"] == "followup"
        e = _last_event("thread_turn")
        assert e["action"] == "followup"
        assert e["deictic"] is True
        assert e["req"] == "req-1"
        assert e["query"].startswith("welche umweltauswirkungen")

    def test_break_on_clear_target(self, monkeypatch):
        _enable(monkeypatch)
        cls = ir.classify_thread_turn("wohnen in karlsruhe", "search_topic",
                                      {"search_topic": 0.9}, "wohnen")
        assert cls["action"] == "break"
        e = _last_event("thread_turn")
        assert e["action"] == "break"
        assert e["topic_focus"] == "wohnen"


class TestClarificationTrace:
    def test_short_fuzzy_multi_cluster_traced(self, monkeypatch):
        _enable(monkeypatch)
        related = [
            {"oparl_key": "r1", "shared_tags": ["a", "b"], "name": "N1"},
            {"oparl_key": "r2", "shared_tags": ["a", "c"], "name": "N2"},
            {"oparl_key": "r3", "shared_tags": ["b", "c"], "name": "N3"},
        ]
        monkeypatch.setattr(
            "src.kg.kgQueries.related_by_tags", lambda top, **k: related)
        monkeypatch.setattr(
            "src.kg.kgFollowups.seal_state_or_none", lambda s, sid: "tok")
        monkeypatch.setattr(
            "src.kg.kgFollowups.generate_followups",
            lambda *a, **k: {"questions": ["q1", "q2"]})

        from src.apiServer import _kg_enrich
        result = {"top_files": [{"oparlKey": "f1"}], "summary": None}
        _kg_enrich(result, "wohnen", "sid-1")  # 1 word → short-fuzzy
        assert result.get("clarification")
        e = _last_event("clarification_mode")
        assert e["reason"] == "short-fuzzy multi-cluster"
        assert e["clusters"] == 3
        assert e["query_words"] == 1
        assert e["req"] == "req-1"


class TestMiddlewareTrace:
    def test_request_response_share_req_id(self, monkeypatch):
        _enable(monkeypatch)
        from fastapi.testclient import TestClient
        from src import apiServer

        def _no_db():
            raise RuntimeError("no DB in unit context")

        monkeypatch.setattr(apiServer, "get_db_session", _no_db)
        with TestClient(apiServer.app) as client:
            r = client.post("/ask", json={"query": "wohnen in karlsruhe"})
        assert r.status_code == 503  # get_db_session stubbed to fail
        http_req = _last_event("http_request")
        http_resp = _last_event("http_response")
        api_q = _last_event("api_query")
        assert http_req["path"] == "/ask"
        assert http_req["method"] == "POST"
        assert http_req["req"] == http_resp["req"] == api_q["req"]
        assert http_resp["status"] == 503
        assert api_q["endpoint"] == "ask"
        assert api_q["query"] == "wohnen in karlsruhe"


class TestSummarizerTrace:
    def test_summarizer_event(self, monkeypatch):
        _enable(monkeypatch)
        import src.pgResultSummarizer as pc
        from src.tests.test_unit_pgResultSummarizer import (
            FakeSession, make_result,
        )
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "test-model")
        monkeypatch.setattr(pc.remote, "chat",
                            lambda *a, **k: {"content": "Zusammenfassung."})
        result = make_result(2)
        pc.ResultSummarizer(FakeSession({})).summarize(result)
        e = _last_event("summarizer")
        assert e["docs"] == 2
        assert e["grounded"] == 0
        assert e["layer"] == "Teaser"
        assert e["req"] == "req-1"


class TestRecallTrace:
    def test_search_stage_entry_traced_before_failure(self, monkeypatch):
        """The recall entry event fires at stage entry — even if the
        heavy pipeline behind it fails (no embedding endpoint here)."""
        _enable(monkeypatch)
        import src.pgTimeline as pt

        def boom(text, *a, **k):
            raise RuntimeError("embed endpoint down")

        monkeypatch.setattr(pt, "call_embedding_model", boom)
        with pytest.raises(RuntimeError):
            pt.search_stage(type("S", (), {"connection": lambda self: None})(),
                            "wohnen in karlsruhe", hybrid=False)
        e = _last_event("recall")
        assert e["stage"] == "search_stage"
        assert e["query"] == "wohnen in karlsruhe"
        assert e["req"] == "req-1"


class TestKgTrace:
    def test_related_by_tags_event(self, monkeypatch):
        _enable(monkeypatch)
        from src.kg import kgQueries as kq
        rows = [("doc-2", 2, 4.0, ["Umwelt", "Bauen"])]
        names = [("doc-2", "Dokument 2", "d2.pdf", "2024-01-01", "T")]
        conn_calls = []

        class Conn:
            def execute(self, *a, **k):
                conn_calls.append(1)
                rows_ = rows if len(conn_calls) == 1 else names
                class R:
                    def fetchall(self):
                        return rows_
                return R()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Eng:
            def connect(self):
                return Conn()

        monkeypatch.setattr(kq, "get_engine", lambda readonly=False: Eng())
        out = kq.related_by_tags([("doc-1", 0.5)])
        assert len(out) == 1
        e = _last_event("kg_related")
        assert e["top_docs"] == 1
        assert e["results"] == 1
        assert e["req"] == "req-1"

    def test_topic_focus_event(self, monkeypatch):
        _enable(monkeypatch)
        from src.kg import kgQueries as kq
        monkeypatch.setattr(kq, "_TOPIC_CACHE", {"umwelt": [1.0, 0.0],
                                                 "bauen": [0.0, 1.0]})
        monkeypatch.setattr("src.remote.embed", lambda q: [1.0, 0.0])
        assert kq.topic_focus_for_query("umwelt in karlsruhe") == "umwelt"
        e = _last_event("kg_topic_focus")
        assert e["topic"] == "umwelt"
        assert e["similarity"] == 1.0
        assert e["req"] == "req-1"

    def test_followups_and_thread_events(self, monkeypatch):
        _enable(monkeypatch)
        from src.kg import kgFollowups as kf

        class FakeRemote:
            # generate_followups probes chat_json: truthy → remote is the
            # client (its .chat method is used, no real LLM call)
            chat_json = lambda *a, **k: None  # noqa: E731

            def chat(self, messages, model=None, **kwargs):
                return '{"questions": ["Q1?", "Q2?", "Q3?"]}'

        out = kf.generate_followups("Antworttext.", statements=None,
                                    topics=["umwelt"], remote=FakeRemote())
        assert len(out["questions"]) == 3
        e = _last_event("kg_followups")
        assert e["questions"] == 3
        assert e["topics"] == ["umwelt"]
        assert e["req"] == "req-1"

        token = kf.seal_state({"q0": "wohnen"}, "sid-1")
        opened = kf.open_state(token, "sid-1")
        assert opened["q0"] == "wohnen"
        seal_e = [x for x in _entries()
                  if x["event"] == "kg_thread" and x["mode"] == "seal"][-1]
        open_e = [x for x in _entries()
                  if x["event"] == "kg_thread" and x["mode"] == "open"][-1]
        assert seal_e["token"] == token[:8]
        assert len(seal_e["token"]) == 8  # prefix only, never the full token
        assert open_e["token"] == token[:8]
        assert open_e["req"] == "req-1"
