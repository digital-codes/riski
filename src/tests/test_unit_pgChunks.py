"""Unit tests for src.pgChunks — heading-aware chunking + schema helpers
(change: content-chunking)."""

import pytest
from sqlalchemy import create_engine, text

from src import pgChunks as pc

pytestmark = pytest.mark.unit


class TestChunkMarkdown:
    def test_short_document_single_chunk(self):
        text = "# Titel\n\nEin kurzer Absatz."
        chunks = pc.chunk_markdown(text)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 1
        assert chunks[0]["char_start"] == 0
        assert chunks[0]["char_end"] == len(text)
        assert chunks[0]["text"] == text

    def test_empty_document(self):
        assert pc.chunk_markdown("") == []

    def test_large_document_split_at_headings(self):
        # 5 sections à ~3.300 chars -> ~3 chunks (target 7.000); realistic
        # markdown with trailing newlines per line
        section = "# Überschrift {}\n\n" + ("Lorem ipsum Ratstext. \n" * 150)
        text = "".join(section.format(i) for i in range(5))
        chunks = pc.chunk_markdown(text)
        assert len(chunks) >= 2
        # chunks are ordered, contiguous, gapless
        pos = 0
        for i, c in enumerate(chunks, 1):
            assert c["chunk_index"] == i
            assert c["char_start"] == pos
            assert c["text"] == text[c["char_start"]:c["char_end"]]
            pos = c["char_end"]
        assert pos == len(text)
        # every chunk within the hard limit
        assert all(len(c["text"]) <= pc.CHUNK_HARD for c in chunks)

    def test_oversized_section_hard_split(self):
        # single section (one heading) far beyond the hard limit
        text = "# Riesiger Abschnitt\n\n" + ("Zeile mit Inhalt.\n" * 3000)
        chunks = pc.chunk_markdown(text)
        assert len(chunks) >= 2
        assert all(len(c["text"]) <= pc.CHUNK_HARD for c in chunks)
        # coverage: gapless and complete
        pos = 0
        for c in chunks:
            assert c["char_start"] == pos
            pos = c["char_end"]
        assert pos == len(text)

    def test_no_headings_hard_split_by_lines(self):
        text = "Zeile ohne Überschrift.\n" * 2000  # ~48 KB, no '#'
        chunks = pc.chunk_markdown(text)
        assert len(chunks) >= 2
        assert all(len(c["text"]) <= pc.CHUNK_HARD for c in chunks)
        assert "".join(c["text"] for c in chunks) == text

    def test_offsets_are_original_positions(self):
        text = ("# A\n" + "x" * 100 + "\n# B\n" + "y" * 150)
        chunks = pc.chunk_markdown(text, target=50, hard=8000)
        for c in chunks:
            assert text[c["char_start"]:c["char_end"]] == c["text"]

    def test_chunks_start_at_one(self):
        text = "# A\n" + "a" * 200 + "\n# B\n" + "b" * 200
        chunks = pc.chunk_markdown(text, target=100)
        assert [c["chunk_index"] for c in chunks] == list(range(1, len(chunks) + 1))


class TestEnsureTables:
    def test_creates_tables_and_columns(self):
        eng = create_engine("sqlite:///:memory:")
        with eng.begin() as conn:
            conn.execute(text('CREATE TABLE "File" (sid INTEGER PRIMARY KEY, '
                              '"oparlKey" VARCHAR, content TEXT, '
                              '"contentKind" VARCHAR)'))
            conn.execute(text('CREATE TABLE "contentEmbeddings" '
                              '(id INTEGER PRIMARY KEY, "oparlKey" VARCHAR, '
                              'value VARCHAR)'))
        pc.ensure_tables(eng)
        insp = __import__("sqlalchemy").inspect(eng)
        assert "File_chunks" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("File_chunks")}
        assert {"file_sid", "chunk_index", "char_start", "char_end", "text"} <= cols
        emb_cols = {c["name"] for c in insp.get_columns("contentEmbeddings")}
        assert "chunk_index" in emb_cols

    def test_store_and_read_chunks(self):
        eng = create_engine("sqlite:///:memory:")
        with eng.begin() as conn:
            conn.execute(text('CREATE TABLE "File" (sid INTEGER PRIMARY KEY, '
                              '"oparlKey" VARCHAR)'))
            conn.execute(text('INSERT INTO "File" VALUES (1, \'K1\')'))
        pc.ensure_tables(eng)
        chunks = pc.chunk_markdown("# A\n" + "a" * 100 + "\n# B\n" + "b" * 100,
                                   target=50)
        with eng.begin() as conn:
            n = pc.store_chunks(conn, 1, chunks)
            assert n == len(chunks)
            # idempotent: replace, not duplicate
            n = pc.store_chunks(conn, 1, chunks)
            assert n == len(chunks)
        with eng.connect() as conn:
            assert pc.chunk_text(conn, "K1", 1) == chunks[0]["text"]
            assert pc.chunk_text(conn, "K1", None) is None
            assert pc.chunk_text(conn, "UNKNOWN", 1) is None
