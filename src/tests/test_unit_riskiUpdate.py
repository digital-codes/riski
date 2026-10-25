"""Unit tests for the riskiUpdate orchestrator — mocked phase adapters,
in-memory ledger, no live database / LLM endpoints."""

import sys

import pytest

import src.riskiUpdate as ru
from src.db.stageLedger import STATUS_DONE, STATUS_EMPTY, STATUS_FAILED, StageLedger
from src.riskiUpdate import (
    BEST_EFFORT,
    CRITICAL,
    EXIT_CRITICAL,
    EXIT_OK,
    EXIT_PARTIAL,
    PhaseRegistry,
    PhaseResult,
    RunContext,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def ledger():
    return StageLedger(engine=__import__("sqlalchemy").create_engine("sqlite://"))


def _registry_from(names_crits_fns):
    reg = PhaseRegistry()
    for name, crit, fn in names_crits_fns:
        reg.add(name, crit, fn)
    return reg


# ----------------------------------------------------------------------
# 3.1 registry / selection
# ----------------------------------------------------------------------

def test_registry_default_order():
    reg = _registry_from([
        ("snapshot", CRITICAL, lambda: None),
        ("sync", CRITICAL, lambda: None),
        ("ocr", BEST_EFFORT, lambda: None),
        ("tags", BEST_EFFORT, lambda: None),
    ])
    assert reg.names() == ["snapshot", "sync", "ocr", "tags"]


def test_phase_selection_subset_preserves_order():
    reg = _registry_from([
        ("snapshot", CRITICAL, lambda: None),
        ("sync", CRITICAL, lambda: None),
        ("ocr", BEST_EFFORT, lambda: None),
    ])
    assert [p["name"] for p in reg.select("sync,snapshot", None)] == \
        ["snapshot", "sync"]


def test_phase_skip():
    reg = _registry_from([
        ("sync", CRITICAL, lambda: None),
        ("ocr", BEST_EFFORT, lambda: None),
        ("tags", BEST_EFFORT, lambda: None),
    ])
    assert [p["name"] for p in reg.select(None, "ocr")] == ["sync", "tags"]


def test_unknown_phase_rejected():
    reg = PhaseRegistry()
    with pytest.raises(SystemExit, match="unknown phase"):
        reg.select("sync,bogus", None)


# ----------------------------------------------------------------------
# 3.4 exit codes
# ----------------------------------------------------------------------

def test_exit_code_ok():
    ctx = RunContext()
    ctx.phases = [
        PhaseResult("sync", CRITICAL, "ok"),
        PhaseResult("ocr", BEST_EFFORT, "ok"),
        PhaseResult("tags", BEST_EFFORT, "skipped"),
    ]
    assert ctx.exit_code == EXIT_OK


def test_exit_code_partial_on_best_effort_failure():
    ctx = RunContext()
    ctx.phases = [
        PhaseResult("sync", CRITICAL, "ok"),
        PhaseResult("ocr", BEST_EFFORT, "failed"),
        PhaseResult("tags", BEST_EFFORT, "ok"),
    ]
    assert ctx.exit_code == EXIT_PARTIAL


def test_exit_code_timeout_counts_as_failure():
    ctx = RunContext()
    ctx.phases = [
        PhaseResult("sync", CRITICAL, "ok"),
        PhaseResult("teasers", BEST_EFFORT, "timeout"),
    ]
    assert ctx.exit_code == EXIT_PARTIAL


def test_exit_code_critical_failure():
    ctx = RunContext()
    ctx.phases = [
        PhaseResult("snapshot", CRITICAL, "ok"),
        PhaseResult("sync", CRITICAL, "failed"),
        PhaseResult("ocr", BEST_EFFORT, "skipped"),
    ]
    assert ctx.exit_code == EXIT_CRITICAL


# ----------------------------------------------------------------------
# 3.3 failure semantics (mocked phases through run_update's helpers)
# ----------------------------------------------------------------------

def test_best_effort_failure_does_not_stop_phases(ledger, monkeypatch, tmp_path):
    """A failing best-effort phase must not prevent later phases."""
    executed = []

    # build a tiny fake pipeline via the PhaseRegistry primitives used by
    # run_update's loop; we test the loop's semantics directly here.
    reg = _registry_from([
        ("sync", CRITICAL, lambda: executed.append("sync") or {}),
        ("ocr", BEST_EFFORT, lambda: (_ for _ in ()).throw(RuntimeError("ocr down"))),
        ("tags", BEST_EFFORT, lambda: executed.append("tags") or {}),
    ])
    selected = reg.select(None, None)
    # emulate the run_update loop's phase handling
    ctx = RunContext()
    for phase in selected:
        try:
            phase["fn"]()
            pass
        except Exception as exc:  # noqa: BLE001
            if phase["criticality"] == CRITICAL:
                break
            ctx.errors.append(f"{phase['name']}: {exc}")
            continue
    assert executed == ["sync", "tags"]
    assert any("ocr" in e for e in ctx.errors)


def test_critical_failure_stops_run(ledger):
    executed = []
    reg = _registry_from([
        ("snapshot", CRITICAL, lambda: executed.append("snapshot") or {}),
        ("sync", CRITICAL,
         lambda: (_ for _ in ()).throw(RuntimeError("import failed"))),
        ("ocr", BEST_EFFORT, lambda: executed.append("ocr") or {}),
    ])
    ctx = RunContext()
    for phase in reg.select(None, None):
        try:
            phase["fn"]()
        except Exception:  # noqa: BLE001
            if phase["criticality"] == CRITICAL:
                break
    assert executed == ["snapshot"]  # ocr never ran


# ----------------------------------------------------------------------
# 3.5 locking
# ----------------------------------------------------------------------

def test_lock_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(ru, "LOCK_FILE", str(tmp_path / "lock"))
    assert ru.acquire_lock()
    # second acquisition in the same process via a fresh handle fails
    monkeypatch.setattr(ru, "_lock_handle", None)
    assert not ru.acquire_lock()
    ru.release_lock()


def test_lock_release_allows_reacquire(tmp_path, monkeypatch):
    monkeypatch.setattr(ru, "LOCK_FILE", str(tmp_path / "lock"))
    assert ru.acquire_lock()
    ru.release_lock()
    assert ru.acquire_lock()
    ru.release_lock()


# ----------------------------------------------------------------------
# 3.5 phase timeout
# ----------------------------------------------------------------------

def test_phase_timeout_raises_and_is_recorded_as_failure(ledger):
    def hang():
        import time

        time.sleep(5)

    with pytest.raises(TimeoutError):
        ru._run_with_deadline(hang, timeout=0.2)


def test_phase_deadline_worker_exception_propagates():
    def boom():
        raise ValueError("phase exploded")

    with pytest.raises(ValueError, match="phase exploded"):
        ru._run_with_deadline(boom, timeout=5)


# ----------------------------------------------------------------------
# 3.6 report rendering
# ----------------------------------------------------------------------

def test_report_renders_phases_stages_and_poison(ledger, tmp_path):
    from src.riskiUpdate import render_report

    ledger.record("F-1", "ocr", STATUS_DONE)
    ledger.record("F-2", "ocr", STATUS_EMPTY, reason="no text")
    for _ in range(3):
        ledger.record("F-3", "ocr", STATUS_FAILED, reason="backend 500")

    ctx = RunContext(
        started_at="2026-10-25T10:00:00+00:00",
        finished_at="2026-10-25T11:00:00+00:00",
        snapshot="/snapshots/riski_agentic_2026-10-25.dump",
        errors=["teasers: RuntimeError: LLM down"],
    )
    ctx.phases = [
        PhaseResult("sync", CRITICAL, "ok", duration=120.5,
                    counters={"total_new": 3, "total_modified": 7}),
        PhaseResult("ocr", BEST_EFFORT, "failed", duration=10.0,
                    errors=["RuntimeError: ocr backend down"]),
    ]
    ctx.sync_stats = {"total_new": 3, "total_modified": 7}
    reg = _registry_from([
        ("sync", CRITICAL, lambda: None),
        ("ocr", BEST_EFFORT, lambda: None),
        ("teasers", BEST_EFFORT, lambda: None),
    ])
    report = tmp_path / "report.md"
    render_report(ctx, reg, {}, {}, {}, ledger, 3, report)

    content = report.read_text(encoding="utf-8")
    # phases with criticality + status
    assert "| sync | critical | ok | 120.5 |" in content
    assert "| ocr | best-effort | failed | 10.0 |" in content
    # skipped phases still listed
    assert "| teasers | best-effort | skipped |" in content
    # sync counters
    assert "total_new: 3" in content
    # stage summary separates done/failed/empty
    assert "done=1" in content and "failed=1" in content and "empty=1" in content
    # poison items listed with attempts and reason
    assert "F-3" in content and "attempts=3" in content and "backend 500" in content
    # errors present
    assert "LLM down" in content


def test_report_survives_interrupted_run(ledger, tmp_path):
    """The report is re-rendered after every phase: a killed run still
    leaves a report reflecting completed phases."""
    from src.riskiUpdate import render_report

    ctx = RunContext(started_at="2026-10-25T10:00:00+00:00")
    ctx.phases = [PhaseResult("sync", CRITICAL, "ok", duration=5)]
    reg = _registry_from([
        ("sync", CRITICAL, lambda: None),
        ("ocr", BEST_EFFORT, lambda: None),
    ])
    report = tmp_path / "report.md"
    render_report(ctx, reg, {}, {}, {}, ledger, 3, report)
    content = report.read_text(encoding="utf-8")
    assert "(running)" in content  # finished_at not yet set
    assert "| sync | critical | ok |" in content


# ----------------------------------------------------------------------
# stage definitions
# ----------------------------------------------------------------------

def test_stage_defs_cover_stages():
    # the reconcilable stage defs exist for the DB-backed stages
    expected = {"summary", "content", "teaser", "geo", "tags"}
    # _stage_defs needs an engine; build with a fake to inspect keys only
    class _E:
        def connect(self):
            raise RuntimeError("no db in unit test")

    import src.db.stageLedger as sl

    ledger = StageLedger(engine=__import__("sqlalchemy").create_engine("sqlite://"))
    defs = ru._stage_defs(ledger)
    assert expected.issubset(set(defs))


# ----------------------------------------------------------------------
# 3.2 phase adapters: argv handling + SystemExit safety
# ----------------------------------------------------------------------

def test_argv_helper_restores_sysargv():
    import sys

    old = sys.argv
    with ru._argv("--embed-missing", "-s", "/x", "-f", "/y"):
        assert sys.argv[1:] == ["--embed-missing", "-s", "/x", "-f", "/y"]
    assert sys.argv == old


def test_content_adapter_invokes_main_with_explicit_args(monkeypatch, tmp_path):
    import src.update.pgAddSummaries as mod

    captured = {}

    def fake_main():
        captured["argv"] = list(sys.argv)

    monkeypatch.setattr(mod, "main", fake_main)
    from src.riskiUpdate import _phase_content

    class _LedgerStub:
        def record(self, *a, **kw):
            pass

    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 5)
    # main() is called via `from src import pgAddSummaries` inside the
    # adapter — patch the module attribute the adapter resolves
    monkeypatch.setattr("src.update.pgAddSummaries.main", fake_main)
    _phase_content(None, _LedgerStub())
    assert captured["argv"][1:] == [
        "--embed-missing", "-s", str(ru.SUMS_DIR), "-f", str(ru.MD_DIR),
    ]


def test_content_adapter_swallows_clean_systemexit(monkeypatch):
    import sys as _sys

    import src.update.pgAddSummaries as mod

    def fake_main():
        raise SystemExit(0)

    monkeypatch.setattr(mod, "main", fake_main)
    from src.riskiUpdate import _phase_content

    class _LedgerStub:
        def record(self, *a, **kw):
            pass

    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 5)
    _phase_content(None, _LedgerStub())  # no raise


def test_content_adapter_reraises_error_systemexit(monkeypatch):
    import src.update.pgAddSummaries as mod

    def fake_main():
        raise SystemExit(3)

    monkeypatch.setattr(mod, "main", fake_main)
    from src.riskiUpdate import _phase_content

    class _LedgerStub:
        def record(self, *a, **kw):
            pass

    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 5)
    with pytest.raises(RuntimeError, match="exited 3"):
        _phase_content(None, _LedgerStub())


def test_ocr_adapter_records_item_outcomes(monkeypatch):
    from src.riskiUpdate import _ocr_stats_with_keys, _phase_ocr

    class _LedgerStub:
        def __init__(self):
            self.rows = []

        def record(self, key, stage, status, reason=None):
            self.rows.append((key, stage, status, reason))

    ledger = _LedgerStub()
    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 5)
    monkeypatch.setattr(ru, "_ocr_stats_with_keys", lambda ctx: {
        "missing": 2, "ocr_ok": 1, "ocr_failed": 1, "empty": 0,
        "ok_keys": ["001"], "failed_keys": [("002", "backend 503")],
        "empty_keys": [],
    })
    stats = _phase_ocr(None, ledger)
    # item outcomes recorded in the ledger; aggregate keys stay out of counters
    assert ("001", "ocr", "done", None) in ledger.rows
    assert ("002", "ocr", "failed", "backend 503") in ledger.rows
    assert stats == {"missing": 2, "ocr_ok": 1, "ocr_failed": 1, "empty": 0}
