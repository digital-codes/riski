"""Unit tests for item history chains (kgChains, no network)."""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.kg.kgChains import build_chains  # noqa: E402
from src.kg.kgStore import KgStore  # noqa: E402


@pytest.fixture
def store():
    import tempfile

    path = os.path.join(tempfile.mkdtemp(), "kg.sqlite")
    s = KgStore(path)
    s.ensure_pre_stage()
    # one paper with 3 pairs; last dated pair has the outcome
    for key, d, o in [
        (("p1", "m2013-11-19"), "2013-11-19", None),
        (("p1", "m2013-12-17"), "2013-12-17", "beschlossen"),
        (("p1", "m2014-01-20"), "2014-01-20", None),
    ]:
        paper_key, meeting_key = key
        s.upsert_pair(
            pair_key=f"{paper_key}|{meeting_key}",
            paper_key=paper_key,
            meeting_key=meeting_key,
            meeting_date=d,
            outcome=o,
        )
    yield s
    s.close()


class TestBuildChains:
    def test_pre_stage_flags_and_links(self, store):
        stats = build_chains(store)
        assert stats["chains"] == 1
        assert stats["pre_stage"] == 2
        assert stats["links"] == 2
        rows = store.paper_pairs("p1")
        assert rows[0]["pre_stage"] == 1 and rows[1]["pre_stage"] == 1
        assert rows[2]["pre_stage"] == 0
        links = store.conn.execute(
            "SELECT prev_pair_key, next_pair_key FROM pair_links ORDER BY next_pair_key"
        ).fetchall()
        assert links[0]["next_pair_key"] == "p1|m2013-12-17"
        assert links[1]["prev_pair_key"] == "p1|m2013-12-17"

    def test_single_pair_paper_unmarked(self, store):
        store.upsert_pair(
            pair_key="p2|m1", paper_key="p2", meeting_key="m1",
        )
        build_chains(store)
        row = store.get_pair("p2|m1")
        assert row["pre_stage"] == 0

    def test_ensure_pre_stage_idempotent(self, store):
        cols1 = [r[1] for r in store.conn.execute("PRAGMA table_info(pairs)")]
        store.ensure_pre_stage()
        cols2 = [r[1] for r in store.conn.execute("PRAGMA table_info(pairs)")]
        assert cols1 == cols2 and "pre_stage" in cols1
