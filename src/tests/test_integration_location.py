"""Integration tests for location-scoped retrieval (change:
add-location-intent). Live read-only checks against the real RIS database;
the location resolver (trigram word similarity), the association-table
candidate path, and the stage-1 result contract."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import MetaData, Table, select

from src.pgIntentRouter import (
    find_intent,
    load_intents_config,
    resolve_location,
)
from src.pgLocationSearch import (
    candidate_agenda_items,
    candidate_files,
    location_search_stage,
)

pytestmark = pytest.mark.integration


def _street_id(session, name):
    with session.bind.connect() as conn:
        street = Table("Street", MetaData(), autoload_with=conn)
        return conn.execute(
            select(street.c.id).where(street.c.name == name)).scalar()


@pytest.fixture(scope="module")
def session():
    from src.pgTimeline import get_db_session

    session = get_db_session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def cfg():
    return load_intents_config()


@pytest.fixture(scope="module")
def intent(cfg):
    return find_intent(cfg, "ask_location")


class TestResolveLocationLive:
    def test_typo_resolves_with_suffix_threshold(self, cfg, intent, session):
        out = resolve_location(session, "was passiert am freidrichsplatz",
                               intent)
        assert out["locations"]
        best = out["locations"][0]
        assert best["name"] == "Friedrichsplatz"
        assert best["type"] == "street"
        assert best["score"] >= 0.5
        assert out["threshold"] < 0.5  # suffix lowered the threshold

    def test_bare_name_resolves(self, cfg, intent, session):
        out = resolve_location(session, "friedrichsplatz", intent)
        assert out["locations"][0]["name"] == "Friedrichsplatz"
        assert out["locations"][0]["score"] == 1.0

    def test_suffixless_district_resolves(self, cfg, intent, session):
        out = resolve_location(session, "durlach", intent)
        assert out["locations"][0]["name"] == "Durlach"
        assert out["locations"][0]["type"] == "district"

    def test_ambiguity_reported_in_note(self, cfg, intent, session):
        out = resolve_location(
            session, "platz an der neureuter strasse", intent)
        assert out["locations"]
        assert out["alternates"]
        assert "mehrere orte" in out["note"].lower()

    def test_non_location_query_unresolved(self, cfg, intent, session):
        out = resolve_location(session, "erzähl was zur theatersanierung",
                               intent)
        assert out["locations"] == []
        assert "kein ort" in out["note"].lower()


class TestAssociationCandidates:
    """Street Friedrichsplatz (id 542): 16 agenda-item refs and 135 file
    refs in the DB, 3 of them boilerplate-gated (132 visible)."""

    LOC = [{"type": "street", "id": 542, "name": "Friedrichsplatz",
            "score": 1.0}]

    def test_all_non_gated_agenda_items_are_candidates(self, session):
        with session.bind.connect() as conn:
            rows = candidate_agenda_items(conn, self.LOC, "friedrichsplatz",
                                          cap=500)
        # 16 linked agenda items, none gated
        assert len(rows) == 16

    def test_all_non_gated_files_available(self, session):
        with session.bind.connect() as conn:
            rows, total = candidate_files(conn, self.LOC, "friedrichsplatz",
                                          top_k=500)
        assert total == 132  # 135 refs minus 3 boilerplate-gated
        assert len(rows) == 132

    def test_top_k_cap_applied_with_total(self, session):
        with session.bind.connect() as conn:
            rows, total = candidate_files(conn, self.LOC, "friedrichsplatz",
                                          top_k=10)
        assert len(rows) == 10
        assert total == 132

    def test_gate_excludes_boilerplate(self, session):
        with session.bind.connect() as conn:
            assoc = Table("Streets_items_Files", MetaData(),
                          autoload_with=conn)
            gated = conn.execute(
                select(assoc.c.file_id).where(
                    assoc.c.street_id == 542,
                    assoc.c.gate_status == "boilerplate")).scalars().all()
            rows, _total = candidate_files(conn, self.LOC, "friedrichsplatz",
                                           top_k=500)
        sids = {f.sid for f, _sim in rows}
        assert not sids.intersection(gated)

    def test_newest_meeting_wins_the_cap(self, session):
        """Files attached to the most recent meetings fill the capped list;
        a recent meeting outranks an older publication date (D6)."""
        fm = Table("File__meeting__Meeting", MetaData(),
                   autoload_with=session.bind)
        meeting = Table("Meeting", MetaData(), autoload_with=session.bind)
        with session.bind.connect() as conn:
            rows, _total = candidate_files(conn, self.LOC, "friedrichsplatz",
                                           top_k=10)
            latest = {
                sid: d for sid, d in conn.execute(
                    select(fm.c.srcSid,
                           sa.func.max(meeting.c.start_date).label("d"))
                    .select_from(fm.join(meeting, fm.c.tgtSid == meeting.c.sid))
                    .where(fm.c.srcSid.in_([f.sid for f, _s in rows]))
                    .group_by(fm.c.srcSid))
            }
        dates = [latest.get(f.sid) or f.date for f, _s in rows]
        assert all(d is not None for d in dates)
        assert dates == sorted(dates, reverse=True)

    def test_truncation_note_present(self, session):
        result = location_search_stage(
            session, "friedrichsplatz",
            [{"type": "street", "id": 542, "name": "Friedrichsplatz",
              "score": 1.0}],
            top_k=10, summarize=False)
        assert any("132" in n and "neuesten" in n
                   for n in result["notes"])

    def test_no_truncation_note_below_cap(self, session):
        # Rosenhofweg links a single file — well below the cap, so the
        # truncation note must not appear
        result = location_search_stage(
            session, "rosenhofweg",
            [{"type": "street", "id": _street_id(session, "Rosenhofweg"),
              "name": "Rosenhofweg", "score": 1.0}],
            top_k=10, summarize=False)
        assert result["top_files"]
        assert not any("neuesten" in n for n in result["notes"])


class TestLocationSearchStage:
    def test_stage1_contract_and_map_scope(self, session, monkeypatch):
        """Response shape equals a search answer; with no reranker
        configured (RERANK_MODE None) all capped candidates are kept."""
        import src.pgLocationSearch as locmod
        from src.pgTimeline import RERANK_MODE

        if RERANK_MODE is not None:
            pytest.skip("reranker configured — acceptance depends on model")
        monkeypatch.setattr(locmod, "RERANK_ACCEPT", 0.0)

        result = location_search_stage(
            session, "friedrichsplatz",
            [{"type": "street", "id": 542, "name": "Friedrichsplatz",
              "score": 1.0}],
            top_k=10, summarize=False)

        assert set(result) >= {"query", "top_files", "matched_entities",
                               "facets", "applied_filters"}
        assert len(result["top_files"]) == 10
        for f in result["top_files"]:
            assert {"sid", "oparlKey", "name", "fileName", "downloadurl",
                    "oparlId", "date", "distance", "match"} <= set(f)
            assert f["match"] == {"location": True}
        # matched entities: linked agenda items + the returned files
        types = {m["type"] for m in result["matched_entities"]}
        assert types <= {"AgendaItem", "File"}
        assert any(m["type"] == "AgendaItem"
                   for m in result["matched_entities"])

    def test_answer_files_are_linked_to_location(self, session):
        with session.bind.connect() as conn:
            assoc = Table("Streets_items_Files", MetaData(),
                          autoload_with=conn)
            linked = set(conn.execute(
                select(assoc.c.file_id).where(
                    assoc.c.street_id == 542)).scalars().all())
        result = location_search_stage(
            session, "friedrichsplatz",
            [{"type": "street", "id": 542, "name": "Friedrichsplatz",
              "score": 1.0}],
            top_k=10, summarize=False)
        assert {f["sid"] for f in result["top_files"]} <= linked


class TestAskEndpointLocation:
    """POST /ask routes a location question end-to-end: resolved location
    in the response (additive field), stage-1 contract intact, map scope
    served for the session."""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from src import apiServer

        with TestClient(apiServer.app) as c:
            yield c

    @pytest.fixture(autouse=True)
    def stub_decode(self, monkeypatch):
        """Deterministic intent: the decision model's classification is
        verified by the decoder harness, not here."""
        from src.pgIntentRouter import IntentRouter

        monkeypatch.setattr(
            IntentRouter, "decode",
            lambda self, query, engine=None: {
                "intent": "ask_location", "scores": {"ask_location": 1.0},
                "slots": {}, "error": None,
            },
        )

    def test_location_answer_contract(self, client):
        resp = client.post("/ask", json={"query": "friedrichsplatz",
                                         "summarize": False})
        assert resp.status_code == 200
        result = resp.json()
        assert result["intent"] == "ask_location"
        # additive field: resolved location(s) echoed
        locations = result["location"]["locations"]
        assert locations and locations[0]["name"] == "Friedrichsplatz"
        assert not any("kein ort" in n.lower()
                       for n in result["fallback_notes"])
        # existing clients' fields unchanged
        assert {"top_files", "matched_entities", "facets",
                "applied_filters", "sessionId"} <= set(result)
        assert result["top_files"]
        assert all({"sid", "oparlKey", "name", "downloadurl", "date",
                    "distance", "match"} <= set(f)
                   for f in result["top_files"])

    def test_map_scope_for_location_session(self, client):
        resp = client.post("/ask", json={"query": "friedrichsplatz",
                                         "summarize": False})
        session_id = resp.json()["sessionId"]
        geo = client.get(f"/geo/{session_id}")
        assert geo.status_code == 200
        assert geo.json()["type"] == "FeatureCollection"
