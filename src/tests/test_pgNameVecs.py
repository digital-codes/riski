"""
Tests for the refactored NameVecs (src.update.pgNameVecs).

Unit part: embeddings are mocked (no network, no live endpoint needed).
Integration part: runs against the live DB and embedding endpoint, only
touching ``test_*`` tables.
"""

from __future__ import annotations

import os
import uuid

import numpy as np
import pytest
from sqlalchemy import Column, MetaData, String, Table, text
from sqlalchemy.orm import sessionmaker

from src import db
from src.update.pgNameVecs import NameVecs

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine():
    if os.getenv("RW_USER") and os.getenv("RW_PWD"):
        url = db.build_url(
            os.environ["RW_USER"],
            os.environ["RW_PWD"],
            db.DB_HOST,
            db.DB_NAME,
        )
        eng = db.get_engine(url=url)
    else:
        eng = db.get_engine()
    yield eng
    eng.dispose()


@pytest.fixture()
def item_table(engine):
    meta = MetaData()
    tbl = Table(
        "test_items",
        meta,
        Column("id", String(36), primary_key=True),
        Column("oparlKey", String(500), nullable=False),
        Column("name", String(200)),
    )
    meta.create_all(engine, checkfirst=True)
    with sessionmaker(bind=engine)() as session:
        for _ in range(10):
            pk = str(uuid.uuid4())
            opk = f"oparl:{uuid.uuid4().hex[:12]}"
            session.execute(
                tbl.insert().values(id=pk, oparlKey=opk, name=f"item_{pk[:8]}")
            )
        session.commit()
    yield tbl
    with sessionmaker(bind=engine)() as session:
        session.execute(text("DROP TABLE IF EXISTS test_items_name_vecs CASCADE"))
        session.execute(text("DROP TABLE IF EXISTS test_items CASCADE"))
        session.commit()


def _fake_embed(monkeypatch, dim=1024, seed=0):
    """Patch src.update.pgNameVecs.embed with a deterministic pseudo-embedding."""
    import hashlib

    def _embed(text: str, **kwargs):
        digest = hashlib.sha256(f"{seed}:{text}".encode()).digest()
        vec = np.frombuffer(digest * (dim // len(digest) + 1), dtype=np.uint8)[:dim]
        vec = vec.astype(np.float64) / 255.0
        return vec / (np.linalg.norm(vec) + 1e-9)

    monkeypatch.setattr("src.update.pgNameVecs.embed", _embed)
    return _embed


@pytest.fixture()
def nv(engine, item_table, monkeypatch):
    _fake_embed(monkeypatch)
    mgr = NameVecs("test_items", engine=engine)
    yield mgr
    with sessionmaker(bind=engine)() as session:
        session.execute(text("DROP TABLE IF EXISTS test_items_name_vecs CASCADE"))
        session.commit()


def _table_exists(engine, name: str) -> bool:
    from sqlalchemy import inspect

    with engine.connect() as conn:
        return inspect(conn).has_table(name)


# ---------------------------------------------------------------------------
# Unit tests (mocked embeddings)
# ---------------------------------------------------------------------------


class TestInit:
    def test_table_created(self, engine, item_table, monkeypatch):
        _fake_embed(monkeypatch)
        nv = NameVecs("test_items", engine=engine)
        assert _table_exists(engine, "test_items_name_vecs")

    def test_raises_on_missing_item_table(self, engine, monkeypatch):
        _fake_embed(monkeypatch)
        with pytest.raises(ValueError, match="does not exist"):
            NameVecs("nonexistent", engine=engine)


class TestUpsert:
    def test_insert_new(self, nv: NameVecs):
        key = "oparl:test-insert-001"
        nv.upsert(key, "hello world")
        with nv._session_factory() as session:
            row = session.execute(
                nv._vec_table.select().where(nv._vec_table.c.oparl_key == key)
            ).first()
        assert row is not None
        assert row.oparl_key == key

    def test_update_existing(self, nv: NameVecs):
        key = "oparl:test-update-001"
        nv.upsert(key, "first text")
        nv.upsert(key, "second text")
        with nv._session_factory() as session:
            row = session.execute(
                nv._vec_table.select().where(nv._vec_table.c.oparl_key == key)
            ).first()
        assert row is not None
        vals = np.array(row.embedding, dtype=np.float64)
        assert np.abs(np.linalg.norm(vals) - 1.0) < 1e-5


class TestRemove:
    def test_remove_existing(self, nv: NameVecs):
        key = "oparl:test-remove-001"
        nv.upsert(key, "to be removed")
        nv.remove(key)
        with nv._session_factory() as session:
            row = session.execute(
                nv._vec_table.select().where(nv._vec_table.c.oparl_key == key)
            ).first()
        assert row is None

    def test_remove_nonexistent(self, nv: NameVecs):
        nv.remove("oparl:does-not-exist")


class TestFindSimilar:
    def test_similarity_returns_results(self, nv: NameVecs):
        nv.upsert("oparl:sim-a", "Python programming language")
        nv.upsert("oparl:sim-b", "Java virtual machine")
        nv.upsert("oparl:sim-c", "quantum physics")
        results = nv.find_similar("python coding", k=2, cutoff=0.0)
        assert len(results) <= 2
        keys = [r[0] for r in results]
        assert "oparl:sim-a" in keys

    def test_sorted_by_similarity_desc(self, nv: NameVecs):
        nv.upsert("oparl:sort-a", "Python programming")
        nv.upsert("oparl:sort-b", "Java programming")
        nv.upsert("oparl:sort-c", "Rust programming")
        nv.upsert("oparl:sort-d", "Haskell programming")
        results = nv.find_similar("python", k=5, cutoff=0.0)
        sims = [r[1] for r in results]
        assert sims == sorted(sims, reverse=True)

    def test_self_is_best_match(self, nv: NameVecs):
        nv.upsert("oparl:self-1", "municipal committee")
        nv.upsert("oparl:self-2", "budget planning")
        results = nv.find_similar("municipal committee", k=2, cutoff=0.0)
        assert results[0][0] == "oparl:self-1"

    def test_cutoff_filters_low(self, nv: NameVecs):
        nv.upsert("oparl:cut-a", "Python is great")
        nv.upsert("oparl:cut-b", "quantum chromodynamics")
        results = nv.find_similar("python programming", k=5, cutoff=0.95)
        assert len(results) == 0

    def test_no_vectors_returns_empty(self, nv: NameVecs):
        results = nv.find_similar("anything", k=5, cutoff=0.0)
        assert results == []


class TestIntegration:
    """End-to-end with the real embedding endpoint."""

    @pytest.fixture()
    def live_nv(self, engine, item_table, monkeypatch):
        try:
            from src import remote

            remote.embed("connectivity probe")
        except Exception as e:
            pytest.skip(f"live embedding endpoint unavailable: {e}")
        mgr = NameVecs("test_items", engine=engine)
        yield mgr
        with sessionmaker(bind=engine)() as session:
            session.execute(text("DROP TABLE IF EXISTS test_items_name_vecs CASCADE"))
            session.commit()

    def test_full_workflow(self, live_nv: NameVecs):
        docs = {
            "oparl:int-1": "machine learning algorithms",
            "oparl:int-2": "deep neural networks",
            "oparl:int-3": "database indexing techniques",
            "oparl:int-4": "natural language processing",
        }
        for k, t in docs.items():
            live_nv.upsert(k, t)

        res = live_nv.find_similar("neural networks", k=2, cutoff=0.0)
        assert len(res) == 2
        top_key = res[0][0]
        assert top_key == "oparl:int-2"

        live_nv.remove("oparl:int-3")
        res2 = live_nv.find_similar("indexing", k=5, cutoff=0.0)
        assert "oparl:int-3" not in [r[0] for r in res2]

pytestmark = pytest.mark.unit
