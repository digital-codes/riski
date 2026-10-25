"""Integration tests for src.update.syncIncremental against the live database.

Full sync flow with stubbed crawl/import phases; all DB writes (run row,
item log, type counts, full_fetches marker) happen inside a transaction
that is rolled back at test end (same pattern as
test_integration_oparlRunLog.py). No real crawl sessions are run.
"""

import os

import pytest
from sqlalchemy import select

from src import db
from src.update import oparlRunLog as orl
from src.update import syncIncremental as si

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
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False  # no commit - outer transaction decides


class _RollbackEngine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return _ConnScope(self._conn)

    def connect(self):
        return _ConnScope(self._conn)


@pytest.fixture()
def rollback_tx(engine, monkeypatch):
    orl.ensure_tables(engine)
    monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: None)
    # pin the baseline: unit/integration tests must not depend on the live
    # tracking table's current value
    monkeypatch.setattr(orl, "resolve_baseline",
                        lambda engine=None: (BASELINE, "table"))
    conn = engine.connect()
    tx = conn.begin()
    yield conn
    tx.rollback()
    conn.close()


BASELINE = "2026-02-19T00:00:00+01:00"


def _stub_crawl(items, full_fetches=(), end_state="2026-10-23T12:00:00+00:00",
                fail_import=False):
    """Build a crawl_oparl stand-in that records like the real one."""

    def crawl(system_url, baseline, recorder=None, finalise=True):
        assert finalise is False, "sync must finalise the run itself"
        assert baseline == BASELINE
        recorder.start(baseline)  # the real crawl_oparl starts the run row
        for element_type, oparl_id, status in items:
            recorder.record_item(element_type, oparl_id,
                                 oparl_key=oparl_id.rsplit("/", 1)[-1],
                                 status=status)
        for collection in full_fetches:
            recorder.record_full_fetch(collection)
        recorder.set_end_state(end_state)

    return crawl


class TestSyncFlowRollback:
    def test_successful_sync_records_run_items_counts_marker(self, rollback_tx, monkeypatch):
        crawl = _stub_crawl(
            items=[
                ("Meeting", "https://x/meetings/1", "new"),
                ("Paper", "https://x/papers/2", "modified"),
            ],
            full_fetches=["papers"],
        )
        monkeypatch.setattr(si, "crawl_oparl", crawl)
        monkeypatch.setattr("src.pgGen.main", lambda directory: None)

        recorder = orl.RunRecorder(engine=_RollbackEngine(rollback_tx))
        assert recorder.available
        code = si.sync(recorder=recorder)
        assert code == 0

        # run row: success, advanced end_state, full_fetches marker
        row = rollback_tx.execute(
            select(orl.OparlUpdateRun).order_by(orl.OparlUpdateRun.id.desc()).limit(1)
        ).first()
        assert row.success is True
        assert row.end_state == "2026-10-23T12:00:00+00:00"
        assert row.baseline == BASELINE
        assert row.full_fetches == "papers"

        # item log
        items = rollback_tx.execute(
            select(orl.OparlUpdateRunItem).where(orl.OparlUpdateRunItem.run_id == row.id)
        ).all()
        assert {(i.element_type, i.status) for i in items} == {
            ("Meeting", "new"), ("Paper", "modified"),
        }

        # per-type counts
        counts = rollback_tx.execute(
            select(orl.OparlUpdateRunTypeCount)
            .where(orl.OparlUpdateRunTypeCount.run_id == row.id)
        ).all()
        by_type = {c.element_type: (c.new_count, c.modified_count) for c in counts}
        assert by_type["Meeting"] == (1, 0)
        assert by_type["Paper"] == (0, 1)

    def test_failed_import_leaves_baseline_untouched(self, rollback_tx, monkeypatch):
        crawl = _stub_crawl(items=[("Meeting", "https://x/meetings/1", "new")],
                            end_state="2026-10-23T12:00:00+00:00")

        def failing_import(directory):
            raise RuntimeError("import exploded")

        monkeypatch.setattr(si, "crawl_oparl", crawl)
        monkeypatch.setattr("src.pgGen.main", failing_import)

        recorder = orl.RunRecorder(engine=_RollbackEngine(rollback_tx))
        code = si.sync(recorder=recorder)
        assert code == 1

        row = rollback_tx.execute(
            select(orl.OparlUpdateRun).order_by(orl.OparlUpdateRun.id.desc()).limit(1)
        ).first()
        assert row.success is False
        # end_state reset to the pre-crawl baseline: next run re-fetches the window
        assert row.end_state == BASELINE
