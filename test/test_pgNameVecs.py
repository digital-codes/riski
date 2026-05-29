"""
Tests for NameVecs against a real PostgreSQL database with the vector
extension installed.

The caller must provide:
  DATABASE_URL (default: postgresql://localhost/octest)

A temporary ``test_items`` table is created for each test run.
"""

from __future__ import annotations

import os
import uuid

import numpy as np

# Add ../src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


import pytest
from sqlalchemy import Column, String, Table, create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker

from pgNameVecs import NameVecs

try:
    import private as pr
    DATABASE_URL = f"postgresql+psycopg2://{pr.DB_USER}:{pr.DB_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
except (ImportError, KeyError):
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://localhost/octest"
    )   


EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8085/v1")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3-Q4_K_M")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
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
                tbl.insert().values(
                    id=pk, oparlKey=opk, name=f"item_{pk[:8]}"
                )
            )
        session.commit()
    yield tbl
    with sessionmaker(bind=engine)() as session:
        session.execute(
            text("DROP TABLE IF EXISTS test_items_name_vecs CASCADE")
        )
        session.execute(text("DROP TABLE IF EXISTS test_items CASCADE"))
        session.commit()


@pytest.fixture
def nv(engine, item_table):
    mgr = NameVecs(
        engine,
        "test_items",
        EMBEDDING_URL,
        EMBEDDING_MODEL,
        EMBEDDING_API_KEY or "",
    )
    yield mgr
    with sessionmaker(bind=engine)() as session:
        session.execute(
            text("DROP TABLE IF EXISTS test_items_name_vecs CASCADE")
        )
        session.commit()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestInit:
    def test_table_created(self, engine, item_table):
        nv = NameVecs(
            engine,
            "test_items",
            EMBEDDING_URL,
            EMBEDDING_MODEL,
            EMBEDDING_API_KEY or "",
        )
        assert nv._table_exists("test_items_name_vecs")

    def test_raises_on_missing_item_table(self, engine):
        with pytest.raises(ValueError, match="does not exist"):
            NameVecs(
                engine,
                "nonexistent",
                EMBEDDING_URL,
                EMBEDDING_MODEL,
                EMBEDDING_API_KEY or "",
            )


class TestUpsert:
    def test_insert_new(self, nv: NameVecs):
        key = "oparl:test-insert-001"
        nv.upsert(key, "hello world")
        with nv._session_factory() as session:
            row = session.execute(
                nv._vec_table.select().where(
                    nv._vec_table.c.oparl_key == key
                )
            ).first()
        assert row is not None
        assert row.oparl_key == key

    def test_update_existing(self, nv: NameVecs):
        key = "oparl:test-update-001"
        nv.upsert(key, "first text")
        nv.upsert(key, "second text")
        with nv._session_factory() as session:
            row = session.execute(
                nv._vec_table.select().where(
                    nv._vec_table.c.oparl_key == key
                )
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
                nv._vec_table.select().where(
                    nv._vec_table.c.oparl_key == key
                )
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

    def test_cutoff_filters_low(self, nv: NameVecs):
        nv.upsert("oparl:cut-a", "Python is great")
        nv.upsert("oparl:cut-b", "quantum chromodynamics")
        results = nv.find_similar("python programming", k=5, cutoff=0.95)
        assert len(results) == 0

    def test_no_vectors_returns_empty(self, nv: NameVecs):
        results = nv.find_similar("anything", k=5, cutoff=0.0)
        assert results == []


class TestEmbed:
    def test_embed_returns_normalized(self, nv: NameVecs):
        sample = "test"
        try:
            vec = nv._embed(sample)
        except Exception:
            vec = None
        assert vec is not None
        assert vec.shape == (NameVecs.DIM,)
        assert np.abs(np.linalg.norm(vec) - 1.0) < 1e-5


class TestIntegration:
    def test_full_workflow(self, nv: NameVecs):
        docs = {
            "oparl:int-1": "machine learning algorithms",
            "oparl:int-2": "deep neural networks",
            "oparl:int-3": "database indexing techniques",
            "oparl:int-4": "natural language processing",
        }
        for k, t in docs.items():
            nv.upsert(k, t)

        res = nv.find_similar("neural networks", k=2, cutoff=0.0)
        assert len(res) == 2
        top_key = res[0][0]
        assert top_key == "oparl:int-2"

        nv.remove("oparl:int-3")
        res2 = nv.find_similar("indexing", k=5, cutoff=0.0)
        assert "oparl:int-3" not in [r[0] for r in res2]
