"""Parity harness: concurrent hybrid recall must produce results identical
to the sequential path (change: api-latency-optimization, task 1.3)."""

from __future__ import annotations

import pytest

from src.search.pgHybridSearch import hybrid_candidates

pytestmark = pytest.mark.integration

# real queries over the live Karlsruhe RIS data
_QUERIES = [
    "Theatersanierung",
    "Rückbau der Herrenalber Straße",
    "Digitalstrategie der Stadt Karlsruhe",
    "Radweg Terrainkurweg",
]

# signal-toggle variants exercised across the queries
_SIGNAL_VARIANTS = [
    {"lexical": True, "name_vectors": True, "content_vectors": True},
    {"lexical": True, "name_vectors": False, "content_vectors": False},
    {"lexical": False, "name_vectors": True, "content_vectors": True},
]


@pytest.fixture(scope="module")
def conn():
    from src.db import get_engine

    engine = get_engine(readonly=True)
    with engine.connect() as c:
        yield c


@pytest.mark.parametrize("query,signals", [
    (q, s) for i, q in enumerate(_QUERIES) for s in [_SIGNAL_VARIANTS[i % len(_SIGNAL_VARIANTS)]]
])
def test_concurrent_matches_sequential(conn, query, signals, monkeypatch):
    fake = [0.01] * 1024  # name_vecs absent/empty environments still work

    monkeypatch.setenv("RISKI_PARALLEL_SIGNALS", "0")
    sequential = hybrid_candidates(
        conn, query, fake, top_k=10, signals=signals,
    )
    monkeypatch.setenv("RISKI_PARALLEL_SIGNALS", "1")
    concurrent = hybrid_candidates(
        conn, query, fake, top_k=10, signals=signals,
    )

    assert concurrent["matched_entities"] == sequential["matched_entities"]
    assert concurrent["file_candidates"] == sequential["file_candidates"]
    if sequential["file_candidates"]:
        assert concurrent["file_candidates"]  # sanity: not both empty
