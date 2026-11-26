"""Integration test: report data collection + ledger transitions against
the live database (update-orchestration, task 3.7). Phase adapters are
mocked (no crawl/LLM work); the stage ledger and run-row schema are real.
Skipped automatically when no RW credentials are available."""

import os
import re
import time

import pytest
from sqlalchemy import create_engine, text

from src import riskiUpdate as ru
from src.db.stageLedger import STATUS_DONE, STATUS_FAILED, StageLedger

pytestmark = pytest.mark.integration

ITEST_KEY = f"itest-unified-pipeline-{int(time.time())}"  # unique per run


@pytest.fixture()
def live_ledger(monkeypatch, tmp_path):
    """Real ledger + engine against the configured database; isolated
    lock/report dir; mocked (cheap) phase adapters."""
    monkeypatch.setattr(ru, "LOCK_FILE", str(tmp_path / "run.lock"))
    monkeypatch.setattr(ru, "create_snapshot_phase",
                        lambda: str(tmp_path / "snap.dump"))

    def mock_sync(ctx, last_date=None):
        # exercise the real run-row schema: the adapter reads these columns
        with ru.get_engine().connect() as conn:
            row = conn.execute(text(
                'SELECT baseline, end_state, total_new, total_modified, errors '
                'FROM "oparlUpdateRuns" ORDER BY run_timestamp DESC LIMIT 1'
            )).mappings().first()
        return dict(row) if row else {}

    def mock_teasers(ctx, ledger):
        ledger.record(ITEST_KEY, "teaser", STATUS_FAILED, "itest failure A")
        ledger.record(ITEST_KEY, "teaser", STATUS_FAILED, "itest failure B")
        ledger.record(ITEST_KEY, "teaser", STATUS_FAILED, "itest failure C")
        ledger.record(ITEST_KEY, "tags", STATUS_DONE)
        raise RuntimeError("llm 500 — ledger populated")

    for name, fn in (("_phase_sync", mock_sync),
                     ("_phase_ocr", lambda ctx, ledger: {}),
                     ("_phase_summaries", lambda ctx, ledger: {}),
                     ("_phase_content", lambda ctx, ledger: {}),
                     ("_phase_teasers", mock_teasers),
                     ("_phase_geo", lambda ctx, ledger: {}),
                     ("_phase_tags", lambda ctx, ledger: {})):
        monkeypatch.setattr(ru, name, fn)

    ledger = StageLedger()
    yield ledger
    # cleanup: quirk — the table name must be quoted, it is case-sensitive
    try:
        with ru.get_engine().begin() as conn:
            conn.execute(text(
                'DELETE FROM "fileStageStatus" WHERE "oparlKey" = :k'),
                {"k": ITEST_KEY})
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


def test_report_collects_sync_stats_and_ledger_transitions(live_ledger, tmp_path):
    ledger = live_ledger
    code = ru.run_update(report_dir=str(tmp_path))
    assert code == ru.EXIT_PARTIAL
    report = next(tmp_path / f.name for f in tmp_path.iterdir()
                  if f.name.startswith("update_report_"))
    txt = report.read_text()
    # all phases listed with criticality + status
    assert "| sync | critical | ok |" in txt
    assert "| teasers | best-effort | failed |" in txt
    assert "| tags | best-effort | ok |" in txt
    # sync stats block (counters dict rendered under ## Sync)
    assert "baseline:" in txt
    # ledger transitions real: teaser failed x3 (attempts=3 → poison), tags done
    poison = ledger.poison(threshold=3)
    assert any(p["oparlKey"] == ITEST_KEY and p["stage"] == "teaser"
               and p["attempts"] >= 3 for p in poison)
    assert "## Poison items" in txt and ITEST_KEY in txt and "attempts=" in txt
    assert "teaser: done=0 failed=1 empty=0" in txt
    # tags summary line present (global counts); the run's own row is done
    assert re.search(r"tags: done=\d+ failed=\d+ empty=\d+", txt)
    assert ledger.status_of(ITEST_KEY, "tags") == STATUS_DONE
    # reconciliation flips the failed row on the next pass
    n = ledger.reconcile("teaser", lambda key: key == ITEST_KEY, [ITEST_KEY])
    assert n == 1
    assert ledger.status_of(ITEST_KEY, "teaser") == STATUS_DONE
    assert ledger.poison(threshold=3) == []


def test_stage_defs_queries_run_against_live_schema(live_ledger):
    """The stage definitions' SQL (candidate universe + done-checks) must
    execute against the real schema — catches silent drift of assoc tables."""
    ledger = live_ledger
    defs = ru._stage_defs(ledger)
    for stage, definition in defs.items():
        if stage == "summary":
            candidates = definition["candidates"]()  # filesystem only
            assert isinstance(candidates, list)
            continue
        candidates = definition["candidates"]() or []
        # done-check on an absent key must be safe (False/None, no raise)
        result = definition["check"]("no-such-oparl-key-xyz")
        assert not result
        # ledger integration: pending() on the real candidates universe
        ledger.pending(stage, candidates[:5])
