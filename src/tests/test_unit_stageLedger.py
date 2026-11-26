"""Unit tests for the per-File stage ledger (enrichment-stage-tracking).
SQLite in-memory — no live database required."""

import pytest
from sqlalchemy import create_engine

from src.db.stageLedger import (
    STATUS_DONE,
    STATUS_EMPTY,
    STATUS_FAILED,
    STAGES,
    StageLedger,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def ledger():
    engine = create_engine("sqlite://")
    return StageLedger(engine=engine)


def test_record_and_status(ledger):
    ledger.record("F-1", "ocr", STATUS_DONE)
    assert ledger.status_of("F-1", "ocr") == STATUS_DONE
    assert ledger.status_of("F-1", "summary") is None


def test_record_rejects_unknown_status(ledger):
    with pytest.raises(ValueError):
        ledger.record("F-1", "ocr", "maybe")


def test_pending_excludes_done_and_empty(ledger):
    ledger.record("F-1", "ocr", STATUS_DONE)
    ledger.record("F-2", "ocr", STATUS_EMPTY)
    ledger.record("F-3", "ocr", STATUS_FAILED)
    pending = ledger.pending("ocr", ["F-1", "F-2", "F-3", "F-4"])
    # done/empty are never retried; absent + failed are
    assert pending == ["F-3", "F-4"]
    assert pending.index("F-3") < pending.index("F-4")  # order preserved


def test_failed_items_retried_next_run(ledger):
    # run N: OCR fails for F-1, succeeds for F-2
    ledger.record("F-1", "ocr", STATUS_FAILED, reason="backend 503")
    ledger.record("F-2", "ocr", STATUS_DONE)
    # run N+1: F-1 is pending again, F-2 is not
    assert ledger.pending("ocr", ["F-1", "F-2"]) == ["F-1"]
    # run N+1 succeeds: status flips to done
    ledger.record("F-1", "ocr", STATUS_DONE)
    assert ledger.pending("ocr", ["F-1"]) == []


def test_attempts_count_consecutive_failures(ledger):
    ledger.record("F-1", "summary", STATUS_FAILED, reason="a")
    ledger.record("F-1", "summary", STATUS_FAILED, reason="b")
    ledger.record("F-1", "summary", STATUS_FAILED, reason="c")
    assert ledger.status_of("F-1", "summary") == STATUS_FAILED
    poison = ledger.poison(threshold=3)
    assert [(p["oparlKey"], p["stage"], p["attempts"]) for p in poison] == [
        ("F-1", "summary", 3)
    ]
    # success resets the counter
    ledger.record("F-1", "summary", STATUS_DONE)
    assert ledger.poison(threshold=1) == []


def test_empty_is_terminal_and_distinguishable(ledger):
    ledger.record("F-1", "ocr", STATUS_EMPTY, reason="no extractable text")
    # empty counts as satisfied: not pending
    assert ledger.pending("ocr", ["F-1"]) == []
    counts = ledger.summary("ocr")
    assert counts == {"done": 0, "failed": 0, "empty": 1, "pending": 0}
    # summary separates done/empty/failed
    ledger.record("F-2", "ocr", STATUS_DONE)
    ledger.record("F-3", "ocr", STATUS_FAILED)
    counts = ledger.summary("ocr")
    assert (counts["done"], counts["empty"], counts["failed"]) == (1, 1, 1)


def test_poison_threshold(ledger):
    for _ in range(2):
        ledger.record("F-1", "teaser", STATUS_FAILED, reason="x")
    assert ledger.poison(threshold=3) == []
    ledger.record("F-1", "teaser", STATUS_FAILED, reason="x")
    assert len(ledger.poison(threshold=3)) == 1


def test_reconcile_prefers_reality(ledger):
    ledger.record("F-1", "summary", STATUS_FAILED, reason="transient")
    ledger.record("F-2", "summary", STATUS_FAILED, reason="real failure")
    # check_fn reports F-1's artifact already exists (reconcilable), F-2's not
    n = ledger.reconcile("summary", lambda k: k == "F-1",
                         files=["F-1", "F-2"])
    assert n == 1
    assert ledger.status_of("F-1", "summary") == STATUS_DONE
    assert ledger.status_of("F-2", "summary") == STATUS_FAILED
    # reconciled rows are not pending
    assert ledger.pending("summary", ["F-1", "F-2"]) == ["F-2"]


def test_summary_counts_pending_for_absent_rows(ledger):
    ledger.record("F-1", "geo", STATUS_DONE)
    counts = ledger.summary("geo")
    # pending is derived by the caller from the candidate universe; the
    # ledger only counts recorded rows here
    assert counts["done"] == 1 and counts["pending"] == 0


def test_all_stages_covered_by_ledger(ledger):
    for stage in STAGES:
        ledger.record("F-1", stage, STATUS_DONE)
        assert ledger.status_of("F-1", stage) == STATUS_DONE
