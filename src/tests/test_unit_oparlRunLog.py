"""Unit tests for src.oparlRunLog – mocked engine / in-memory SQLite."""

import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

from src import oparlRunLog as orl

pytestmark = pytest.mark.unit


@pytest.fixture()
def pg_engine(monkeypatch):
    """Real Postgres engine but isolated recorder tables via unique schema? No:
    unit tests must not touch the live DB. Use a fake engine recorder instead.
    """
    return None


class TestTableDefinitions:
    def test_tables_present(self):
        names = {t.name for t in orl.TABLES}
        assert names == {"oparlUpdateRuns", "oparlUpdateRunItems", "oparlUpdateRunTypeCounts"}

    def test_run_table_columns(self):
        cols = {c.name for c in orl.OparlUpdateRun.__table__.columns}
        assert {"id", "run_timestamp", "baseline", "end_state", "started_at",
                "finished_at", "success", "total_new", "total_modified", "errors"} <= cols

    def test_item_table_columns(self):
        cols = {c.name for c in orl.OparlUpdateRunItem.__table__.columns}
        assert {"id", "run_id", "element_type", "oparl_id", "oparl_key",
                "status", "recorded_at"} <= cols

    def test_count_table_columns(self):
        cols = {c.name for c in orl.OparlUpdateRunTypeCount.__table__.columns}
        assert {"id", "run_id", "element_type", "new_count", "modified_count"} <= cols


class TestStatusValidation:
    def test_invalid_status_raises(self):
        recorder = orl.RunRecorder.__new__(orl.RunRecorder)
        recorder._items = []
        recorder._pending = []
        recorder._available = False  # skip DB path
        with pytest.raises(ValueError):
            recorder.record_item("Meeting", "https://x/1", status="bogus")


class TestBaselineResolution:
    def test_epoch_when_nothing_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # no DB: monkeypatch ensure_tables to raise, engine irrelevant
        class Boom:
            def connect(self):
                raise RuntimeError("no db")

        baseline, source = orl.resolve_baseline(engine=Boom())
        assert baseline == orl.EPOCH_BASELINE
        assert source == "epoch"

    def test_empty_table_yields_epoch(self, monkeypatch):
        """A tracking table with no rows resolves to the epoch baseline."""
        monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: None)
        from sqlalchemy import create_engine
        eng = create_engine("sqlite://")
        orl.Base.metadata.create_all(eng, tables=orl.TABLES)
        baseline, source = orl.resolve_baseline(engine=eng)
        assert source == "epoch"
        assert baseline == orl.EPOCH_BASELINE

    def test_table_row_beats_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: None)
        (tmp_path / "last_run.txt").write_text("2026-01-15T10:00:00Z\n")

        class Row:
            baseline = "2026-02-01T00:00:00Z"
            end_state = "2026-02-10T12:00:00Z"

        class TableDB:
            def __init__(self):
                self.calls = 0

            def connect(self):
                self.calls += 1
                raise AssertionError  # never called directly

        # Patch the module-level query path: emulate a successful table read.
        orig_connect = None
        import src.oparlRunLog as m

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, stmt):
                class Res:
                    def first(self):
                        return Row()

                return Res()

        class TableEngine:
            def connect(self):
                return FakeConn()

        baseline, source = m.resolve_baseline(engine=TableEngine())
        assert source == "table"
        assert baseline == "2026-02-10T12:00:00Z"  # end_state preferred over baseline

    def test_table_falls_back_to_baseline_when_no_end_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: None)
        class Row:
            baseline = "2026-02-01T00:00:00Z"
            end_state = None

        import src.oparlRunLog as m

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, stmt):
                class Res:
                    def first(self):
                        return Row()

                return Res()

        class TableEngine:
            def connect(self):
                return FakeConn()

        baseline, source = m.resolve_baseline(engine=TableEngine())
        assert baseline == "2026-02-01T00:00:00Z"
        assert source == "table"


class TestRecorderDegradedMode:
    def test_degraded_mode_records_error_and_never_raises(self, monkeypatch, tmp_path):
        calls = {}

        def boom(engine=None):
            calls["err"] = RuntimeError("db down")
            raise calls["err"]

        monkeypatch.setattr(orl, "ensure_tables", boom)
        recorder = orl.RunRecorder(engine=object())
        assert recorder.available is False
        assert recorder.last_error is not None
        # all operations are no-ops and must not raise
        recorder.start("2026-01-01T00:00:00Z")
        recorder.record_item("Meeting", "https://x/1", status="new")
        recorder.record_error()
        recorder.finish(success=True)
        assert recorder.run_id is None

    def test_degraded_state_is_visible(self, monkeypatch):
        monkeypatch.setattr(orl, "ensure_tables", lambda engine=None: (_ for _ in ()).throw(RuntimeError("down")))
        recorder = orl.RunRecorder(engine=object())
        assert recorder.available is False
        assert "down" in recorder.last_error


class TestFlushBatching:
    def test_flush_called_at_threshold(self, monkeypatch):
        """record_item triggers flush() every FLUSH_EVERY items."""
        counter = {"flushes": 0}
        recorder = orl.RunRecorder.__new__(orl.RunRecorder)
        recorder._available = False  # flush becomes a no-op clear
        recorder._items = []
        recorder._pending = []
        recorder.run_id = None
        monkeypatch.setattr(orl.RunRecorder, "flush", lambda self: counter.__setitem__("flushes", counter["flushes"] + 1))
        for i in range(orl.RunRecorder.FLUSH_EVERY + 1):
            recorder.record_item("Meeting", f"https://x/{i}", status="new")
        # the stub flush does not clear the buffer, so it re-triggers once
        # more after the threshold - at least one flush must have happened
        assert counter["flushes"] >= 1
        assert len(recorder._items) == orl.RunRecorder.FLUSH_EVERY + 1


class TestFullFetchesMarker:
    """Task 1.3: full_fetches marker on the run row."""

    def test_column_present(self):
        cols = {c.name for c in orl.OparlUpdateRun.__table__.columns}
        assert "full_fetches" in cols

    def test_ensure_tables_adds_missing_column(self, monkeypatch):
        """The ALTER TABLE migration runs for pre-existing tables."""
        executed = []

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, stmt):
                executed.append(str(stmt))

        class FakeEngine:
            def begin(self):
                return FakeConn()

        monkeypatch.setattr(orl, "get_engine", lambda: FakeEngine())
        monkeypatch.setattr(orl.Base.metadata, "create_all", lambda *a, **k: None)
        orl.ensure_tables(engine=FakeEngine())
        assert any("ADD COLUMN IF NOT EXISTS" in s and "full_fetches" in s
                   for s in executed)

    def test_record_full_fetch_dedupes(self, monkeypatch):
        recorder = orl.RunRecorder.__new__(orl.RunRecorder)
        recorder._available = False
        recorder._full_fetches = []
        recorder.record_full_fetch("papers")
        recorder.record_full_fetch("papers")
        recorder.record_full_fetch("meetings")
        assert recorder._full_fetches == ["papers", "meetings"]

    def test_finish_writes_comma_separated_marker(self, monkeypatch):
        """finish() persists the collected full-fetch types (NULL when none)."""
        captured = {}

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, stmt):
                captured["values"] = stmt.compile().params

        class FakeEngine:
            def begin(self):
                return FakeConn()

        recorder = orl.RunRecorder.__new__(orl.RunRecorder)
        recorder._engine = FakeEngine()
        recorder._available = True
        recorder.run_id = 1
        recorder._run_timestamp = orl._now()
        recorder._baseline = "2026-01-01T00:00:00Z"
        recorder._end_state = "2026-01-02T00:00:00Z"
        recorder._full_fetches = []
        recorder._items = []
        recorder._pending = []
        recorder._errors = 0
        recorder.finish(success=True)
        assert captured["values"]["full_fetches"] is None

        recorder._full_fetches = ["papers", "meetings"]
        recorder.finish(success=True)
        assert captured["values"]["full_fetches"] == "papers,meetings"
