"""Unit tests for the intent router (src.pgIntentRouter)."""

from __future__ import annotations

import datetime

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
