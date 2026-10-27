"""Integration tests for the instance endpoint and instance-scoped config
plumbing (change: instance-agnostic-config)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from src import apiServer

    with TestClient(apiServer.app) as c:
        yield c


class TestInstanceEndpoint:
    def test_serves_karlsruhe_defaults(self, client):
        resp = client.get("/instance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["frontend"]["title"] == "RISKI Karlsruhe"
        assert data["frontend"]["default_query"].startswith("wo liegt die Governance")
        assert data["geo"]["city"] == "Karlsruhe"
        assert data["geo"]["map_center"] == [49.0069, 8.4037]
        assert data["geo"]["map_zoom"] == 12
        assert data["frontend"]["data_sources"]
        assert {"name", "url"} <= set(data["frontend"]["data_sources"][0])

    def test_no_secrets_exposed(self, client):
        """The endpoint is public — only the whitelisted frontend/geo
        sections may be served."""
        import json

        data = client.get("/instance").json()
        blob = json.dumps(data)
        assert "api_key" not in blob.lower()
        assert "password" not in blob.lower()
        assert set(data) == {"frontend", "geo"}

    def test_config_override_reaches_endpoint(self, client, monkeypatch):
        import src.instanceConfig as ic

        monkeypatch.setenv("RISKI_GEO__CITY", "Dresden")
        monkeypatch.setenv("RISKI_FRONTEND__TITLE", "RISKI Dresden")
        ic.clear_cache()
        try:
            data = client.get("/instance").json()
            assert data["geo"]["city"] == "Dresden"
            assert data["frontend"]["title"] == "RISKI Dresden"
        finally:
            ic.clear_cache()
