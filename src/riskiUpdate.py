"""riskiUpdate — one-command update pipeline (change: unified-update-pipeline).

Composes the existing, individually idempotent pipeline steps into a
cron-safe sequence:

    snapshot → sync → ocr → summaries → content → teasers → geo → tags

Failure philosophy (amended proposal, 2026-10-25):

- **Criticality classes.** ``snapshot`` and ``sync`` are critical — on
  failure the run stops (the sync baseline deliberately stays put, so the
  next run re-fetches the window). All enrichment phases are best-effort:
  a failure is recorded and the remaining phases still run. The pipeline
  heals by *retrying on the next run*, never by auto-rollback; the
  snapshot remains a manual recovery point for the operator.
- **Per-File stage ledger** (``src/db/stageLedger.py``): each phase
  reconciles its stage against reality (artifacts/rows that already exist
  are marked done) and records item failures where the underlying script
  reports them; stages with an idempotent ``done``-check never mark failed
  work as complete.
- **Cron contract.** An exclusive ``flock`` prevents overlapping runs; a
  per-phase timeout bounds hung LLM calls (timed-out phases are recorded
  failed and retried next run); exit codes: 0 = all executed stages
  done/empty, 1 = critical failure, 2 = partial success with recorded
  failures.
- **Report.** A markdown report is re-rendered after every phase (an
  interrupted run still leaves a usable report) into the snapshot
  directory.

Usage:
    python src/riskiUpdate.py [--phases sync,enrich] [--skip teasers]
                              [--last-date ISO] [--phase-timeout SECONDS]
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import dataclasses
import fcntl
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text

from src.db import DB_NAME, get_engine
from src.db.stageLedger import STATUS_DONE, STATUS_EMPTY, STATUS_FAILED, StageLedger

# ----------------------------------------------------------------------
# data directories (match the pipeline scripts' operational defaults)
# ----------------------------------------------------------------------
DATA_DIR = Path(os.getenv("RISKI_DATA_DIR", "/mnt_ai/data/odd26/ris"))
PDF_DIR = DATA_DIR / "ko_pdf"
MD_DIR = DATA_DIR / "ko_extracted"
SUMS_DIR = DATA_DIR / "ko_sums"
SNAPSHOT_DIR = os.getenv("RISKI_SNAPSHOT_DIR", "/mnt_ai/data/riski/snapshots")
LOCK_FILE = os.getenv("RISKI_UPDATE_LOCK", "/tmp/riski-update.lock")

CRITICAL = "critical"
BEST_EFFORT = "best-effort"

EXIT_OK = 0
EXIT_CRITICAL = 1
EXIT_PARTIAL = 2

MAIN_TABLES = ("Paper", "File", "AgendaItem", "Meeting", "Person",
               "Consultation", "Organization", "Location", "Membership")


# ----------------------------------------------------------------------
# run context / phase results (task 3.1)
# ----------------------------------------------------------------------

@dataclasses.dataclass
class PhaseResult:
    name: str
    criticality: str
    status: str = "pending"          # ok | failed | timeout | skipped
    duration: float = 0.0
    counters: Dict[str, Any] = dataclasses.field(default_factory=dict)
    errors: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class RunContext:
    started_at: str = ""
    finished_at: str = ""
    snapshot: Optional[str] = None
    phases: List[PhaseResult] = dataclasses.field(default_factory=list)
    sync_stats: Dict[str, Any] = dataclasses.field(default_factory=dict)
    row_deltas: Dict[str, Any] = dataclasses.field(default_factory=dict)
    stage_summaries: Dict[str, Dict[str, int]] = dataclasses.field(default_factory=dict)
    poison: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    errors: List[str] = dataclasses.field(default_factory=list)

    def phase(self, name: str) -> PhaseResult:
        for p in self.phases:
            if p.name == name:
                return p
        raise KeyError(name)

    @property
    def exit_code(self) -> int:
        statuses = [p.status for p in self.phases if p.status != "skipped"]
        if any(p.status in ("failed", "timeout") and p.criticality == CRITICAL
               for p in self.phases):
            return EXIT_CRITICAL
        if any(s in ("failed", "timeout") for s in statuses):
            return EXIT_PARTIAL
        return EXIT_OK


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _row_counts(engine) -> Dict[str, int]:
    counts = {}
    with engine.connect() as conn:
        for table in MAIN_TABLES:
            try:
                counts[table] = conn.execute(
                    text(f'SELECT count(*) FROM "{table}"')).scalar()
            except Exception:  # noqa: BLE001 - table may not exist yet
                counts[table] = -1
    return counts


@contextmanager
def _argv(*args: str):
    """Temporarily replace sys.argv for argparse-only main() entry points."""
    old = sys.argv
    sys.argv = ["riskiUpdate", *args]
    try:
        yield
    finally:
        sys.argv = old


def _run_with_deadline(fn: Callable[[], Any], timeout: float) -> Any:
    """Run fn() with a deadline; raise TimeoutError when it exceeds it.
    The worker thread is a daemon: an orphaned phase dies with the process
    (its idempotent successor retries the work)."""
    result: Dict[str, Any] = {}

    def worker():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised in caller
            result["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"phase exceeded {timeout}s deadline")
    if "error" in result:
        raise result["error"]
    return result.get("value")


# ----------------------------------------------------------------------
# phase adapters (task 3.2) — each: (callable, stage, candidate_fn, check_fn)
# ----------------------------------------------------------------------

def _phase_sync(ctx: RunContext, last_date: Optional[str]) -> Dict[str, Any]:
    from src.update import syncIncremental

    code = syncIncremental.sync(last_date=last_date)
    if code != 0:
        raise RuntimeError(f"syncIncremental exited {code}")
    # run-row counters from the just-finished run
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            'SELECT baseline, end_state, total_new, total_modified, errors '
            'FROM "oparlUpdateRuns" ORDER BY run_timestamp DESC LIMIT 1'
        )).mappings().first()
    return dict(row) if row else {}


def _ocr_stats_with_keys(ctx: RunContext) -> Dict[str, Any]:
    """pgOcr with per-item outcome keys (stage-ledger recording)."""
    from src.update.pgOcr import find_missing, ocr_pdf_to_markdown

    stats = {"missing": 0, "ocr_ok": 0, "ocr_failed": 0, "empty": 0,
             "ok_keys": [], "failed_keys": [], "empty_keys": []}
    missing = find_missing(PDF_DIR, MD_DIR)
    stats["missing"] = len(missing)
    MD_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_path in missing:
        try:
            markdown = ocr_pdf_to_markdown(pdf_path)
        except Exception as exc:  # noqa: BLE001 - item failure: keep going
            stats["ocr_failed"] += 1
            stats["failed_keys"].append((pdf_path.stem, str(exc)[:300]))
            continue
        if not markdown:
            stats["empty"] += 1
            stats["empty_keys"].append(pdf_path.stem)
            continue
        (MD_DIR / (pdf_path.stem + ".md")).write_text(markdown, encoding="utf-8")
        stats["ocr_ok"] += 1
        stats["ok_keys"].append(pdf_path.stem)
    return stats


def _phase_ocr(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    stats = _run_with_deadline(lambda: _ocr_stats_with_keys(ctx), PHASE_TIMEOUT)
    for key in stats["ok_keys"]:
        ledger.record(key, "ocr", STATUS_DONE)
    for key, reason in stats["failed_keys"]:
        ledger.record(key, "ocr", STATUS_FAILED, reason=reason)
    for key in stats["empty_keys"]:
        ledger.record(key, "ocr", STATUS_EMPTY, reason="no extractable text")
    return {k: v for k, v in stats.items() if not k.endswith("_keys")}


def _phase_summaries(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    from src.update.pgSummarize import _run_summarizer

    _run_with_deadline(lambda: _run_summarizer(MD_DIR, SUMS_DIR), PHASE_TIMEOUT)
    return {}


def _phase_content(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    from src.update import pgAddSummaries

    def run():
        with _argv("--embed-missing",
                   "-s", str(SUMS_DIR), "-f", str(MD_DIR)):
            try:
                pgAddSummaries.main()
            except SystemExit as exc:  # argparse/validation exits
                if exc.code not in (0, None):
                    raise RuntimeError(f"pgAddSummaries exited {exc.code}")

    _run_with_deadline(run, PHASE_TIMEOUT)
    return {}


def _phase_teasers(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    from src.update import pgTeasers

    def run():
        with _argv():
            try:
                pgTeasers.main()
            except SystemExit as exc:
                if exc.code not in (0, None):
                    raise RuntimeError(f"pgTeasers exited {exc.code}")

    _run_with_deadline(run, PHASE_TIMEOUT)
    return {}


def _phase_geo(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    from src.update import pgAddDistrictRefs, pgAddFileGeoRefs, pgAddStreetRefs

    parts = []

    def run():
        with _argv("--prune"):
            code = pgAddFileGeoRefs.main()
        if code not in (0, None):
            raise RuntimeError(f"pgAddFileGeoRefs exited {code}")
        parts.append("fileGeoRefs")
        with _argv():
            pgAddStreetRefs.main()
        parts.append("streetRefs")
        with _argv():
            pgAddDistrictRefs.main()
        parts.append("districtRefs")

    _run_with_deadline(run, PHASE_TIMEOUT)
    return {"steps": parts}


def _phase_tags(ctx: RunContext, ledger: StageLedger) -> Dict[str, Any]:
    from src.update import pgCategorise

    def run():
        with _argv("all"):
            code = pgCategorise.main()
        if code not in (0, None):
            raise RuntimeError(f"pgCategorise exited {code}")

    _run_with_deadline(run, PHASE_TIMEOUT)
    return {}


# stage definitions for ledger integration: stage -> (candidate universe,
# done-check). The candidate universe is derived from reality; `pending()`
# filters it by the ledger.
def _stage_defs(ledger: StageLedger) -> Dict[str, Dict[str, Any]]:
    engine = get_engine()

    def files_with_content():
        with engine.connect() as conn:
            return [r[0] for r in conn.execute(text(
                'SELECT "oparlKey" FROM "File" WHERE content IS NOT NULL'))]

    return {
        "summary": {
            "candidates": lambda: [p.stem for p in sorted(MD_DIR.glob("*.md"))],
            "check": lambda key: (SUMS_DIR / f"{key}.md").is_file(),
        },
        "content": {
            "candidates": files_with_content,
            "check": lambda key: _db_scalar(
                'SELECT content IS NOT NULL FROM "File" WHERE "oparlKey" = :k',
                key, engine),
        },
        "teaser": {
            "candidates": files_with_content,
            "check": lambda key: _db_scalar(
                'SELECT teaser IS NOT NULL FROM "File" WHERE "oparlKey" = :k',
                key, engine),
        },
        "geo": {
            "candidates": files_with_content,
            "check": lambda key: _db_scalar(
                'SELECT (SELECT count(*) FROM "Streets_items_Files" sf '
                'JOIN "File" fl ON fl.sid = sf.file_id WHERE fl."oparlKey" = :k) + '
                '(SELECT count(*) FROM "Districts_items_Files" df '
                'JOIN "File" fl ON fl.sid = df.file_id WHERE fl."oparlKey" = :k)',
                key, engine),
        },
        "tags": {
            "candidates": files_with_content,
            "check": lambda key: _db_scalar(
                'SELECT count(*) > 0 FROM "File_tags_assoc" WHERE srcSid = '
                '(SELECT sid FROM "File" WHERE "oparlKey" = :k)', key, engine),
        },
    }


def _db_scalar(sql: str, key: str, engine) -> Any:
    with engine.connect() as conn:
        try:
            return conn.execute(text(sql), {"k": key}).scalar()
        except Exception:  # noqa: BLE001 - table/row missing
            return None


def _reconcile_stage(ledger: StageLedger, stage: str, definition: Dict[str, Any]) -> int:
    """Mark ledger rows done whose data already satisfies the stage."""
    try:
        candidates = definition["candidates"]()
    except Exception as exc:  # noqa: BLE001 - candidates need the DB up
        return 0
    return ledger.reconcile(stage, definition["check"], candidates)


# ----------------------------------------------------------------------
# orchestrator
# ----------------------------------------------------------------------

PHASE_TIMEOUT = float(os.getenv("RISKI_PHASE_TIMEOUT", "7200"))  # 2h per phase


class PhaseRegistry:
    """Ordered phases with criticality (task 3.1)."""

    def __init__(self):
        self._phases: List[Dict[str, Any]] = []

    def add(self, name: str, criticality: str, fn: Callable, **kwargs) -> None:
        self._phases.append({"name": name, "criticality": criticality,
                             "fn": fn, "kwargs": kwargs})

    def names(self) -> List[str]:
        return [p["name"] for p in self._phases]

    def select(self, phases: Optional[str], skip: Optional[str]) -> List[Dict[str, Any]]:
        selected = self._phases
        if phases:
            wanted = [p.strip() for p in phases.split(",") if p.strip()]
            unknown = [w for w in wanted if w not in self.names()]
            if unknown:
                raise SystemExit(f"unknown phase(s): {', '.join(unknown)}")
            selected = [p for p in self._phases if p["name"] in wanted]
        if skip:
            skipped = {p.strip() for p in skip.split(",") if p.strip()}
            selected = [p for p in selected if p["name"] not in skipped]
        return selected


def build_registry(ctx: RunContext, ledger: StageLedger,
                   last_date: Optional[str] = None) -> PhaseRegistry:
    registry = PhaseRegistry()
    registry.add("snapshot", CRITICAL,
                 lambda: str(create_snapshot_phase()))
    registry.add("sync", CRITICAL,
                 lambda: _phase_sync(ctx, last_date))
    stage_defs = _stage_defs(ledger)
    registry.add("ocr", BEST_EFFORT, lambda: _phase_ocr(ctx, ledger))
    registry.add("summaries", BEST_EFFORT, lambda: _phase_summaries(ctx, ledger))
    registry.add("content", BEST_EFFORT, lambda: _phase_content(ctx, ledger),
                 stage="content", defs=stage_defs)
    registry.add("teasers", BEST_EFFORT, lambda: _phase_teasers(ctx, ledger),
                 stage="teaser", defs=stage_defs)
    registry.add("geo", BEST_EFFORT, lambda: _phase_geo(ctx, ledger),
                 stage="geo", defs=stage_defs)
    registry.add("tags", BEST_EFFORT, lambda: _phase_tags(ctx, ledger),
                 stage="tags", defs=stage_defs)
    return registry


def create_snapshot_phase() -> Path:
    from src.db.db_snapshot import create_snapshot

    return create_snapshot(DB_NAME, target_dir=SNAPSHOT_DIR)


def _post_phase_reconcile(name: str, stage: Optional[str],
                          defs: Optional[Dict], ledger: StageLedger) -> None:
    """After a successful best-effort phase, reconcile its stage: data
    reality wins over a stale failed ledger row."""
    if not stage or not defs or stage not in defs:
        return
    try:
        _reconcile_stage(ledger, stage, defs[stage])
    except Exception as exc:  # noqa: BLE001 - reporting only
        print(f"  reconcile({stage}) failed: {exc}")


def run_update(phases: Optional[str] = None, skip: Optional[str] = None,
               last_date: Optional[str] = None,
               phase_timeout: Optional[float] = None,
               poison_threshold: int = 3,
               report_dir: Optional[str] = None) -> int:
    ctx = RunContext(started_at=datetime.now(timezone.utc).isoformat())
    global PHASE_TIMEOUT
    if phase_timeout is not None:
        PHASE_TIMEOUT = phase_timeout

    if not acquire_lock():
        print("another riskiUpdate run holds the lock — exiting", flush=True)
        return EXIT_OK

    ledger = StageLedger()
    registry = build_registry(ctx, ledger, last_date=last_date)
    selected = registry.select(phases, skip)

    # initialise every phase result so skipped phases appear in the report
    all_results = {name: PhaseResult(name, crit, "skipped")
                   for name, crit in
                   ((p["name"], p["criticality"]) for p in registry._phases)}
    engine = get_engine()
    counts_before = _row_counts(engine)

    report_path = Path(report_dir or SNAPSHOT_DIR) / (
        f"update_report_{datetime.now():%Y-%m-%d_%H%M}.md")
    critical_failure = False

    try:
        for phase in selected:
            name, crit = phase["name"], phase["criticality"]
            result = PhaseResult(name, crit)
            ctx.phases = [r for r in ctx.phases if r.name != name] + [result]
            ctx.phases.sort(key=lambda r: registry.names().index(r.name))
            print(f"[{name}] running ({crit}) ...", flush=True)
            start = time.time()
            try:
                counters = phase["fn"]()
                result.status = "ok"
                result.counters = counters or {}
                if name == "snapshot" and counters:
                    ctx.snapshot = counters
                if name == "sync":
                    ctx.sync_stats = counters or {}
            except TimeoutError as exc:
                result.status = "timeout"
                result.errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001 - phase failure recorded
                result.status = "failed"
                result.errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                result.duration = round(time.time() - start, 1)

            if result.status in ("failed", "timeout"):
                ctx.errors.append(f"{name}: {result.errors[0]}")
                if crit == CRITICAL:
                    critical_failure = True
                    render_report(ctx, registry, all_results, counts_before,
                                  _row_counts(engine), ledger, poison_threshold,
                                  report_path)
                    break

            # ledger reconciliation for successful best-effort stages
            stage = next((p.get("stage") for p in registry._phases
                          if p["name"] == name), None)
            defs = next((p.get("defs") for p in registry._phases
                         if p["name"] == name), None)
            if result.status == "ok":
                _post_phase_reconcile(name, stage, defs, ledger)

            ctx.stage_summaries = {
                s: ledger.summary(s) for s in ledger.stages
            }
            ctx.poison = ledger.poison(threshold=poison_threshold)
            ctx.row_deltas = _row_deltas(counts_before, _row_counts(engine))
            render_report(ctx, registry, all_results, counts_before,
                          ctx.row_deltas, ledger, poison_threshold, report_path)
    finally:
        ctx.finished_at = datetime.now(timezone.utc).isoformat()
        ctx.stage_summaries = {s: ledger.summary(s) for s in ledger.stages}
        ctx.poison = ledger.poison(threshold=poison_threshold)
        render_report(ctx, registry, all_results, counts_before,
                      _row_deltas(counts_before, _row_counts(engine)),
                      ledger, poison_threshold, report_path)
        release_lock()

    print(f"report: {report_path}", flush=True)
    return ctx.exit_code


def _row_deltas(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, Dict]:
    return {t: {"before": b, "after": a, "delta": a - b}
            for t, b, a in zip(MAIN_TABLES,
                               (before[t] for t in MAIN_TABLES),
                               (after[t] for t in MAIN_TABLES))}


# ----------------------------------------------------------------------
# locking (task 3.5)
# ----------------------------------------------------------------------

_lock_handle = None


def acquire_lock() -> bool:
    global _lock_handle
    _lock_handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _lock_handle.close()
        _lock_handle = None
        return False
    return True


def release_lock() -> None:
    global _lock_handle
    if _lock_handle is not None:
        fcntl.flock(_lock_handle, fcntl.LOCK_UN)
        _lock_handle.close()
        _lock_handle = None


# ----------------------------------------------------------------------
# report (task 3.6)
# ----------------------------------------------------------------------

def render_report(ctx: RunContext, registry: PhaseRegistry,
                  all_results: Dict[str, PhaseResult],
                  counts_before: Dict[str, int],
                  counts_after: Dict[str, Any],
                  ledger: StageLedger, poison_threshold: int,
                  report_path: Path) -> None:
    report_dir = report_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append(f"# RISKI update report — {ctx.started_at}\n")
    lines.append(f"- finished: {ctx.finished_at or '(running)'}")
    lines.append(f"- snapshot: {ctx.snapshot or '(none)'}")
    lines.append(f"- exit code semantics: 0 = all done, 1 = critical "
                 f"failure, 2 = partial (recorded stage failures)\n")

    lines.append("## Phases\n")
    lines.append("| phase | criticality | status | duration (s) |")
    lines.append("|---|---|---|---|")
    executed = {p.name: p for p in ctx.phases}
    for name in registry.names():
        p = executed.get(name) or all_results.get(name) or PhaseResult(name, "best-effort", "skipped")
        lines.append(f"| {name} | {p.criticality} | {p.status} | {p.duration} |")
    lines.append("")

    if ctx.sync_stats:
        lines.append("## Sync\n")
        for key, value in ctx.sync_stats.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    stage_lines = []
    for stage in ledger.stages:
        summary = ledger.summary(stage)
        stage_lines.append(
            f"- {stage}: done={summary['done']} failed={summary['failed']} "
            f"empty={summary['empty']}")
    if stage_lines:
        lines.append("## Enrichment stages\n")
        lines.extend(stage_lines)
        lines.append("")

    poison = ledger.poison(threshold=poison_threshold)
    if poison:
        lines.append(f"## Poison items (failed >= {poison_threshold} attempts)\n")
        for p in poison:
            lines.append(f"- {p['oparlKey']} [{p['stage']}] "
                         f"attempts={p['attempts']} — {p['reason']}")
        lines.append("")

    if counts_after and any(v.get("delta") for v in counts_after.values()):
        lines.append("## Row deltas\n")
        lines.append("| table | before | after | delta |")
        lines.append("|---|---|---|---|")
        for table, d in counts_after.items():
            lines.append(f"| {table} | {d['before']} | {d['after']} | {d['delta']} |")
        lines.append("")

    if ctx.errors:
        lines.append("## Errors\n")
        for err in ctx.errors:
            lines.append(f"- {err}")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command RISKI update pipeline (snapshot → sync → enrich → report)")
    parser.add_argument("--phases", default=None,
                        help="comma-separated subset (snapshot,sync,ocr,summaries,content,teasers,geo,tags)")
    parser.add_argument("--skip", default=None, help="comma-separated phases to skip")
    parser.add_argument("--last-date", default=None,
                        help="ISO timestamp overriding the tracked sync baseline")
    parser.add_argument("--phase-timeout", type=float, default=None,
                        help="per-phase deadline in seconds (default: RISKI_PHASE_TIMEOUT or 7200)")
    parser.add_argument("--poison-threshold", type=int, default=3,
                        help="report items whose stage failed >= N consecutive runs")
    args = parser.parse_args(argv)
    return run_update(phases=args.phases, skip=args.skip,
                      last_date=args.last_date,
                      phase_timeout=args.phase_timeout,
                      poison_threshold=args.poison_threshold)


if __name__ == "__main__":
    raise SystemExit(main())
