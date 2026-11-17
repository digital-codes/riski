"""Unit tests for the kg prototype store and status ticker (no network)."""

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.kg.kgStore import KgStore  # noqa: E402
from src.kg.kgStatus import StatusTicker  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = KgStore(str(tmp_path / "kg.sqlite"))
    yield s
    s.close()


class TestKgStore:
    def test_pair_upsert_and_resume(self, store):
        store.upsert_pair(
            pair_key="p1|m1",
            paper_key="p1",
            meeting_key="m1",
            meeting_date="2026-01-15",
            signal="db-column",
            confidence=1.0,
        )
        # identical + partial re-run must not duplicate or clobber
        store.upsert_pair(
            pair_key="p1|m1",
            paper_key="p1",
            meeting_key="m1",
            outcome="zugestimmt",
        )
        row = store.get_pair("p1|m1")
        assert row["meeting_date"] == "2026-01-15"  # preserved
        assert row["outcome"] == "zugestimmt"  # enriched
        assert row["status"] == "identified"
        assert store.pair_counts_by_status() == {"identified": 1}

    def test_status_transition_and_query(self, store):
        store.upsert_pair(pair_key="a|m", paper_key="a", meeting_key="m")
        store.set_pair_status("a|m", "statements")
        assert [r["pair_key"] for r in store.pairs_by_status("statements")] == ["a|m"]

    def test_documents_round_trip(self, store):
        store.upsert_pair(pair_key="p|m", paper_key="p", meeting_key="m")
        store.upsert_document(
            "p|m", {"doc_key": "f1", "doc_id": "42", "filename": "42.pdf", "role": "request"}
        )
        store.upsert_document(
            "p|m", {"doc_key": "f1", "filename": "42.pdf"}  # partial re-run
        )
        docs = store.documents_for_pair("p|m")
        assert len(docs) == 1
        assert docs[0]["doc_id"] == "42" and docs[0]["role"] == "request"
        assert docs[0]["name"] is None

    def test_file_meta_chunk_distribution(self, store):
        for i, cc in enumerate([1, 3, 5, 8, 12]):
            store.upsert_file_meta(f"p{i}|m", f"d{i}", cc)
        dist = store.chunk_distribution()
        assert dist == {"<=5": 3, ">5": 2}

    def test_tags_and_file_tags_upsert(self, store):
        store.upsert_tag("Mobility", "Verkehrs- und Mobilitätsthemen")
        store.upsert_tag("Mobility", "Neuformulierung")  # re-seed updates desc
        assert store.tags()[0]["description"] == "Neuformulierung"
        store.upsert_file_tag("d1", "Mobility", 0.9, None, "llm")
        store.upsert_file_tag("d1", "Mobility", 0.8, "Sanierung", "llm")
        rows = store.conn.execute("SELECT * FROM file_tags").fetchall()
        assert len(rows) == 1 and rows[0]["qualifier"] == "Sanierung"

    def test_statements_and_crosscheck(self, store):
        store.upsert_statement("p|m", "request", None, '{"topic": "x"}')
        store.upsert_statement("p|m", "request", None, '{"topic": "y"}')
        rows = store.conn.execute("SELECT * FROM statements").fetchall()
        assert len(rows) == 1 and '"y"' in rows[0]["fields_json"]
        store.upsert_crosscheck("p|m", "failed", "wrong executor")
        store.upsert_crosscheck("p|m", "passed", None)
        assert store.conn.execute("SELECT COUNT(*) FROM crosschecks").fetchone()[0] == 1


class TestStatusTicker:
    def test_force_and_interval(self, tmp_path):
        import time

        path = tmp_path / "out.txt"
        with open(path, "w") as fh:
            t = StatusTicker(interval=10.0, stream=fh)
            assert t.tick("one") is True  # fresh ticker prints immediately
            assert t.tick("two") is False  # immediately after
            t2 = StatusTicker(interval=0.01, stream=fh)
            t2.section("identify")  # forces next tick even so
            assert t2.tick("three") is True
            assert t2.tick("three") is False
            time.sleep(0.02)
            assert t2.tick("four") is True
            t.section("identify")
        content = path.read_text()
        assert "one" in content
        assert "two" not in content
        assert "four" in content and "identify" in content
