"""Tests for src.update.pgAddSummaries / src.update.pgAddNameVectors.

Unit part: pure helpers with tmp directories and a mocked embed.
Integration part: run() against ``test_*`` tables on the live database.
"""

import os
from pathlib import Path

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, UniqueConstraint, text, create_engine
from sqlalchemy.orm import declarative_base

from src import db, remote
from src.update.pgAddSummaries import iter_md_files, normalize_file_basename, run as run_summaries
from src.update.pgAddNameVectors import run as run_vectors

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Unit tests (pure helpers)
# ---------------------------------------------------------------------------


class TestNormalizeFileBasename:
    def test_strips_extension(self):
        assert normalize_file_basename("00123456.md") == "00123456"

    def test_none_returns_none(self):
        assert normalize_file_basename(None) is None

    def test_empty_returns_none(self):
        assert normalize_file_basename("") is None

    def test_plain_name_without_extension(self):
        assert normalize_file_basename("doc") == "doc"


class TestIterMdFiles:
    def test_maps_stems(self, tmp_path):
        sums = tmp_path / "sums"
        full = tmp_path / "full"
        sums.mkdir()
        full.mkdir()
        (sums / "a.md").write_text("summary a" * 100)
        (full / "a.md").write_text("original a")
        md_map = iter_md_files(sums, full)
        assert set(md_map.keys()) == {"a"}
        # full file is < 3000 bytes and < 2x sums size -> full preferred
        assert md_map["a"] == full / "a.md"

    def test_prefers_sums_when_full_too_big(self, tmp_path):
        sums = tmp_path / "sums"
        full = tmp_path / "full"
        sums.mkdir()
        full.mkdir()
        (sums / "b.md").write_text("s")
        (full / "b.md").write_text("x" * 5000)  # >= 3000 bytes
        md_map = iter_md_files(sums, full)
        assert md_map["b"] == sums / "b.md"

    def test_missing_full_uses_sums(self, tmp_path):
        sums = tmp_path / "sums"
        sums.mkdir()
        (sums / "c.md").write_text("s")
        md_map = iter_md_files(sums, tmp_path / "does-not-exist")
        assert md_map["c"] == sums / "c.md"


# ---------------------------------------------------------------------------
# Integration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine():
    if os.getenv("RW_USER") and os.getenv("RW_PWD"):
        url = db.build_url(
            os.environ["RW_USER"], os.environ["RW_PWD"], db.DB_HOST, db.DB_NAME
        )
        eng = db.get_engine(url=url)
    else:
        eng = db.get_engine()
    yield eng
    eng.dispose()


@pytest.fixture()
def file_tbl(engine):
    metadata = MetaData()
    tbl = Table(
        "test_files",
        metadata,
        Column("sid", Integer, primary_key=True),
        Column("oparlKey", String(255)),
        Column("filename", String(500)),
        Column("content", Text),
        Column("contentKind", String(16)),
    )
    metadata.create_all(engine, checkfirst=True)
    yield tbl
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_files CASCADE"))


@pytest.fixture()
def seeded_files(engine, file_tbl, tmp_path):
    """Seed two files: one with a matching md, one without."""
    md_dir = tmp_path / "mds"
    md_dir.mkdir()
    (md_dir / "report1.md").write_text("# Bericht eins\n" + "Text " * 50, encoding="utf-8")
    (md_dir / "orphan.md").write_text("orphan", encoding="utf-8")

    with engine.begin() as conn:
        conn.execute(file_tbl.insert().values(sid=1, oparlKey="f1", filename="report1.md", content=None))
        conn.execute(file_tbl.insert().values(sid=2, oparlKey="f2", filename="missing.md", content=None))
        conn.execute(file_tbl.insert().values(sid=3, oparlKey="f3", filename=None, content=None))
    return md_dir


class TestRunContentLoading:
    def test_updates_matched_and_reports_unmatched(self, engine, file_tbl, seeded_files):
        md_map = iter_md_files(seeded_files, seeded_files)
        with engine.begin() as conn:
            run_summaries(conn, file_tbl, md_map, embeddings=False, dry_run=False)

        with engine.connect() as conn:
            contents = dict(conn.execute(
                __import__("sqlalchemy").select(file_tbl.c.sid, file_tbl.c.content)
            ).fetchall())
        assert contents[1] and "Bericht eins" in contents[1]
        assert contents[2] is None  # no matching md
        assert contents[3] is None  # no filename

    def test_dry_run_does_not_write(self, engine, file_tbl, seeded_files):
        md_map = iter_md_files(seeded_files, seeded_files)
        with engine.begin() as conn:
            run_summaries(conn, file_tbl, md_map, embeddings=False, dry_run=True)
        with engine.connect() as conn:
            from sqlalchemy import select as sel

            contents = dict(conn.execute(sel(file_tbl.c.sid, file_tbl.c.content)).fetchall())
        assert all(c is None for c in contents.values())

    def test_content_kind_provenance(self, engine, file_tbl, tmp_path):
        sums = tmp_path / "sums"
        full = tmp_path / "full"
        sums.mkdir()
        full.mkdir()
        # Same stem in both dirs: small full copy wins over the summary.
        (sums / "doc.md").write_text("S" * 5000, encoding="utf-8")
        (full / "doc.md").write_text("full text", encoding="utf-8")
        # Stem only in sums: LLM summary.
        (sums / "only_sum.md").write_text("summary only", encoding="utf-8")
        with engine.begin() as conn:
            conn.execute(file_tbl.insert().values(sid=10, oparlKey="k_sum", filename="only_sum.md"))
            conn.execute(file_tbl.insert().values(sid=11, oparlKey="k_full", filename="doc.md"))

        md_map = iter_md_files(sums, full)
        with engine.begin() as conn:
            run_summaries(conn, file_tbl, md_map, embeddings=False, dry_run=False,
                          sums_dir=sums, full_dir=full)

        with engine.connect() as conn:
            from sqlalchemy import select as sel
            kinds = dict(conn.execute(sel(file_tbl.c.sid, file_tbl.c.contentKind)).fetchall())
        assert kinds[10] == "summary"
        assert kinds[11] == "fulltext"


class TestRunEmbeddings:
    def test_vectors_upserted_not_duplicated(self, engine, file_tbl, seeded_files, monkeypatch):
        import numpy as np

        Base_test = declarative_base()

        class TestEmbedding(Base_test):
            __tablename__ = "test_embeddings"
            id = Column(Integer, primary_key=True)
            oparlKey = Column(String)
            value = Column(Vector(4))
            __table_args__ = (UniqueConstraint("oparlKey", name="uq_test_embedding"),)

        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_embeddings CASCADE"))
        Base_test.metadata.create_all(engine)

        calls = {"n": 0}

        def fake_embed(txt):
            calls["n"] += 1
            v = np.ones(4, dtype=np.float64) * calls["n"]
            return v / np.linalg.norm(v)

        monkeypatch.setattr("src.update.pgAddNameVectors.remote.embed", fake_embed)

        md_map = iter_md_files(seeded_files, seeded_files)
        with engine.begin() as conn:
            run_vectors(conn, file_tbl, md_map, embeddings=True, dry_run=False,
                        embedding_model=TestEmbedding)

        from sqlalchemy import select as sel

        with engine.connect() as conn:
            rows = conn.execute(sel(TestEmbedding.__table__.c.oparlKey)).fetchall()
        # exactly one embedding for the one matched file
        assert [r[0] for r in rows] == ["f1"]

        # re-run: upsert replaces, no duplicates
        with engine.begin() as conn:
            run_vectors(conn, file_tbl, md_map, embeddings=True, dry_run=False,
                        embedding_model=TestEmbedding)
        with engine.connect() as conn:
            rows = conn.execute(sel(TestEmbedding.__table__.c.oparlKey)).fetchall()
        assert [r[0] for r in rows] == ["f1"]

        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_embeddings CASCADE"))


class TestEmbedWrapper:
    def test_embed_uses_shared_client(self, monkeypatch):
        import numpy as np

        captured = {}

        def fake_embed(t):
            captured["t"] = t
            return np.array([1.0, 0.0])

        monkeypatch.setattr(remote, "embed", fake_embed)
        from src.update.pgAddSummaries import embed as s_embed

        vec = s_embed("hello")
        assert captured["t"] == "hello"
        assert vec[0] == 1.0


class TestPgAddVecsRebuild:
    def test_rebuild_from_npz(self, engine, tmp_path):
        import numpy as np
        from pgvector.sqlalchemy import Vector as V

        from src import pgAddVecs

        Base_v = declarative_base()

        class TestVecs(Base_v):
            __tablename__ = "test_vec_rebuild"
            id = Column(Integer, primary_key=True)
            oparlKey = Column(String)
            value = Column(V(4))

        npz = tmp_path / "vecs.npz"
        vecs = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        files = np.array([101, 102])
        np.savez(npz, vectors=vecs, files=files)

        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_vec_rebuild CASCADE"))

        # first rebuild creates the table and inserts rows
        n = pgAddVecs.rebuild(str(npz), engine=engine, embedding_model=TestVecs)
        assert n == 2
        rows = conn = None
        with engine.connect() as conn:
            rows = conn.execute(text('SELECT "oparlKey" FROM test_vec_rebuild ORDER BY "oparlKey"')).fetchall()
        assert [r[0] for r in rows] == ["101", "102"]

        # rebuild is a drop+recreate: row count stays 2, not 4
        n = pgAddVecs.rebuild(str(npz), engine=engine, embedding_model=TestVecs)
        assert n == 2
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM test_vec_rebuild")).scalar()
        assert count == 2

        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_vec_rebuild CASCADE"))
