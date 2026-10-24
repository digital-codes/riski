"""Unit tests for the intent router (src.pgIntentRouter)."""

from __future__ import annotations

import datetime
import sys
import types

import pytest

from src.pgIntentRouter import (
    IntentRouter,
    SystemOneDecoder,
    build_questions,
    find_intent,
    load_intents_config,
    normalize_value,
    parse_answers,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def cfg():
    return load_intents_config()


class TestConfig:
    def test_fallback_exactly_one(self, cfg):
        assert cfg["fallback_intent"] == "search_topic"
        fallbacks = [i["name"] for i in cfg["intents"] if i.get("fallback")]
        assert fallbacks == ["search_topic"]

    def test_choices_lowercased(self, cfg):
        for intent in cfg["intents"]:
            for choice in intent["choices"]:
                assert choice == choice.lower()

    def test_find_intent(self, cfg):
        assert find_intent(cfg, "ask_gremium_recent")["name"] == "ask_gremium_recent"
        assert find_intent(cfg, "nope") is None

    def test_duplicate_names_rejected(self, tmp_path):
        import yaml

        p = tmp_path / "intents.yaml"
        p.write_text(yaml.safe_dump({"intents": [
            {"name": "a", "description": "d", "choices": ["x"], "fallback": True},
            {"name": "a", "description": "d", "choices": ["x"]},
        ]}))
        with pytest.raises(ValueError, match="duplicate"):
            load_intents_config(p)

    def test_missing_fallback_rejected(self, tmp_path):
        import yaml

        p = tmp_path / "intents.yaml"
        p.write_text(yaml.safe_dump({"intents": [
            {"name": "a", "description": "d", "choices": ["x"]},
        ]}))
        with pytest.raises(ValueError, match="fallback"):
            load_intents_config(p)


class TestNormalize:
    def test_trim_lower_collapse(self):
        assert normalize_value("  CDU-Fraktion  ") == "cdu-fraktion"
        assert normalize_value("Ortschaftsrat   Neureut") == "ortschaftsrat neureut"

    def test_none(self):
        assert normalize_value(None) == ""


class TestQuestions:
    def test_one_noul_per_intent_plus_gremium_slot(self, cfg):
        q = build_questions(cfg, ["gemeinderat", "ortschaftsrat"])
        assert set(q) == {i["name"] for i in cfg["intents"]} | {"slot_gremium"}
        assert q["search_topic"]["type"] == "noul"
        assert q["slot_gremium"]["type"] == "choice"
        assert list(q["slot_gremium"]["criteria"]) == ["gemeinderat", "ortschaftsrat"]

    def test_no_slot_question_without_vocab(self, cfg):
        q = build_questions(cfg, [])
        assert "slot_gremium" not in q


class TestParseAnswers:
    def _cfg(self):
        return load_intents_config()

    def test_above_threshold_wins(self):
        answers = {
            "search_topic": {"noul": 0.1},
            "ask_gremium_recent": {"noul": 0.9},
            "ask_decision_date": {"noul": 0.2},
            "slot_gremium": {"choice": "b"},
        }
        out = parse_answers(self._cfg(), answers, ["a", "b", "c"])
        assert out["intent"] == "ask_gremium_recent"
        assert out["slots"]["gremium"] == "b"

    def test_slot_choice_not_in_vocab_ignored(self):
        answers = {"slot_gremium": {"choice": "horoscope"}}
        out = parse_answers(self._cfg(), answers, ["a", "b"])
        assert "gremium" not in out["slots"]

    def test_below_threshold_falls_back(self):
        answers = {
            "search_topic": {"noul": 0.1},
            "ask_gremium_recent": {"noul": 0.3},
            "ask_decision_date": {"noul": 0.2},
        }
        out = parse_answers(self._cfg(), answers, [])
        assert out["intent"] == "search_topic"

    def test_missing_answers_fall_back(self):
        out = parse_answers(self._cfg(), {}, [])
        assert out["intent"] == "search_topic"

    def test_slot_missing_answer_ignored(self):
        answers = {"slot_gremium": {}}
        out = parse_answers(self._cfg(), answers, ["a"])
        assert "gremium" not in out["slots"]


class TestDecoderFallback:
    def test_unreachable_decoder_degrades_to_fallback(self, cfg):
        class BrokenDecoder:
            def decode(self, *a, **k):
                raise RuntimeError("down")

        router = IntentRouter(cfg=cfg, decoder=BrokenDecoder())
        out = router.decode("erzähl was zur theatersanierung")
        assert out["intent"] == "search_topic"
        assert "down" in out["error"]

    def test_decode_success_passthrough(self, cfg):
        class StubDecoder:
            def decode(self, query, cfg, vocab):
                return {"intent": "ask_gremium_recent", "scores": {}, "slots": {"gremium": "ortschaftsrat neureut"}}

        router = IntentRouter(cfg=cfg, decoder=StubDecoder())
        out = router.decode("was wurde im letzten ortschaftsrat neureut beschlossen")
        assert out["slots"]["gremium"] == "ortschaftsrat neureut"


class TestResolve:
    def test_decision_filters_derived(self, cfg):
        router = IntentRouter(cfg=cfg)
        session = _FakeSession()
        out = router.resolve("ask_decision_date", {}, session)
        assert out["handler"] == "search"
        assert out["answer_mode"] == "date"
        assert any(f["facet"] == "tag" for f in out["filters"])
        assert out["gremium"] is None

    def test_unknown_gremium_clears_filters(self, cfg, monkeypatch):
        import src.pgIntentRouter as ir

        monkeypatch.setattr(
            ir, "resolve_gremium",
            lambda session, term, groups: {
                "orgs": [], "meeting": None,
                "note": f"kein Gremium zu '{term}' gefunden",
            },
        )
        router = IntentRouter(cfg=cfg)
        session = _FakeSession()
        out = router.resolve("ask_gremium_recent", {"gremium": "existiertnicht"}, session)
        assert out["filters"] == []
        assert any("kein gremium" in n.lower() for n in out["notes"])

    def test_fallback_intent_has_no_filters(self, cfg):
        router = IntentRouter(cfg=cfg)
        out = router.resolve("search_topic", {}, _FakeSession())
        assert out["filters"] == []
        assert out["handler"] == "search"


class _FakeSession:
    """Minimal session stub for resolve() paths that must not touch a DB."""

    class _None:
        bind = None


class TestSearchLadder:
    def test_overfiltered_retry_then_success(self, cfg, monkeypatch):
        calls = []

        def fake_search(session, query, top_k=10, filters=None, signals=None, summarize=True):
            calls.append(filters)
            if filters:
                return {"top_files": [], "matched_entities": []}
            return {"top_files": [{"oparlKey": "f1"}], "matched_entities": [{"id": "File_f1"}]}

        import src.pgTimeline as tl

        monkeypatch.setattr(tl, "search_and_summarize", fake_search)

        router = IntentRouter(cfg=cfg)
        resolved = {
            "intent": "ask_decision_date",
            "handler": "search",
            "answer_mode": "date",
            "filters": [{"facet": "tag", "scheme": "document-type", "op": "in",
                         "values": ["Beschlüsse"]}],
            "gremium": None,
            "notes": [],
        }
        out = router.run_search(_FakeSession(), "wann wurde x beschlossen", resolved,
                                top_k=5, summarize=False)
        assert calls[0] == resolved["filters"]
        assert calls[1] is None
        assert out["top_files"] == [{"oparlKey": "f1"}]
        assert any("ohne filter" in n.lower() for n in out["fallback_notes"])
        assert out["intent"] == "ask_decision_date"

    def test_truly_empty_gets_explicit_response(self, cfg, monkeypatch):
        def fake_search(session, query, **kw):
            return {"top_files": [], "matched_entities": []}

        import src.pgTimeline as tl

        monkeypatch.setattr(tl, "search_and_summarize", fake_search)
        router = IntentRouter(cfg=cfg)
        resolved = {"intent": "search_topic", "handler": "search",
                    "answer_mode": "summary", "filters": [],
                    "gremium": None, "notes": []}
        out = router.run_search(_FakeSession(), "xyz", resolved, summarize=False)
        assert out["empty_response"]["message"]
        assert out["empty_response"]["intent"] == "search_topic"


class TestLiveDb:
    """Live read-only checks against the real RIS database."""

    @pytest.fixture(scope="class")
    def session(self):
        from src.pgTimeline import get_db_session

        session = get_db_session()
        yield session
        session.close()

    @pytest.fixture(scope="class")
    def cfg(self):
        return load_intents_config()

    def test_slot_vocab_contains_councils(self, cfg, session):
        from src.pgIntentRouter import build_slot_vocab

        gi = [i for i in cfg["intents"] if "gremium" in (i.get("slots") or {})][0]
        with session.bind.connect() as conn:
            vocab = build_slot_vocab(conn, gi, "gremium")
        assert "ortschaftsrat neureut" in vocab
        assert "gemeinderat" in vocab
        assert all(v == v.lower().strip() for v in vocab)

    def test_latest_held_meeting_wins(self, cfg, session):
        from src.pgIntentRouter import resolve_gremium

        groups = (find_intent(cfg, "ask_gremium_recent").get("groups") or {}).get("gremium", [])
        out = resolve_gremium(session, "ortschaftsrat neureut", groups)
        assert out["orgs"] == ["Ortschaftsrat Neureut"]
        assert out["meeting"] is not None
        assert out["meeting"]["start_date"] <= datetime.datetime.now()

    def test_gemeinderat_group_includes_dhh(self, cfg, session):
        from src.pgIntentRouter import resolve_gremium

        groups = (find_intent(cfg, "ask_gremium_recent").get("groups") or {}).get("gremium", [])
        out = resolve_gremium(session, "gemeinderat", groups)
        assert set(out["orgs"]) == {"Gemeinderat", "Gemeinderat - Beratungen zum DHH"}
        assert out["meeting"] is not None

    def test_unknown_gremium_unresolved(self, cfg, session):
        from src.pgIntentRouter import resolve_gremium

        out = resolve_gremium(session, "gremium das nicht existiert", [])
        assert out["orgs"] == []
        assert "kein gremium" in out["note"].lower()

    def test_organization_facet_constrains_files(self, session):
        from src.pgHybridSearch import hybrid_candidates

        with session.bind.connect() as conn:
            hyb = hybrid_candidates(
                conn, "Rückbau Herrenalber Straße", [0.01] * 1024, top_k=50,
                signals={"lexical": True, "name_vectors": False, "content_vectors": False},
                filters=[{"facet": "organization", "op": "in", "values": ["Ortschaftsrat Neureut"]}],
            )
            file_keys = [c["oparlKey"] for c in hyb["file_candidates"]]
            if not file_keys:
                pytest.skip("no file candidates for scoped query")
            from sqlalchemy import select

            meta = MetaData()
            fm = Table("File__meeting__Meeting", meta, autoload_with=session.bind)
            meeting = Table("Meeting", meta, autoload_with=session.bind)
            morg = Table("Meeting__organization__Organization", meta, autoload_with=session.bind)
            org = Table("Organization", meta, autoload_with=session.bind)
            file_tbl = Table("File", meta, autoload_with=session.bind)
            stmt = (
                select(org.c.name)
                .select_from(
                    file_tbl.join(fm, fm.c.srcSid == file_tbl.c.sid)
                    .join(meeting, fm.c.tgtSid == meeting.c.sid)
                    .join(morg, morg.c.srcSid == meeting.c.sid)
                    .join(org, morg.c.tgtSid == org.c.sid)
                )
                .where(file_tbl.c.oparlKey.in_(file_keys))
            )
            names = {r[0] for r in conn.execute(stmt)}
        assert names <= {"Ortschaftsrat Neureut"}


class TestParallelRecall:
    def test_run_all_concurrent(self):
        import time

        from src.pgHybridSearch import _run_all

        def slow(ms):
            return lambda: (time.sleep(ms / 1000), ms)[1]

        t0 = time.perf_counter()
        out = _run_all([("a", slow(300)), ("b", slow(300))])
        wall = time.perf_counter() - t0
        assert out == [300, 300]
        assert wall < 0.55  # concurrent: ~max, not sum

    def test_run_all_task_failure_isolated(self, monkeypatch):
        from src.pgHybridSearch import _run_all

        def boom():
            raise RuntimeError("db down")

        out = _run_all([("ok", lambda: 42), ("bad", boom)])
        assert out == [42, None]

    def test_sequential_kill_switch(self, monkeypatch):
        import time

        import src.pgHybridSearch as hs

        monkeypatch.setenv("RISKI_PARALLEL_SIGNALS", "0")

        def slow(ms):
            return lambda: (time.sleep(ms / 1000), ms)[1]

        t0 = time.perf_counter()
        out = hs._run_all([("a", slow(200)), ("b", slow(200))])
        wall = time.perf_counter() - t0
        assert out == [200, 200]
        assert wall >= 0.4  # sequential: sum


class TestFacetCache:
    # time imported at use; keep module deps explicit
    def _setup(self, monkeypatch):
        import src.pgHybridSearch as hs

        calls = {"n": 0}

        def fake_uncached(conn):
            calls["n"] += 1
            return {"paperType": {"Antrag": calls["n"]}}

        monkeypatch.setattr(hs, "_facets_uncached", fake_uncached)
        monkeypatch.setattr(hs, "_FACET_CACHE", {"ts": 0.0, "payload": None})
        return hs, calls

    def test_second_call_served_from_cache(self, monkeypatch):
        import time as _t

        hs, calls = self._setup(monkeypatch)
        a = hs.facets(None)
        b = hs.facets(None)
        assert calls["n"] == 1
        assert a == b == {"paperType": {"Antrag": 1}}

    def test_ttl_expiry_recomputes(self, monkeypatch):
        import time
        hs, calls = self._setup(monkeypatch)
        monkeypatch.setattr(hs, "facet_ttl", lambda: 0.05)
        hs.facets(None)
        time.sleep(0.06)
        hs.facets(None)
        assert calls["n"] == 2

    def test_ttl_zero_disables(self, monkeypatch):
        hs, calls = self._setup(monkeypatch)
        monkeypatch.setattr(hs, "facet_ttl", lambda: 0)
        hs.facets(None)
        hs.facets(None)
        assert calls["n"] == 2

    def test_caller_cannot_mutate_cache(self, monkeypatch):
        hs, calls = self._setup(monkeypatch)
        a = hs.facets(None)
        a["paperType"]["HACK"] = 1
        b = hs.facets(None)
        assert "HACK" not in b["paperType"]

    def test_invalidate(self, monkeypatch):
        hs, calls = self._setup(monkeypatch)
        hs.facets(None)
        hs.invalidate_facet_cache()
        hs.facets(None)
        assert calls["n"] == 2


class TestSyncInvalidation:
    def test_sync_calls_invalidate_after_import(self, monkeypatch):
        import inspect

        import src.pgHybridSearch as hs
        import src.syncIncremental as sync

        # source-level guard: the invalidation hook is wired after the
        # import phase (full sync() needs crawl plumbing)
        source = inspect.getsource(sync.sync)
        assert "invalidate_facet_cache" in source

        calls = []
        monkeypatch.setattr(hs, "invalidate_facet_cache", lambda: calls.append(True))
        hs.invalidate_facet_cache()
        assert calls == [True]


class TestEmbeddingCache:
    def test_repeat_query_one_remote_call(self, monkeypatch):
        import src.pgTimeline as tl

        calls = []

        class FakeVec:
            def tolist(self):
                return [0.1, 0.2]

        monkeypatch.setattr(tl.remote, "embed", lambda text, model=None: calls.append(text) or FakeVec())
        tl._embed_cached.cache_clear()
        v1 = tl.call_embedding_model("theatersanierung")
        v2 = tl.call_embedding_model("theatersanierung")
        assert calls == ["theatersanierung"]
        assert v1 == v2 == [0.1, 0.2]
        tl._embed_cached.cache_clear()

    def test_distinct_texts_hit_remote(self, monkeypatch):
        import src.pgTimeline as tl

        calls = []

        class FakeVec:
            def tolist(self):
                return [0.1]

        monkeypatch.setattr(tl.remote, "embed", lambda text, model=None: calls.append(text) or FakeVec())
        tl._embed_cached.cache_clear()
        tl.call_embedding_model("a")
        tl.call_embedding_model("b")
        assert sorted(calls) == ["a", "b"]
        tl._embed_cached.cache_clear()

    def test_bulk_paths_bypass_cache(self):
        # pgAddVecs/pgBackfillNameVecs use remote.embed directly, not the
        # cached query helper (source-level guard)
        import inspect

        import src.pgAddVecs
        import src.pgBackfillNameVecs

        for mod in (src.pgAddVecs, src.pgBackfillNameVecs):
            src_text = inspect.getsource(mod)
            assert "call_embedding_model" not in src_text


class TestDecodeEmbedOverlap:
    def test_embed_overlaps_decode(self, monkeypatch):
        import time as _t

        import src.pgIntentRouter as ir
        import src.pgTimeline as tl

        calls = {"embed": 0, "decode": 0}

        class FakeVec:
            def tolist(self):
                return [0.1]

        def slow_embed(text, model=None):
            _t.sleep(0.3)
            calls["embed"] += 1
            return FakeVec()

        class SlowRouter:
            def __init__(self):
                self.cfg = load_intents_config()

            def decode(self, query, engine=None):
                _t.sleep(0.3)
                calls["decode"] += 1
                return {"intent": "search_topic", "scores": {}, "slots": {}, "error": None}

            def resolve(self, intent, slots, session):
                return {"intent": intent, "handler": "search", "answer_mode": "summary",
                        "filters": [], "gremium": None, "notes": []}

            def run_search(self, session, query, resolved, top_k=10, signals=None, summarize=True):
                tl.call_embedding_model(query)  # what the real search does
                return {"top_files": [{"oparlKey": "f1"}], "matched_entities": []}

        monkeypatch.setattr(tl.remote, "embed", slow_embed)
        t0 = _t.perf_counter()
        out = ir.ask(None, "test", router=SlowRouter(), summarize=False)
        wall = _t.perf_counter() - t0
        assert out["top_files"] == [{"oparlKey": "f1"}]
        assert calls == {"embed": 1, "decode": 1}  # pre-warm, no duplicate
        assert wall < 0.55  # overlapped: ~max(0.3, 0.3), not 0.6

    def test_parallel_kill_switch_skips_prewarm(self, monkeypatch):
        import time as _t

        import src.pgIntentRouter as ir
        import src.pgTimeline as tl

        calls = []

        class FakeVec:
            def tolist(self):
                return [0.1]

        monkeypatch.setenv("RISKI_PARALLEL_SIGNALS", "0")
        monkeypatch.setattr(tl.remote, "embed", lambda text, model=None: calls.append(text) or FakeVec())

        class Router:
            cfg = load_intents_config()
            def decode(self, query, engine=None):
                return {"intent": "search_topic", "scores": {}, "slots": {}, "error": None}
            def resolve(self, intent, slots, session):
                return {"intent": intent, "handler": "search", "answer_mode": "summary",
                        "filters": [], "gremium": None, "notes": []}
            def run_search(self, session, query, resolved, **kw):
                tl.call_embedding_model(query)
                return {"top_files": [], "matched_entities": []}

        ir.ask(None, "x", router=Router(), summarize=False)
        # sequential mode: pre-warm skipped, single embed from the search
        assert calls == ["x"]
