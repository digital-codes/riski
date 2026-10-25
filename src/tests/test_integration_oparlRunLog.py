"""Integration tests for src.update.oparlRunLog against the live database.

All verification writes happen inside a transaction that is **rolled back**
at test end (design D7) - the production tables stay untouched except for
the one-time seed row. No real crawl sessions are run.
"""

import os

import pytest
from sqlalchemy import select, text

from src import db
from src.update import oparlRunLog as orl

pytestmark = pytest.mark.integration


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


class _ConnScope:
    """Context manager yielding the shared connection without committing."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False  # no commit, no rollback - outer transaction decides


class _RollbackEngine:
    """Engine stand-in that routes everything into one open transaction."""

    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return _ConnScope(self._conn)

    def connect(self):
        return _ConnScope(self._conn)


@pytest.fixture()
def rollback_tx(engine, monkeypatch):
    """Open a transaction and roll it back when the test ends."""
    # tables must exist before the recorder runs (create_all cannot work
    # through the transaction-bound engine stand-in)
    orl.ensure_tables(engine)
    monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: None)
    conn = engine.connect()
    tx = conn.begin()
    yield _RollbackEngine(conn)
    tx.rollback()
    conn.close()


class TestRunRecorderRollback:
    def test_full_run_lifecycle_rolled_back(self, rollback_tx):
        from datetime import datetime, timezone

        run_ts = datetime.now(timezone.utc)
        recorder = orl.RunRecorder(engine=rollback_tx, run_timestamp=run_ts)
        assert recorder.available

        recorder.start("2026-10-01T00:00:00Z")
        assert recorder.run_id is not None

        for i in range(3):
            recorder.record_item("Paper", f"https://rollback.test/papers/{i}", f"{i}", orl.STATUS_NEW)
        for i in range(2):
            recorder.record_item("Meeting", f"https://rollback.test/meetings/{i}", f"{i}", orl.STATUS_MODIFIED)
        recorder.record_error()
        recorder.set_end_state("2026-10-23T12:00:00Z")
        recorder.finish(success=True)

        # visible inside the transaction
        with rollback_tx.connect() as conn:
            run = conn.execute(
                select(orl.OparlUpdateRun).where(orl.OparlUpdateRun.run_timestamp == run_ts)
            ).first()
            assert run is not None
            assert run.baseline == "2026-10-01T00:00:00Z"
            assert run.end_state == "2026-10-23T12:00:00Z"
            assert run.success is True
            assert run.total_new == 3 and run.total_modified == 2 and run.errors == 1

            items = conn.execute(
                select(orl.OparlUpdateRunItem).where(orl.OparlUpdateRunItem.run_id == run.id)
            ).fetchall()
            assert len(items) == 5
            counts = conn.execute(
                select(orl.OparlUpdateRunTypeCount).where(
                    orl.OparlUpdateRunTypeCount.run_id == run.id
                )
            ).fetchall()
            per_type = {c.element_type: (c.new_count, c.modified_count) for c in counts}
            assert per_type["Paper"] == (3, 0)
            assert per_type["Meeting"] == (0, 2)

        # baseline resolution sees the (uncommitted) row via the same connection
        baseline, source = orl.resolve_baseline(engine=rollback_tx)
        assert source == "table"
        assert baseline == "2026-10-23T12:00:00Z"

    def test_replay_same_run_timestamp_no_duplicates(self, rollback_tx):
        from datetime import datetime, timezone

        run_ts = datetime.now(timezone.utc)
        recorder = orl.RunRecorder(engine=rollback_tx, run_timestamp=run_ts)
        recorder.start("2026-10-01T00:00:00Z")
        recorder.record_item("Paper", "https://rollback.test/papers/42", "42", orl.STATUS_NEW)
        recorder.finish(success=True)

        recorder2 = orl.RunRecorder(engine=rollback_tx, run_timestamp=run_ts)
        recorder2.start("2026-10-01T00:00:00Z")
        recorder2.record_item("Paper", "https://rollback.test/papers/42", "42", orl.STATUS_MODIFIED)
        recorder2.record_item("Paper", "https://rollback.test/papers/43", "43", orl.STATUS_NEW)
        recorder2.finish(success=True)

        with rollback_tx.connect() as conn:
            runs = conn.execute(
                select(orl.OparlUpdateRun).where(orl.OparlUpdateRun.run_timestamp == run_ts)
            ).fetchall()
            assert len(runs) == 1
            items = conn.execute(
                select(orl.OparlUpdateRunItem).where(
                    orl.OparlUpdateRunItem.run_id == recorder.run_id
                )
            ).fetchall()
            assert {i.oparl_id for i in items} == {
                "https://rollback.test/papers/42",
                "https://rollback.test/papers/43",
            }
            counts = conn.execute(
                select(orl.OparlUpdateRunTypeCount).where(
                    orl.OparlUpdateRunTypeCount.run_id == recorder.run_id
                )
            ).fetchall()
            assert counts[0].new_count == 1 and counts[0].modified_count == 1

    def test_production_table_untouched_after_rollback(self, engine, rollback_tx):
        """The row written in the transaction must not exist after rollback."""
        from datetime import datetime, timezone

        run_ts = datetime.now(timezone.utc)
        recorder = orl.RunRecorder(engine=rollback_tx, run_timestamp=run_ts)
        recorder.start("2026-01-01T00:00:00Z")
        recorder.finish(success=True)

        with engine.connect() as conn:  # real engine, outside the transaction
            row = conn.execute(
                select(orl.OparlUpdateRun).where(orl.OparlUpdateRun.run_timestamp == run_ts)
            ).first()
        assert row is None, "rolled-back run row must not be persisted"


class TestReadonlyAccess:
    def test_tables_readable_by_readonly_role(self):
        ro_engine = db.get_engine(readonly=True)
        with ro_engine.connect() as conn:
            count = conn.execute(text('SELECT count(*) FROM "oparlUpdateRuns"')).scalar()
            assert count is not None


class TestSeedBaseline:
    def test_seeded_baseline_resolves(self):
        """The production table resolves the baseline from its latest row.

        Originally this asserted the 2026-02-19 seed value; the verified
        real sync runs (2026-10-24) legitimately advanced the baseline, so
        only the resolution source and the timestamp format are asserted.
        """
        baseline, source = orl.resolve_baseline()
        assert source == "table"
        ou_iso = baseline
        assert "T" in ou_iso  # ISO timestamp
        assert ou_iso >= orl.SEED_BASELINE[:19]  # never moves backwards
