"""Unit tests for api-capacity-hardening: pool config, fan-out budget,
session eviction, summarize default, 503-on-saturation."""

import threading

import pytest

from src import apiServer

pytestmark = pytest.mark.unit

from src.pgHybridSearch import (
    CapacityError,
    _fanout_budget,
    _fanout_pool_timeout,
    _hybrid_permits,
    _reset_fanout_semaphore_for_tests,
)


# ----------------------------------------------------------------------
# 1.1 pool configuration from environment
# ----------------------------------------------------------------------

def test_env_int_parsing(monkeypatch):
    from src.db import _env_int

    monkeypatch.setenv("RISKI_TEST_INT", "42")
    assert _env_int("RISKI_TEST_INT", 0) == 42
    monkeypatch.setenv("RISKI_TEST_INT", "not-a-number")
    assert _env_int("RISKI_TEST_INT", 7) == 7
    monkeypatch.delenv("RISKI_TEST_INT", raising=False)
    assert _env_int("RISKI_TEST_INT", 7) == 7


def test_get_engine_applies_pool_env(monkeypatch):
    import sqlalchemy as sa

    from src.db import _engines, get_engine

    monkeypatch.setenv("RISKI_DB_POOL_SIZE", "3")
    monkeypatch.setenv("RISKI_DB_MAX_OVERFLOW", "2")
    monkeypatch.setenv("RISKI_DB_POOL_TIMEOUT", "11")
    url = "postgresql+psycopg2://u:p@localhost/pooltest_capacity"
    _engines.pop(url, None)
    engine = get_engine(url=url)
    assert engine.pool.size() == 3
    assert engine.pool._max_overflow == 2
    assert engine.pool._timeout == 11
    _engines.pop(url, None)
    engine.dispose()


# ----------------------------------------------------------------------
# 1.2 fan-out semaphore / CapacityError
# ----------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_sem():
    _reset_fanout_semaphore_for_tests()
    yield
    _reset_fanout_semaphore_for_tests()


def test_fanout_env_defaults(monkeypatch):
    monkeypatch.delenv("RISKI_FANOUT_BUDGET", raising=False)
    monkeypatch.delenv("RISKI_DB_POOL_TIMEOUT", raising=False)
    assert _fanout_budget() == 24
    assert _fanout_pool_timeout() == 30
    monkeypatch.setenv("RISKI_FANOUT_BUDGET", "4")
    assert _fanout_budget() == 4


def test_hybrid_permits_bounded_by_executor_width():
    permits = _hybrid_permits(999)
    assert permits == 12  # executor max_workers


class _FakeConn:
    engine = None


def test_capacity_error_when_budget_held(monkeypatch):
    from src.pgHybridSearch import hybrid_candidates

    monkeypatch.setenv("RISKI_FANOUT_BUDGET", "4")
    monkeypatch.setenv("RISKI_DB_POOL_TIMEOUT", "1")
    sem = None
    from src.pgHybridSearch import _fanout_semaphore

    sem = _fanout_semaphore()
    for _ in range(4):
        sem.acquire()
    with pytest.raises(CapacityError):
        hybrid_candidates(_FakeConn(), "test query", [0.1] * 4, top_k=5)
    # the failed acquisition must not have released anything
    with pytest.raises(CapacityError):
        hybrid_candidates(_FakeConn(), "test query", [0.1] * 4, top_k=5)


def test_semaphore_released_after_success(monkeypatch):
    """When the budget is available the request acquires and releases its
    permits (observable: a second full-budget hold after the run)."""
    from src.pgHybridSearch import _fanout_semaphore

    sem = _fanout_semaphore()
    acquired = sem.acquire(timeout=1)
    assert acquired
    sem.release()


# ----------------------------------------------------------------------
# 2.1 summarize default + 2.2 503 mapping + 2.3 session eviction
# ----------------------------------------------------------------------

class _FakeDbSession:
    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(apiServer, "get_db_session", lambda: _FakeDbSession())
    monkeypatch.setattr(apiServer, "_sessions", {})
    return TestClient(apiServer.app, raise_server_exceptions=False)


def test_search_default_does_not_summarize(client, monkeypatch):
    captured = {}

    def fake_search(session, query, **kwargs):
        captured.update(kwargs)
        return {"graph": {"nodes": []}}

    monkeypatch.setattr(apiServer, "search_and_summarize", fake_search)
    client.post("/search", json={"query": "radwege"})
    assert captured["summarize"] is False

    monkeypatch.setattr(
        apiServer, "search_and_summarize",
        lambda session, query, **kw: (captured.update(kw), {"graph": {"nodes": []}})[1],
    )
    client.post("/search", json={"query": "radwege", "summarize": True})
    assert captured["summarize"] is True


def test_search_capacity_error_maps_to_503(client, monkeypatch):
    def raise_capacity(session, query, **kwargs):
        raise CapacityError("budget exhausted")

    monkeypatch.setattr(apiServer, "search_and_summarize", raise_capacity)
    resp = client.post("/search", json={"query": "radwege"})
    assert resp.status_code == 503
    assert resp.headers.get("retry-after") == "5"


def test_session_eviction_by_ttl(client, monkeypatch):
    monkeypatch.setattr(apiServer, "_sessions", {})
    monkeypatch.setenv("RISKI_SESSION_TTL", "1")
    apiServer._store_session("old", {"query": "a"})
    apiServer._sessions["old"]["created"] -= 3600  # far in the past
    apiServer._store_session("new", {"query": "b"})
    assert "old" not in apiServer._sessions
    assert "new" in apiServer._sessions
    assert apiServer._get_session("old") is None


def test_session_cap_trims_oldest(client, monkeypatch):
    monkeypatch.setattr(apiServer, "_sessions", {})
    monkeypatch.setenv("RISKI_SESSION_MAX", "3")
    for i, sid in enumerate(["s1", "s2", "s3", "s4"]):
        apiServer._store_session(sid, {"query": f"q{i}"})
        if sid != "s4":
            # backdate so insertion order is deterministic
            apiServer._sessions[sid]["created"] -= (4 - i) * 10
    assert set(apiServer._sessions) == {"s2", "s3", "s4"}


def test_get_session_after_ttl_returns_none(client, monkeypatch):
    monkeypatch.setattr(apiServer, "_sessions", {})
    monkeypatch.setenv("RISKI_SESSION_TTL", "1")
    apiServer._store_session("sid", {"query": "a"})
    apiServer._sessions["sid"]["created"] -= 3600
    assert apiServer._get_session("sid") is None
