"""Integration test for report data collection (unified-update-pipeline
task 3.7): run-row counters, stage-ledger transitions and row-count deltas
are reflected in the rendered report. Uses the live database (rollback-free:
only the stage ledger's own table is written) and skips when it is
unavailable."""

import pytest

from src.riskiUpdate import (
    BEST_EFFORT,
    CRITICAL,
    PhaseRegistry,
    PhaseResult,
    RunContext,
    _row_counts,
    render_report,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def engine():
    try:
        from src.db import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return engine
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live database unavailable: {exc}")


def test_report_collects_real_run_data(engine, tmp_path):
    import uuid

    from sqlalchemy import text

    from src.db.stageLedger import STATUS_DONE, STATUS_FAILED, StageLedger

    ledger = StageLedger(engine=engine)
    # unique per run: the ledger is durable, attempts accumulate across runs
    done_key = f"IT-{uuid.uuid4().hex[:8]}"
    fail_key = f"IT-{uuid.uuid4().hex[:8]}"

    ledger.record(done_key, "tags", STATUS_DONE)
    ledger.record(fail_key, "tags", STATUS_FAILED, reason="transient")
    ledger.record(fail_key, "tags", STATUS_FAILED, reason="transient")
    counts = ledger.summary("tags")

    ctx = RunContext(started_at="2026-10-25T10:00:00+00:00")
    ctx.sync_stats = {"total_new": 1, "errors": 0}
    ctx.phases = [PhaseResult("sync", CRITICAL, "ok", duration=1.0)]
    before = _row_counts(engine)
    # a nonzero delta so the row-delta section renders
    after = {t: {"before": v, "after": v + 1, "delta": 1} for t, v in before.items()}
    reg = PhaseRegistry()
    reg.add("sync", CRITICAL, lambda: None)

    report = tmp_path / "report.md"
    render_report(ctx, reg, {}, before, after, ledger, 5, report)
    content = report.read_text(encoding="utf-8")

    # sync counters from the run row land in the report
    assert "total_new: 1" in content
    # stage summary shows the ledger transitions
    assert f"done={counts['done']}" in content
    assert f"failed={counts['failed']}" in content
    # row deltas table lists the real main tables
    assert "| File |" in content and "| delta |" in content
    # the failing item stayed below the poison threshold of this report
    assert fail_key not in content
