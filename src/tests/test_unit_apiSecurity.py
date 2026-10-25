"""Unit tests for api-security-hardening: client identity, sliding-window
limiter, input bounds, sanitized errors, CORS origins."""

import logging

import pytest

from src import apiRateLimit, apiServer

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------
# 1.1 client identity
# ----------------------------------------------------------------------

class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, peer, forwarded=None):
        self.client = _FakeClient(peer) if peer else None
        self.headers = {}
        if forwarded is not None:
            self.headers["x-forwarded-for"] = forwarded


def test_client_id_direct_peer(monkeypatch):
    monkeypatch.setenv("RISKI_TRUSTED_PROXIES", "127.0.0.1")
    req = _FakeRequest("1.2.3.4", forwarded="9.9.9.9")
    # peer not a trusted proxy: spoofed header ignored
    assert apiRateLimit.client_identifier(req) == "1.2.3.4"


def test_client_id_via_trusted_proxy(monkeypatch):
    monkeypatch.setenv("RISKI_TRUSTED_PROXIES", "127.0.0.1")
    req = _FakeRequest("127.0.0.1", forwarded="10.0.0.1, 1.2.3.4")
    # trusted proxy: last hop of the chain is the client
    assert apiRateLimit.client_identifier(req) == "1.2.3.4"


def test_client_id_via_trusted_proxy_no_header(monkeypatch):
    monkeypatch.setenv("RISKI_TRUSTED_PROXIES", "127.0.0.1")
    req = _FakeRequest("127.0.0.1")
    assert apiRateLimit.client_identifier(req) == "127.0.0.1"


# ----------------------------------------------------------------------
# 1.2 sliding-window limiter
# ----------------------------------------------------------------------

def test_limiter_allows_up_to_limit_then_blocks():
    lim = apiRateLimit.SlidingWindowLimiter(window_seconds=60)
    for _ in range(5):
        assert lim.check("c1", "llm", 5)
    assert not lim.check("c1", "llm", 5)
    # another client is unaffected
    assert lim.check("c2", "llm", 5)


def test_limiter_groups_are_independent():
    lim = apiRateLimit.SlidingWindowLimiter(window_seconds=60)
    for _ in range(3):
        assert lim.check("c1", "llm", 3)
    assert not lim.check("c1", "llm", 3)
    assert lim.check("c1", "search", 3)


def test_limiter_retry_after_bounds():
    lim = apiRateLimit.SlidingWindowLimiter(window_seconds=60)
    lim.check("c1", "llm", 1)
    assert not lim.check("c1", "llm", 1)
    retry = lim.retry_after("c1", "llm")
    assert 1 <= retry <= 61
    assert lim.retry_after("unknown", "llm") == 60


# ----------------------------------------------------------------------
# middleware behaviour over the app
# ----------------------------------------------------------------------

class _FakeDbSession:
    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(apiServer, "get_db_session", lambda: _FakeDbSession())
    monkeypatch.setattr(apiServer, "_sessions", {})
    apiRateLimit.limiter._hits.clear()
    return TestClient(apiServer.app, raise_server_exceptions=False)


def test_health_is_never_rate_limited(client, monkeypatch):
    monkeypatch.setenv("RISKI_RATE_LIMIT_SEARCH", "1")
    for _ in range(10):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_search_group_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("RISKI_RATE_LIMIT_SEARCH", "2")

    def fake_search(session, query, **kwargs):
        return {"graph": {"nodes": []}}

    monkeypatch.setattr(apiServer, "search_and_summarize", fake_search)
    assert client.post("/search", json={"query": "a"}).status_code == 200
    assert client.post("/search", json={"query": "b"}).status_code == 200
    resp = client.post("/search", json={"query": "c"})
    assert resp.status_code == 429
    assert "retry-after" in resp.headers


def test_llm_budget_blocks_inline_summary_before_work(client, monkeypatch):
    monkeypatch.setenv("RISKI_RATE_LIMIT_LLM", "1")
    calls = {"n": 0}

    def fake_search(session, query, **kwargs):
        calls["n"] += 1
        return {"graph": {"nodes": []}}

    monkeypatch.setattr(apiServer, "search_and_summarize", fake_search)
    assert client.post("/search", json={"query": "a", "summarize": True}).status_code == 200
    resp = client.post("/search", json={"query": "b", "summarize": True})
    assert resp.status_code == 429
    assert calls["n"] == 1  # the blocked request never reached the search
    # plain search still allowed (search budget untouched)
    assert client.post("/search", json={"query": "c"}).status_code == 200


def test_ask_endpoint_in_llm_group(client, monkeypatch):
    monkeypatch.setenv("RISKI_RATE_LIMIT_LLM", "1")

    def raise_no_llm(*a, **kw):
        raise AssertionError("intent router must not run when rate limited")

    monkeypatch.setattr(apiServer, "route_ask", raise_no_llm, raising=False)
    import src.pgIntentRouter as router

    monkeypatch.setattr(router, "ask", raise_no_llm)
    # first /ask runs (router patched to raise would 500, so patch success)
    monkeypatch.setattr(router, "ask", lambda s, q, **kw: {"graph": {"nodes": []}})
    assert client.post("/ask", json={"query": "a"}).status_code == 200
    resp = client.post("/ask", json={"query": "b"})
    assert resp.status_code == 429


# ----------------------------------------------------------------------
# 2.1 input bounds
# ----------------------------------------------------------------------

def test_oversized_query_rejected_422(client):
    resp = client.post("/search", json={"query": "x" * (apiServer.MAX_QUERY_LENGTH + 1)})
    assert resp.status_code == 422


def test_oversized_ask_query_rejected_422(client):
    resp = client.post("/ask", json={"query": "x" * 513})
    assert resp.status_code == 422


def test_too_many_filters_rejected_422(client):
    filters = [{"field": "paperType", "values": ["x"]} for _ in range(21)]
    resp = client.post("/search", json={"query": "a", "filters": filters})
    assert resp.status_code == 422


def test_max_length_boundary_ok(client, monkeypatch):
    monkeypatch.setattr(apiServer, "search_and_summarize", lambda s, q, **kw: {"graph": {"nodes": []}})
    resp = client.post("/search", json={"query": "x" * apiServer.MAX_QUERY_LENGTH})
    assert resp.status_code == 200


# ----------------------------------------------------------------------
# 2.2 sanitized errors
# ----------------------------------------------------------------------

def test_db_failure_returns_generic_503(client, monkeypatch):
    def raise_db():
        raise RuntimeError("FATAL: password authentication failed for user 'riski' at 10.0.0.5")

    monkeypatch.setattr(apiServer, "get_db_session", raise_db)
    resp = client.post("/search", json={"query": "a"})
    assert resp.status_code == 503
    body = resp.json()["detail"]
    assert "password" not in body
    assert "10.0.0.5" not in body
    assert body == "database temporarily unavailable"


def test_ask_exception_returns_correlation_id_only(client, monkeypatch):
    import src.pgIntentRouter as router

    def boom(session, query, **kw):
        raise ValueError("secret internal path /etc/riski/private.py")

    monkeypatch.setattr(router, "ask", boom)
    resp = client.post("/ask", json={"query": "a"})
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "secret" not in detail
    assert "correlation_id=" in detail


def test_log_contains_full_detail(client, monkeypatch, caplog):
    import src.pgIntentRouter as router

    def boom(session, query, **kw):
        raise ValueError("the full diagnosis for the log")

    monkeypatch.setattr(router, "ask", boom)
    with caplog.at_level(logging.ERROR, logger="riski.api"):
        client.post("/ask", json={"query": "a"})
    assert "the full diagnosis for the log" in caplog.text


# ----------------------------------------------------------------------
# 3.1 CORS origins from configuration
# ----------------------------------------------------------------------

def test_cors_origins_default(monkeypatch):
    monkeypatch.delenv("RISKI_CORS_ORIGINS", raising=False)
    assert apiServer._cors_origins() == [
        "http://localhost:5173", "http://localhost:4173", "http://localhost:5199",
    ]


def test_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv("RISKI_CORS_ORIGINS", "https://ris.example.org, https://alt.example.org")
    assert apiServer._cors_origins() == ["https://ris.example.org", "https://alt.example.org"]
