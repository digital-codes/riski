"""Unit tests for src.syncIncremental – crawl and import phases mocked."""

import pytest

from src import syncIncremental as si


class _FakeRecorder:
    """Recorder double capturing the sync entry point's interactions."""

    def __init__(self, engine=None):
        self._engine = engine
        self.started = None
        self.end_state = None
        self.finished = None
        self.available = True

    def start(self, baseline):
        self.started = baseline

    def set_end_state(self, state):
        self.end_state = state

    def finish(self, success=True):
        self.finished = success

    # syncIncremental resolves the baseline via recorder._engine
    def _resolve_baseline(self):
        return "2026-02-19T00:00:00+01:00", "table"


@pytest.fixture(autouse=True)
def fixed_baseline(monkeypatch):
    """Unit tests must not read the live tracking table — the baseline the
    sync resolves is fixed (a successful run 2026-10-24 legitimately moved
    the real baseline past the value asserted here)."""
    import src.oparlRunLog as orl
    monkeypatch.setattr(orl, "resolve_baseline",
                        lambda engine=None: ("2026-02-19T00:00:00+01:00", "table"))


@pytest.fixture()
def mocked_phases(monkeypatch):
    """Stub both phases; returns the call log dicts."""
    log = {"crawl": [], "import": []}

    def fake_crawl(system_url, baseline, recorder=None, finalise=True):
        log["crawl"].append({"system_url": system_url, "baseline": baseline,
                             "finalise": finalise, "recorder": recorder})
        # crawl_oparl (real) sets the end state before the caller finalises
        recorder.set_end_state("2026-10-23T12:00:00+00:00")

    def fake_import(directory):
        log["import"].append({"directory": directory})

    monkeypatch.setattr(si, "crawl_oparl", fake_crawl)
    monkeypatch.setattr("src.pgGen.main", fake_import)
    return log


class TestSyncSuccess:
    def test_success_path(self, mocked_phases):
        recorder = _FakeRecorder()
        code = si.sync(system_url="https://x/oparl",
                       output_folder="/out", recorder=recorder)
        assert code == 0
        # crawl ran without finalising the run itself
        assert mocked_phases["crawl"][0]["finalise"] is False
        assert mocked_phases["crawl"][0]["baseline"] == "2026-02-19T00:00:00+01:00"
        # import ran against the crawl output folder
        assert mocked_phases["import"][0]["directory"] == "/out"
        # run finalised with success and the advanced end state
        assert recorder.finished is True
        assert recorder.end_state == "2026-10-23T12:00:00+00:00"


class TestImportFailure:
    def test_import_failure_resets_baseline(self, mocked_phases, monkeypatch):
        def boom(directory):
            raise RuntimeError("db unavailable")

        monkeypatch.setattr("src.pgGen.main", boom)
        recorder = _FakeRecorder()
        code = si.sync(output_folder="/out", recorder=recorder)
        assert code == 1
        assert recorder.finished is False
        # end_state reset to the pre-crawl baseline
        assert recorder.end_state == "2026-02-19T00:00:00+01:00"

    def test_import_system_exit_resets_baseline(self, mocked_phases, monkeypatch):
        def boom(directory):
            raise SystemExit(2)

        monkeypatch.setattr("src.pgGen.main", boom)
        recorder = _FakeRecorder()
        assert si.sync(recorder=recorder) == 1
        assert recorder.finished is False
        assert recorder.end_state == "2026-02-19T00:00:00+01:00"


class TestCrawlFailure:
    def test_crawl_failure_does_not_import(self, monkeypatch):
        log = {"import": []}

        def failing_crawl(system_url, baseline, recorder=None, finalise=True):
            raise RuntimeError("network down")

        def fake_import(directory):
            log["import"].append(directory)

        monkeypatch.setattr(si, "crawl_oparl", failing_crawl)
        monkeypatch.setattr("src.pgGen.main", fake_import)
        recorder = _FakeRecorder()
        code = si.sync(recorder=recorder)
        assert code == 1
        assert log["import"] == []  # import never ran
        assert recorder.finished is False
        assert recorder.end_state == "2026-02-19T00:00:00+01:00"

    def test_keyboard_interrupt_records_partial_run(self, monkeypatch):
        def interrupted_crawl(system_url, baseline, recorder=None, finalise=True):
            raise KeyboardInterrupt

        monkeypatch.setattr(si, "crawl_oparl", interrupted_crawl)
        recorder = _FakeRecorder()
        assert si.sync(recorder=recorder) == 1
        assert recorder.finished is False


class TestBaselineOverride:
    def test_last_date_overrides_tracked_baseline(self, mocked_phases):
        recorder = _FakeRecorder()
        si.sync(last_date="2026-05-21T16:20:38+02:00", recorder=recorder)
        assert mocked_phases["crawl"][0]["baseline"] == "2026-05-21T16:20:38+02:00"


pytestmark = pytest.mark.unit
