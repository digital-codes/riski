"""Unit tests for the chunk-based contentEmbeddings coverage basis
(pgCoverage fix 2026-11-26: the percentage must be of CHUNKS, not of
files — chunked documents made the file-based basis report >100%)."""

import pytest
from sqlalchemy import create_engine, text

from src.update.pgCoverage import coverage

pytestmark = pytest.mark.unit


@pytest.fixture()
def sqlite_engine():
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text(
            'CREATE TABLE "File" (sid int, "oparlKey" text, teaser text)'))
        c.execute(text(
            'CREATE TABLE "File_chunks" (file_sid int, chunk_index int, text text)'))
        # 2 files, 3 chunks (one file chunked into 2) + 1 file without chunks
        c.execute(text(
            "INSERT INTO \"File\" VALUES (1, 'f1', NULL), (2, 'f2', NULL), "
            "(3, 'f3', NULL)"))
        c.execute(text(
            'INSERT INTO "File_chunks" VALUES (1, 0, \'a\'), (1, 1, \'b\'), (2, 0, \'c\')'))
        # embeddings: 2 of the 3 chunks embedded
        c.execute(text(
            'CREATE TABLE contentEmbeddings (id int, "oparlKey" text, '
            'value blob, chunk_index int)'))
        c.execute(text(
            "INSERT INTO contentEmbeddings VALUES (1, 'f1', NULL, 0), (1, 'f1', NULL, 1)"))
    return eng


def test_content_embeddings_percent_is_of_chunks(sqlite_engine, monkeypatch):
    monkeypatch.setattr("src.update.pgCoverage._table_names",
                        lambda conn: {"File", "File_chunks",
                                      "contentEmbeddings"})
    report = coverage(sqlite_engine, item_tables=["File"])
    layers = report["File"]["layers"]
    emb = layers["contentEmbeddings"]
    # 2 embeddings of 3 chunks — 66.7%, NOT 2-of-3-files (66.7 either way?
    # no: the denominator is chunks=3 here; with 500 chunks and 900
    # embeddings the old basis would report >100%)
    assert emb["count"] == 2
    assert emb["denominator"] == 3
    assert emb["pct"] == 66.7


def test_full_chunk_embedding_reports_100_percent(sqlite_engine, monkeypatch):
    with sqlite_engine.begin() as c:
        c.execute(text(
            "INSERT INTO contentEmbeddings VALUES (3, 'f2', NULL, 0)"))
    monkeypatch.setattr("src.update.pgCoverage._table_names",
                        lambda conn: {"File", "File_chunks",
                                      "contentEmbeddings"})
    report = coverage(sqlite_engine, item_tables=["File"])
    emb = report["File"]["layers"]["contentEmbeddings"]
    assert emb == {"count": 3, "denominator": 3, "pct": 100.0}
