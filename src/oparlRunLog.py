"""Run tracking for incremental OParl crawls.

Records every crawl run in the ``oparlUpdateRuns`` table together with a
per-element log of new/modified resources (``oparlUpdateRunItems``) and
per-type summary counts (``oparlUpdateRunTypeCounts``). The tracking table is
the source of truth for the next crawl baseline; the legacy ``last_run.txt``
file is read only once as a migration fallback (when the table has no rows)
and is never written.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import declarative_base

from src.db import get_engine, get_logger

_logger = get_logger(__name__)

EPOCH_BASELINE = "1970-01-01T00:00:00Z"
SEED_BASELINE = "2026-02-19T00:00:00+01:00"  # 19 Feb 2026, CET (initial seed)

STATUS_NEW = "new"
STATUS_MODIFIED = "modified"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Tables (own metadata; additive create-if-missing)
# ----------------------------------------------------------------------
Base = declarative_base()


class OparlUpdateRun(Base):
    __tablename__ = "oparlUpdateRuns"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime(timezone=True), nullable=False, unique=True)
    baseline = Column(String(64), nullable=True)
    end_state = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    success = Column(Boolean, nullable=True)
    total_new = Column(Integer, nullable=False, default=0)
    total_modified = Column(Integer, nullable=False, default=0)
    errors = Column(Integer, nullable=False, default=0)


class OparlUpdateRunItem(Base):
    __tablename__ = "oparlUpdateRunItems"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("oparlUpdateRuns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_type = Column(String(255), nullable=False)
    oparl_id = Column(String(512), nullable=False)
    oparl_key = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("run_id", "oparl_id", name="uq_run_item_oparl_id"),
    )


class OparlUpdateRunTypeCount(Base):
    __tablename__ = "oparlUpdateRunTypeCounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("oparlUpdateRuns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_type = Column(String(255), nullable=False)
    new_count = Column(Integer, nullable=False, default=0)
    modified_count = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("run_id", "element_type", name="uq_run_type_counts"),
    )


TABLES = [OparlUpdateRun.__table__, OparlUpdateRunItem.__table__, OparlUpdateRunTypeCount.__table__]


def ensure_tables(engine=None) -> None:
    """Create the tracking tables if missing (additive, non-destructive)."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine, tables=TABLES, checkfirst=True)
    # Best-effort: make the tables readable by the read-only role.
    try:
        with engine.begin() as conn:
            for table in TABLES:
                conn.execute(text(f'GRANT SELECT ON "{table.name}" TO wiski'))
    except Exception as e:  # pragma: no cover - privilege dependent
        _logger.debug("GRANT SELECT for read-only role failed: %s", e)


def resolve_baseline(engine=None) -> Tuple[str, str]:
    """Determine the crawl baseline.

    Order (design D6):
      1. latest row in ``oparlUpdateRuns`` (its ``end_state``, falling back to
         its ``baseline``) - the table is the sole source of truth;
      2. the epoch default when the table has no rows or the DB is
         unreachable - i.e. fetch everything.

    The legacy ``last_run.txt`` file is ignored completely. Returns
    ``(baseline, source)`` where *source* is ``"table"`` or ``"epoch"``.
    """
    engine = engine or get_engine()
    try:
        ensure_tables(engine)
        with engine.connect() as conn:
            row = conn.execute(
                select(
                    OparlUpdateRun.baseline,
                    OparlUpdateRun.end_state,
                )
                .order_by(OparlUpdateRun.run_timestamp.desc())
                .limit(1)
            ).first()
        if row is not None:
            state = row.end_state or row.baseline
            if state:
                return state, "table"
    except Exception as e:
        # DB unreachable: the baseline cannot be read from the table, so the
        # next run would fetch everything. Make the degraded state visible.
        _logger.error(
            "Cannot read run state from the database (%s); "
            "falling back to the epoch baseline (fetch everything)", e,
        )

    return EPOCH_BASELINE, "epoch"


class RunRecorder:
    """Records one crawl run: run row, item log and per-type counts.

    Items are batched in memory and flushed to the database in batches.
    If the database is unreachable, the recorder degrades to a no-op mode
    that reports a visible error (the baseline cannot advance without the
    tracking table) but never raises into the crawl.
    """

    FLUSH_EVERY = 500

    def __init__(self, engine=None, run_timestamp: Optional[datetime] = None):
        self._engine = engine or get_engine()
        self._available = True
        self.last_error: Optional[str] = None
        self.run_id: Optional[int] = None
        self._run_timestamp = run_timestamp or _now()
        self._baseline: Optional[str] = None
        self._end_state: Optional[str] = None
        self._items: List[dict] = []
        self._pending: List[dict] = []
        self._errors = 0
        try:
            ensure_tables(self._engine)
        except Exception as e:
            self._degrade(e)

    # ------------------------------------------------------------------
    def _degrade(self, error: Exception) -> None:
        self._available = False
        self.last_error = str(error)
        _logger.error(
            "OParl run tracking is unavailable (%s); the crawl continues but "
            "the run will NOT be recorded and the baseline cannot advance "
            "via the tracking table", error,
        )

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    def start(self, baseline: str) -> None:
        """Insert the run row for this crawl."""
        self._baseline = baseline
        if not self._available:
            return
        try:
            stmt = (
                pg_insert(OparlUpdateRun)
                .values(
                    run_timestamp=self._run_timestamp,
                    baseline=baseline,
                    started_at=_now(),
                    success=None,
                    total_new=0,
                    total_modified=0,
                    errors=0,
                )
                .on_conflict_do_update(
                    index_elements=["run_timestamp"],
                    set_={"baseline": baseline, "started_at": _now()},
                )
                .returning(OparlUpdateRun.id)
            )
            with self._engine.begin() as conn:
                self.run_id = conn.execute(stmt).scalar_one()
        except Exception as e:
            self._degrade(e)

    def record_item(
        self,
        element_type: str,
        oparl_id: str,
        oparl_key: Optional[str] = None,
        status: str = STATUS_MODIFIED,
    ) -> None:
        """Buffer one new/modified element; flushed in batches."""
        if status not in (STATUS_NEW, STATUS_MODIFIED):
            raise ValueError(f"invalid item status: {status!r}")
        self._items.append(
            {
                "element_type": element_type,
                "oparl_id": oparl_id,
                "oparl_key": oparl_key,
                "status": status,
            }
        )
        self._pending.append(
            {
                "element_type": element_type,
                "oparl_id": oparl_id,
                "oparl_key": oparl_key,
                "status": status,
                "recorded_at": _now(),
            }
        )
        if len(self._pending) >= self.FLUSH_EVERY:
            self.flush()

    def record_error(self) -> None:
        self._errors += 1

    def set_end_state(self, state: str) -> None:
        self._end_state = state

    # ------------------------------------------------------------------
    def _flush_items(self) -> None:
        if not self._pending or self.run_id is None:
            self._pending.clear()
            return
        rows = [{**item, "run_id": self.run_id} for item in self._pending]
        stmt = (
            pg_insert(OparlUpdateRunItem)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_run_item_oparl_id",
                set_={
                    "status": pg_insert(OparlUpdateRunItem).excluded.status,
                    "oparl_key": pg_insert(OparlUpdateRunItem).excluded.oparl_key,
                    "recorded_at": pg_insert(OparlUpdateRunItem).excluded.recorded_at,
                },
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        self._pending.clear()

    def _flush_counts(self) -> None:
        counts: dict[str, dict[str, int]] = {}
        for item in self._items:
            per_type = counts.setdefault(item["element_type"], {"new": 0, "modified": 0})
            per_type[item["status"]] += 1
        if not counts or self.run_id is None:
            return
        rows = [
            {
                "run_id": self.run_id,
                "element_type": element_type,
                "new_count": c["new"],
                "modified_count": c["modified"],
            }
            for element_type, c in counts.items()
        ]
        stmt = (
            pg_insert(OparlUpdateRunTypeCount)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_run_type_counts",
                set_={
                    "new_count": pg_insert(OparlUpdateRunTypeCount).excluded.new_count,
                    "modified_count": pg_insert(OparlUpdateRunTypeCount).excluded.modified_count,
                },
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def flush(self) -> None:
        """Write buffered items and recomputed type counts to the database."""
        if not self._available or self.run_id is None:
            self._pending.clear()
            return
        try:
            self._flush_items()
            self._flush_counts()
        except Exception as e:
            self._degrade(e)

    def finish(self, success: bool = True) -> None:
        """Flush everything and finalise the run row."""
        if not self._available or self.run_id is None:
            return
        try:
            self._flush_items()
            self._flush_counts()
            total_new = sum(1 for i in self._items if i["status"] == STATUS_NEW)
            total_modified = sum(1 for i in self._items if i["status"] == STATUS_MODIFIED)
            stmt = (
                pg_insert(OparlUpdateRun)
                .values(
                    run_timestamp=self._run_timestamp,
                    baseline=self._baseline,
                    end_state=self._end_state,
                    started_at=self._run_timestamp,
                    finished_at=_now(),
                    success=success,
                    total_new=total_new,
                    total_modified=total_modified,
                    errors=self._errors,
                )
                .on_conflict_do_update(
                    index_elements=["run_timestamp"],
                    set_={
                        "end_state": self._end_state,
                        "finished_at": _now(),
                        "success": success,
                        "total_new": total_new,
                        "total_modified": total_modified,
                        "errors": self._errors,
                    },
                )
            )
            with self._engine.begin() as conn:
                conn.execute(stmt)
            self._pending.clear()
        except Exception as e:
            self._degrade(e)
