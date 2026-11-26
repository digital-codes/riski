"""Per-File enrichment stage ledger (change: unified-update-pipeline,
capability: enrichment-stage-tracking).

Every File advances through enrichment stages (ocr, summary, content,
teaser, geo, tags). The ledger records each (file, stage) outcome:

- ``done``   — the stage succeeded; never reprocessed
- ``failed`` — the stage failed (reason recorded, attempts incremented);
  retried on the next run
- ``empty``  — the stage genuinely does not apply (terminal, reason
  recorded); treated as satisfied, never retried

A file is *fully enriched* when every stage row is ``done`` or ``empty``.
The ledger is the single source of truth for what a run attempts:
``pending(stage)`` returns exactly the files whose row is absent or
``failed``. Reconciliation prefers reality: a row marked ``failed`` whose
data already satisfies the stage (verified by a caller-supplied check) is
marked ``done`` without reprocessing — a lost ledger row can therefore
only cause harmless rework, never data corruption.
"""

from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, insert, select,
    update,
)
from sqlalchemy.engine import Engine

from src.db import get_engine, table_exists

STAGES = ("ocr", "summary", "content", "teaser", "geo", "tags")
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_EMPTY = "empty"

LEDGER_TABLE = "fileStageStatus"

_metadata = MetaData()
_ledger = Table(
    LEDGER_TABLE,
    _metadata,
    Column("oparlKey", String, primary_key=True),
    Column("stage", String, primary_key=True),
    Column("status", String, nullable=False),  # done | failed | empty
    Column("reason", String, nullable=True),
    Column("attempts", Integer, nullable=False, default=0),
    Column("updatedAt", DateTime, nullable=False),
)


class StageLedger:
    """Database-backed per-File stage status. Created on demand; portable
    across PostgreSQL (production) and SQLite (tests)."""

    def __init__(self, engine: Optional[Engine] = None, stages: Iterable[str] = STAGES):
        self.engine = engine or get_engine()
        self.stages = tuple(stages)
        self._ensure_table()

    # -- schema ----------------------------------------------------------

    def _ensure_table(self) -> None:
        if not table_exists(LEDGER_TABLE, self.engine):
            _metadata.create_all(self.engine, tables=[_ledger])

    # -- writes ----------------------------------------------------------

    def record(self, oparl_key: str, stage: str, status: str,
               reason: Optional[str] = None) -> None:
        """Record a stage outcome. ``failed`` increments the attempt
        counter; ``done`` resets it (consecutive-failure tracking)."""
        if status not in (STATUS_DONE, STATUS_FAILED, STATUS_EMPTY):
            raise ValueError(f"invalid stage status: {status!r}")
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            row = conn.execute(
                select(_ledger.c.attempts).where(
                    _ledger.c.oparlKey == oparl_key, _ledger.c.stage == stage
                )
            ).first()
            attempts = 0
            if row is not None:
                attempts = (row.attempts or 0) + 1 if status == STATUS_FAILED else 0
                conn.execute(
                    update(_ledger)
                    .where(_ledger.c.oparlKey == oparl_key, _ledger.c.stage == stage)
                    .values(status=status, reason=reason, attempts=attempts,
                            updatedAt=now)
                )
            else:
                attempts = 1 if status == STATUS_FAILED else 0
                conn.execute(insert(_ledger).values(
                    oparlKey=oparl_key, stage=stage, status=status,
                    reason=reason, attempts=attempts, updatedAt=now,
                ))

    # -- reads -----------------------------------------------------------

    def status_of(self, oparl_key: str, stage: str) -> Optional[str]:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(_ledger.c.status).where(
                    _ledger.c.oparlKey == oparl_key, _ledger.c.stage == stage
                )
            ).first()
        return row.status if row else None

    def pending(self, stage: str, files: Iterable[str]) -> List[str]:
        """From *files* (the stage's candidate universe), exactly those
        whose ledger row is absent or ``failed`` — the set a run will
        attempt. Order is preserved."""
        with self.engine.connect() as conn:
            done_or_empty = {
                row.oparlKey for row in conn.execute(
                    select(_ledger.c.oparlKey).where(
                        _ledger.c.stage == stage,
                        _ledger.c.status.in_([STATUS_DONE, STATUS_EMPTY]),
                    )
                )
            }
        files = list(files)
        return [k for k in files if k not in done_or_empty]

    def summary(self, stage: str) -> Dict[str, int]:
        """Counts per status for one stage; ``pending`` = rows absent."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(_ledger.c.status, _ledger.c.oparlKey).where(
                    _ledger.c.stage == stage)
            ).all()
        counts = {"done": 0, "failed": 0, "empty": 0, "pending": 0}
        for status, _key in rows:
            counts[status] = counts.get(status, 0) + 1
        return counts

    def poison(self, threshold: int = 3) -> List[Dict]:
        """Items whose stage has failed ``threshold`` or more consecutive
        times — the report's repeat offenders."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(_ledger.c.oparlKey, _ledger.c.stage, _ledger.c.attempts,
                       _ledger.c.reason)
                .where(_ledger.c.status == STATUS_FAILED,
                       _ledger.c.attempts >= threshold)
                .order_by(_ledger.c.attempts.desc())
            ).all()
        return [
            {"oparlKey": r.oparlKey, "stage": r.stage,
             "attempts": r.attempts, "reason": r.reason}
            for r in rows
        ]

    # -- reconciliation ----------------------------------------------------

    def reconcile(self, stage: str, check_fn: Callable[[str], bool],
                  files: Iterable[str]) -> int:
        """Mark ``failed``/absent rows whose data already satisfies the
        stage as ``done`` (reason: reconciled) without reprocessing.
        Returns the number of reconciled rows."""
        reconciled = 0
        for key in files:
            if self.status_of(key, stage) != STATUS_FAILED:
                continue
            if check_fn(key):
                self.record(key, stage, STATUS_DONE, reason="reconciled")
                reconciled += 1
        return reconciled
