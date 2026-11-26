"""Unit tests for the riskiUpdate orchestrator (update-orchestration).
Phase adapters are mocked; the ledger uses SQLite; no live DB/LLM needed."""

import sys
import threading
import time

import pytest
from sqlalchemy import create_engine

from src.db.stageLedger import STATUS_DONE, STATUS_FAILED, StageLedger
from src import riskiUpdate as ru

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------
# fixtures: run_update with mocked phase adapters
# ----------------------------------------------------------------------

class Recorder:
    """Records which phases ran in which order."""

    def __init__(self):
        self.calls = []


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Isolated orchestrator environment (lock, engine, ledger)."""
    monkeypatch.setattr(ru, "LOCK_FILE", str(tmp_path / "run.lock"))
    engine = create_engine("sqlite://")

    def fake_stage_ledger():
        return StageLedger(engine=create_engine("sqlite://"))

    monkeypatch.setattr(ru, "StageLedger", fake_stage_ledger)
    monkeypatch.setattr(ru, "get_engine", lambda *a, **k: engine)
    monkeypatch.setattr(ru, "create_snapshot_phase",
                        lambda: tmp_path / "snap.dump")
    rec = Recorder()
    # mock every phase adapter; build_registry resolves them at call time
    for name in ("_phase_sync", "_phase_ocr", "_phase_summaries",
                 "_phase_content", "_phase_teasers", "_phase_geo",
                 "_phase_tags"):
        monkeypatch.setattr(ru, name,
                            lambda *a, _n=name.split("_")[-1], **k:
                            rec.calls.append(_n) or {})
    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 10.0)
    return rec, tmp_path


# ----------------------------------------------------------------------
# registry / selection (task 3.1)
# ----------------------------------------------------------------------

def test_registry_default_order_and_criticality():
    registry = ru.build_registry(ru.RunContext(), ru.StageLedger(
        engine=create_engine("sqlite://")))
    assert registry.names() == ["snapshot", "sync", "ocr", "summaries",
                                "content", "teasers", "geo", "tags"]
    crit = {p["name"]: p["criticality"] for p in registry._phases}
    assert crit["snapshot"] == ru.CRITICAL
    assert crit["sync"] == ru.CRITICAL
    assert crit["tags"] == ru.BEST_EFFORT


def test_select_subset_and_unknown_phase(monkeypatch):
    registry = ru.PhaseRegistry()
    for n in ("snapshot", "sync", "tags"):
        registry.add(n, ru.CRITICAL if n != "tags" else ru.BEST_EFFORT,
                     lambda: {})
    sel = registry.select("sync,tags", None)
    assert [p["name"] for p in sel] == ["sync", "tags"]
    sel = registry.select(None, "tags")
    assert [p["name"] for p in sel] == ["snapshot", "sync"]
    with pytest.raises(SystemExit):
        registry.select("nope", None)


# ----------------------------------------------------------------------
# run semantics (tasks 3.3 / 3.4)
# ----------------------------------------------------------------------

def test_default_run_executes_all_phases(env):
    rec, tmp = env
    code = ru.run_update(report_dir=str(tmp))
    # snapshot runs via create_snapshot_phase (mocked), sync via _phase_sync
    assert rec.calls == ["sync", "ocr", "summaries", "content",
                         "teasers", "geo", "tags"]
    assert code == ru.EXIT_OK


def test_phase_selection_and_skip_reported(env):
    rec, tmp = env
    code = ru.run_update(phases="sync,ocr", skip="ocr", report_dir=str(tmp))
    assert rec.calls == ["sync"]
    report = next((tmp / f).name for f in tmp.iterdir()
                  if f.name.startswith("update_report_"))
    assert "skipped" in (tmp / report).read_text()


def test_critical_failure_stops_run(env, monkeypatch):
    rec, tmp = env

    def failing_sync(ctx, last_date=None):
        raise RuntimeError("crawl down")

    monkeypatch.setattr(ru, "_phase_sync", failing_sync)
    code = ru.run_update(report_dir=str(tmp))
    assert code == ru.EXIT_CRITICAL
    assert rec.calls == []  # enrichment phases never started
    report = next((tmp / f).name for f in tmp.iterdir()
                  if f.name.startswith("update_report_"))
    text = (tmp / report).read_text()
    assert "failed" in text and "crawl down" in text


def test_best_effort_failure_continues(env, monkeypatch):
    rec, tmp = env

    def failing_teasers(ctx, ledger):
        raise RuntimeError("llm 500")

    monkeypatch.setattr(ru, "_phase_teasers", failing_teasers)
    code = ru.run_update(report_dir=str(tmp))
    assert code == ru.EXIT_PARTIAL
    # geo and tags still ran after the teaser failure
    assert rec.calls == ["sync", "ocr", "summaries", "content", "geo", "tags"]
    report = next((tmp / f).name for f in tmp.iterdir()
                  if f.name.startswith("update_report_"))
    assert "llm 500" in (tmp / report).read_text()


def test_exit_code_property():
    ctx = ru.RunContext()
    ctx.phases = [ru.PhaseResult("sync", ru.CRITICAL, "ok"),
                  ru.PhaseResult("geo", ru.BEST_EFFORT, "ok")]
    assert ctx.exit_code == ru.EXIT_OK
    ctx.phases.append(ru.PhaseResult("tags", ru.BEST_EFFORT, "failed"))
    assert ctx.exit_code == ru.EXIT_PARTIAL
    ctx.phases[0].status = "failed"
    assert ctx.exit_code == ru.EXIT_CRITICAL  # critical wins


# ----------------------------------------------------------------------
# deadline (task 3.5)
# ----------------------------------------------------------------------

def test_run_with_deadline_value_and_error():
    assert ru._run_with_deadline(lambda: 42, 5) == 42
    with pytest.raises(ValueError):
        ru._run_with_deadline(lambda: (_ for _ in ()).throw(ValueError("x")), 5)


def test_run_with_deadline_times_out():
    start = time.time()
    with pytest.raises(TimeoutError):
        ru._run_with_deadline(lambda: time.sleep(1.0), 0.05)
    assert time.time() - start < 0.9


def test_phase_timeout_recorded_and_run_continues(env, monkeypatch):
    rec, tmp = env

    def hung_teasers(ctx, ledger):
        raise TimeoutError("phase exceeded 0.05s deadline")

    monkeypatch.setattr(ru, "PHASE_TIMEOUT", 0.05)
    monkeypatch.setattr(ru, "_phase_teasers", hung_teasers)
    code = ru.run_update(report_dir=str(tmp))
    assert code == ru.EXIT_PARTIAL
    assert rec.calls[-2:] == ["geo", "tags"]  # run continued past the hang


# ----------------------------------------------------------------------
# locking (task 3.5)
# ----------------------------------------------------------------------

def test_overlapping_invocation_exits_immediately(env, monkeypatch, tmp_path):
    """Second invocation while a subprocess holds the lock: no work,
    no phases executed."""
    import subprocess
    import sys as _sys
    rec, _ = env
    lock = str(tmp_path / "exclusive.lock")
    monkeypatch.setattr(ru, "LOCK_FILE", lock)
    holder = subprocess.Popen(
        [_sys.executable, "-c",
         "import fcntl, time; f=open('" + lock + "', 'w'); "
         "fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); "
         "time.sleep(3)"],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        assert ru.acquire_lock() is False
    finally:
        holder.kill()
        holder.wait()
        if ru._lock_handle is not None:
            ru.release_lock()


# ----------------------------------------------------------------------
# report (task 3.6)
# ----------------------------------------------------------------------

def test_report_contents_partial_run(env, monkeypatch, tmp_path):
    rec, tmp = env

    def failing_geo(ctx, ledger):
        raise RuntimeError("geo gate down")

    monkeypatch.setattr(ru, "_phase_geo", failing_geo)

    # stateful row counts: first census 10 rows/table, later census 12
    calls = {"n": 0}

    def fake_counts(engine):
        calls["n"] += 1
        return {t: (10 if calls["n"] == 1 else 12) for t in ru.MAIN_TABLES}

    monkeypatch.setattr(ru, "_row_counts", fake_counts)
    ru.run_update(report_dir=str(tmp))
    report = next((tmp / f).name for f in tmp.iterdir()
                  if f.name.startswith("update_report_"))
    text = (tmp / report).read_text()
    for phase in ("snapshot", "sync", "ocr", "summaries", "content",
                  "teasers", "geo", "tags"):
        assert f"| {phase} " in text
    assert "| sync | critical | ok |" in text
    assert "| geo | best-effort | failed |" in text
    # best-effort failure does not block: tags still ran (per spec)
    assert "| tags | best-effort | ok |" in text
    assert "## Row deltas" in text
    assert "| File_chunks | 10 | 12 | 2 |" in text
    assert "## Errors" in text


def test_report_lists_poison_items(env, monkeypatch, tmp_path):
    rec, tmp = env

    def failing_teasers(ctx, ledger):
        ledger.record("F-1", "teaser", STATUS_FAILED, "llm 500")
        ledger.record("F-1", "teaser", STATUS_FAILED, "llm 500")
        ledger.record("F-1", "teaser", STATUS_FAILED, "llm 500")
        ledger.record("F-2", "teaser", STATUS_DONE)
        raise RuntimeError("llm 500 — ledger recorded")

    monkeypatch.setattr(ru, "_phase_teasers", failing_teasers)
    code = ru.run_update(report_dir=str(tmp))
    assert code == ru.EXIT_PARTIAL
    report = next((tmp / f).name for f in tmp.iterdir()
                  if f.name.startswith("update_report_"))
    text = (tmp / report).read_text()
    assert "Poison items" in text and "F-1" in text
    assert "attempts=3" in text
    # stage summary counts ledger ROWS (not attempts): F-2 done, F-1 failed
    assert "teaser: done=1 failed=1 empty=0" in text


def test_row_deltas_includes_chunk_store():
    before = dict.fromkeys(ru.MAIN_TABLES, 10)
    after = dict.fromkeys(ru.MAIN_TABLES, 12)
    deltas = ru._row_deltas(before, after)
    assert "File_chunks" in deltas
    assert deltas["File_chunks"] == {"before": 10, "after": 12, "delta": 2}
