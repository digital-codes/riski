"""Integration tests for georeference collection and the /geo endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.pgGeo import collect_geo, geo_available_for_keys

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def linked_agenda_key():
    """oparlKey of an agenda item linked to a street or district."""
    from src.db import get_engine

    with get_engine().connect() as c:
        row = c.execute(text("""
            SELECT ai."oparlKey" FROM "Streets_items_AgendaItems" s
            JOIN "AgendaItem" ai ON s.agendaitem_id = ai.sid
            LIMIT 1
        """)).first()
        if row is None:
            row = c.execute(text("""
                SELECT ai."oparlKey" FROM "Districts_items_AgendaItems" d
                JOIN "AgendaItem" ai ON d.agendaitem_id = ai.sid
                LIMIT 1
            """)).first()
        assert row is not None, "no linked agenda items in DB"
        return row[0]


class TestGeoCollection:
    def test_geo_available_for_linked_agenda_item(self, linked_agenda_key):
        from src.db import get_engine

        assert geo_available_for_keys(get_engine(), [linked_agenda_key]) is True

    def test_geo_unavailable_for_unknown_keys(self):
        from src.db import get_engine

        assert geo_available_for_keys(get_engine(), ["999999999"]) is False

    def test_collect_geo_returns_features_with_properties(self, linked_agenda_key):
        from src.db import get_engine

        fc = collect_geo(get_engine(), [linked_agenda_key])
        assert fc["type"] == "FeatureCollection"
        assert fc["features"], "expected at least one feature for a linked entity"
        for f in fc["features"]:
            assert f["properties"]["type"] in ("street", "district")
            assert f["properties"]["name"]
            assert linked_agenda_key in f["properties"]["agendaItems"]
            # WGS84 coordinates (Karlsruhe region: lon ~8.3-8.5, lat ~48.9-49.1)
            coords = f["geometry"]["coordinates"]
            while isinstance(coords[0], list):
                coords = coords[0]
            lon, lat = coords[0], coords[1]
            assert 8.0 < lon < 9.0 and 48.5 < lat < 49.5

    def test_collect_geo_empty_for_unknown_keys(self):
        from src.db import get_engine

        fc = collect_geo(get_engine(), ["999999999"])
        assert fc == {"type": "FeatureCollection", "features": []}


class TestGeoEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        from src.apiServer import app

        return TestClient(app)

    def test_geo_unknown_session_404(self, client):
        assert client.get("/geo/does-not-exist").status_code == 404

    def test_geo_for_session_with_georeferences(self, client, linked_agenda_key):
        # build a session whose answer set contains the linked agenda item
        from src.apiServer import _sessions

        session_id = "test-geo-session"
        _sessions[session_id] = {
            "query": "geo test",
            "filters": [],
            "node_ids": [f"AgendaItem_{linked_agenda_key}"],
            "result": {
                "query": "geo test",
                "graph": {"nodes": [{"id": f"AgendaItem_{linked_agenda_key}",
                                     "type": "AgendaItem", "oparlKey": linked_agenda_key}],
                          "edges": []},
                "matched_entities": [],
            },
        }
        r = client.get(f"/geo/{session_id}")
        assert r.status_code == 200
        fc = r.json()
        assert fc["type"] == "FeatureCollection"
        assert fc["features"]
        assert fc["features"][0]["properties"]["agendaItems"] == [linked_agenda_key]

    def test_geo_empty_for_session_without_georeferences(self, client):
        from src.apiServer import _sessions

        session_id = "test-geo-empty"
        _sessions[session_id] = {
            "query": "no geo",
            "filters": [],
            "node_ids": [],
            "result": {"query": "no geo", "graph": {"nodes": [], "edges": []},
                       "matched_entities": []},
        }
        r = client.get(f"/geo/{session_id}")
        assert r.status_code == 200
        assert r.json()["features"] == []
