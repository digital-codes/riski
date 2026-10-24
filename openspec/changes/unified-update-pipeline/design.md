# Design

## Context

The pipeline's building blocks already exist and are individually idempotent:
`syncIncremental.sync()` (crawl + import, baseline only advances on import
success), `pgOcr.run()`, `pgSummarize._run_summarizer(src, dst)`,
`pgAddSummaries.main()` (with `--embed-missing`), `pgTeasers.main()` (needs
`RISKI_LLM_*` env), `pgAddFileGeoRefs.run()` (+ `pgAddStreetRefs`/
`pgAddDistrictRefs` mains), `pgCategorise.main()`, `pgCoverage` and the
`oparlUpdateRuns` tracking tables. The 2026-10-24 update proved the flow but
was orchestrated by hand; the missing pieces are composition, a pre-run
snapshot, rollback and reporting. The snapshot directory
`/mnt_ai/data/riski/snapshots/` is already in operational use.

## Goals / Non-Goals

**Goals:**
- One entry point (`src/riskiUpdate.py`) that composes the existing phases,
  takes a verified snapshot first, and produces a run report.
- Optional automatic restore from the snapshot on failure.
- Clear module separation: `src/update/`, `src/db/`, `src/search/` with
  backward-compatible shims.
- Every phase individually selectable and re-runnable.

**Non-Goals:**
- No change to crawl/import/enrichment behaviour (that is `oparl-import` /
  `data-enrichment`'s domain — already implemented).
- No scheduler/daemon: still a CLI, cron wiring is the operator's job
  (documented pattern in README).
- No schema changes; no new Python dependencies (pg_dump/pg_restore are
  system tools already in use).
- No parallel phase execution.

## Decisions

**D1 — Orchestrator calls existing `main()`/`run()` functions in-process.**
Each phase is a small adapter that invokes the existing module entry points
(captured stdout/log output per phase into the report context). Alternative:
shell out to the scripts as subprocesses — rejected because env/credential
passing becomes stringly and in-process calls keep the rollback decision
programmatic. Subprocess remains the fallback for steps that hard-exit
(`pgTeasers.main()` uses `sys.exit`? — adapter must intercept `SystemExit`).

**D2 — Snapshot via `pg_dump -Fc`, verify via `pg_restore --list`.** Helpers
live in `src/db/db_snapshot.py` (build_url from `src.db`); snapshot name
`riski_agentic_<date>[_<HHMM>].dump`. Alternative: SQL-level backups — rejected
(pg_dump is the operational standard already in use).

**D3 — Restore is two-step and defensive.** `pg_restore` into a NEW database
(`<name>_restore_<ts>`), run `pg_restore --list` verification against it,
then swap: terminate connections, `ALTER DATABASE ... RENAME` current →
`<name>_pre_restore_<ts>`, rename restore target → live name. The old
database is kept (not dropped) so a bad restore is itself reversible.
Alternative: drop-and-restore in place — rejected (unrecoverable on failure).

**D4 — Auto-restore is opt-in** (`--auto-restore`). Default on failure:
stop, report, print the restore command. Rationale: a wrong automatic restore
could discard hours of enrichment work; the operator decides for unattended
cron runs.

**D5 — Report as structured context + markdown rendering.** Each phase
adapter returns a `PhaseResult` (name, status, duration, counters, errors)
appended to a `RunContext`; rendering to markdown happens at the end (and on
SIGINT/failure). Row-count deltas: reuse a fixed list of main tables
(Paper, File, AgendaItem, Meeting, Person, Consultation, Organization,
Location, Membership) counted before sync and after enrich.

**D6 — Module restructure is move + shim.** Modules move into packages;
old paths become `from src.update.pgOcr import *  # noqa` one-liners
(explicit names, not `*`: re-export the public API). Tests move with the
modules (test import paths updated), shims keep external commands working.
`src/db` already exists and stays.

**D7 — Phase list and ordering.** snapshot → sync → ocr → summaries →
content(+embeddings) → teasers → geo → tags → report. OCR/summaries are
file-system steps (no DB writes) and run before content so the DB import
picks up markdown produced in the same run.

## Risks / Trade-offs

- [Long LLM phases block the report] → report is written incrementally
  (re-rendered after every phase), so a killed run still leaves a useful
  report.
- [`pgTeasers.main()` hard-exits / uses its own arg parsing] → adapter wraps
  in try/except SystemExit and sets argv explicitly.
- [Restore swap needs exclusive access] → documented: stop the API/app during
  a rollback; orchestrator terminates connections via
  `pg_terminate_backend` before rename.
- [Snapshot size (~680 MB per run)] → retention: keep the last N snapshots
  (N configurable, default 5) — pruning is manual by default.
- [Module moves can break third-party references] → shims + full test suite
  run before/after the move.

## Migration Plan

1. `src/db/db_snapshot.py` (snapshot/verify/restore/swap) + unit tests.
2. `src/riskiUpdate.py` orchestrator with `PhaseResult`/`RunContext`, phase
   adapters, report rendering + unit tests (mocked phases).
3. Integration test (rollback-only DB) for report data collection.
4. Module restructure into `src/update/`/`src/search/` with shims; full test
   suite green.
5. README workflow section updated to the one-command flow.

Rollback: revert the commit — the old per-script workflow remains documented
and functional at every step.

## Open Questions

- Should the orchestrator also prune old snapshots automatically (keep last
  N)? Default: report-only suggestion, pruning stays manual.
