"""Integration tests for content chunking (change: content-chunking).

Runs against the live database but is non-destructive: one real oversized
document is processed through the loader chunk path, verified, and the
original state is restored afterwards. Embeddings are stubbed with
deterministic vectors except where noted (one real query embedding).
"""

import os

import pytest
from sqlalchemy import text

from src import pgAddSummaries as pas
from src import pgChunks as pc
from src.db import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture()
def oversized():
    """A real oversized markdown file + its File row + the original state."""
    directory = "/mnt_ai/data/odd26/ris/ko_extracted"
    engine = get_engine()
    with engine.connect() as conn:
        for fn in sorted(os.listdir(directory)):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(directory, fn)
            if os.path.getsize(path) <= pc.SIZE_CUTOFF:
                continue
            stem = fn[:-3]
            row = conn.execute(text(
                'SELECT sid, "oparlKey", filename, content, "contentKind" '
                'FROM "File" WHERE filename LIKE :f LIMIT 1'),
                {"f": stem + ".%"}).first()
            if row is None:
                continue
            orig = {"sid": row.sid, "oparlKey": row.oparlKey,
                    "content": row.content, "kind": row.contentKind}
            # original embedding state (legacy single vector?)
            orig_emb = [tuple(r) for r in conn.execute(text(
                'SELECT chunk_index, id FROM "contentEmbeddings" '
                'WHERE "oparlKey" = :k'), {"k": row.oparlKey}).fetchall()]
            return {"stem": stem, "path": path, "engine": engine,
                    "file": dict(row._mapping) if hasattr(row, "_mapping") else dict(row._asdict()) if hasattr(row, "_asdict") else {"sid": row.sid, "oparlKey": row.oparlKey, "content": row.content, "contentKind": row.contentKind},
                    "orig": orig, "orig_emb": orig_emb}
    pytest.skip("no oversized markdown with File row found")


@pytest.fixture()
def stub_embed(monkeypatch):
    """Deterministic 1024-dim vectors derived from the text (offline)."""
    import numpy as np

    def fake_embed(text: str, model=None, dimensions=None):
        v = np.zeros(1024)
        for i, ch in enumerate(text[:1024].encode("utf-8")):
            v[i % 1024] += float(ch) / 255.0
        n = float(np.linalg.norm(v)) or 1.0
        return v / n

    monkeypatch.setattr(pas, "embed", fake_embed)
    return fake_embed


class TestLoaderChunkPath:
    def test_oversized_document_chunked_no_llm(self, oversized, stub_embed, monkeypatch):
        engine = oversized["engine"]
        key = oversized["orig"]["oparlKey"]
        sid = oversized["orig"]["sid"]
        pc.ensure_tables(engine)

        md_map = {oversized["stem"]: oversized["path"]}
        metadata = __import__("sqlalchemy").MetaData()
        file_tbl = __import__("sqlalchemy").Table(
            "File", metadata, autoload_with=engine)

        conn = engine.connect()
        try:
            # snapshot the legacy vector for restore
            pas.run(conn, file_tbl, md_map, embeddings=True,
                    sums_dir=None, full_dir=__import__("pathlib").Path(os.path.dirname(oversized["path"])))
            conn.commit()  # run() leaves the commit to the caller (engine.begin in main)

            with engine.connect() as check:
                kind = check.execute(text(
                    'SELECT "contentKind" FROM "File" WHERE sid = :s'),
                    {"s": sid}).scalar()
                assert kind == "chunked"
                content = check.execute(text(
                    'SELECT content FROM "File" WHERE sid = :s'), {"s": sid}).scalar()
                chunks = check.execute(text(
                    'SELECT chunk_index, char_start, char_end, text '
                    'FROM "File_chunks" WHERE file_sid = :s ORDER BY chunk_index'),
                    {"s": sid}).fetchall()
                assert chunks, "no chunks stored"
                assert content == chunks[0].text  # head = first chunk
                vecs = check.execute(text(
                    'SELECT chunk_index FROM "contentEmbeddings" '
                    'WHERE "oparlKey" = :k ORDER BY chunk_index'), {"k": key}).fetchall()
                assert [v[0] for v in vecs] == [c.chunk_index for c in chunks]
                # legacy vector replaced
                assert 0 not in [v[0] for v in vecs]
                # chunk text helper (reranker input)
                assert pc.chunk_text(check, key, chunks[0].chunk_index) == chunks[0].text

            # idempotent re-run: no duplicates
            pas.run(conn, file_tbl, md_map, embeddings=True,
                    sums_dir=None, full_dir=__import__("pathlib").Path(os.path.dirname(oversized["path"])))
            conn.commit()  # run() leaves the commit to the caller (engine.begin in main)
            with engine.connect() as check:
                n = check.execute(text(
                    'SELECT count(*) FROM "File_chunks" WHERE file_sid = :s'),
                    {"s": sid}).scalar()
                assert n == len(chunks)
        finally:
            conn.close()
            # restore original state
            with engine.begin() as back:
                back.execute(text('DELETE FROM "File_chunks" WHERE file_sid = :s'),
                             {"s": sid})
                back.execute(text('DELETE FROM "contentEmbeddings" WHERE "oparlKey" = :k'),
                             {"k": key})
                for idx, _id in oversized["orig_emb"]:
                    back.execute(text(
                        'INSERT INTO "contentEmbeddings" ("oparlKey", chunk_index, id) '
                        'VALUES (:k, :i, :id)'), {"k": key, "i": idx, "id": _id})
                back.execute(text(
                    'UPDATE "File" SET content = :c, "contentKind" = :k2 '
                    'WHERE sid = :s'), {"c": oversized["orig"]["content"],
                                        "k2": oversized["orig"]["kind"], "s": sid})
