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
- Criticality-based failure handling: sync stops the run, enrichment phases
  continue past failures; failed items retry next run.
- Per-File stage ledger so per-item failure/retry/empty status is explicit
  and observable.
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

**D4 — Snapshot is a manual recovery point, not an auto-rollback.**
(Amended 2026-10-25.) The pipeline heals by retrying: all steps are
idempotent and only mark done work that succeeded, so the next run re-processes
exactly the failed items. An unattended `pg_restore` swap is the wrong default —
it discards hours of enrichment work and adds its own failure mode. On a
critical (sync) failure the run stops and the report prints the restore
command; the restore helpers (D3) stay available for the operator. Rationale:
the baseline already refuses to advance on import failure
(`syncIncremental.set_end_state`), so a failed sync leaves a consistent
database — there is nothing to roll back to.

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

**D8 — Criticality classes on phases.** Each phase declares
`critical: true|false`. Critical phases (snapshot, sync) stop the run on
failure; best-effort phases (ocr, summaries, content, teasers, geo, tags)
record the failure in the report and let the remaining phases run. The run
exit code distinguishes: 0 = all done, 1 = critical failure, 2 = partial
(enrichment failures present). Alternative: fail-fast everywhere — rejected
because a nightly OCR outage would then also block summaries, teasers, geo
and tags of *already-OCR'd* material, multiplying the damage of a single
backend outage.

**D9 — Per-File stage ledger.** A dedicated table (provisional name
`file_stage_status`: file key, stage, status, reason, attempts, updated_at;
PK (file, stage), created on demand) records per-item outcomes. Each phase
adapter marks items `done`, `failed` (with error reason, attempts+1) or
`empty` (terminal, with reason: e.g. no extractable text, no streets
matched, document too short for a teaser). The adapter for a stage processes
only files whose ledger row for that stage is missing or `failed`. Existing
scripts already behave this way implicitly (pgOcr skips existing markdown,
summaries skip existing rows) — the ledger makes it explicit, queryable, and
reportable. Alternative: derive status from the data itself (missing summary
= retry) — kept as the fallback for backfill, but rejected as the primary
mechanism because "empty with good reason" (e.g. OCR of a blank scan) is
indistinguishable from "failed" without a ledger, so failures would either
retry forever or be misread as complete.

**D10 — Cron-safe execution.** Exclusive-run lock via `flock` on a lockfile
(second invocation exits 0 with a log line — overlapping nightly runs must
never corrupt each other); per-phase timeout via `subprocess`-style deadline
in the orchestrator (a hung LLM call cannot block the next day's run — the
phase is recorded as failed/timeout and retried next run); exit codes per
D8 so a cron wrapper can mail only on 1/2.

## Risks / Trade-offs

- [Long LLM phases block the report] → report is written incrementally
  (re-rendered after every phase), so a killed run still leaves a useful
  report.
- [Stage ledger can drift from reality (a summary exists but ledger says
  failed)] → stage adapters reconcile on startup: an item whose ledger row
  says `failed`/`pending` but whose data already satisfies the stage is
  marked `done` without reprocessing (the existing idempotency checks are
  the reconciler's source of truth). Worst case, a lost ledger row causes
  redundant-but-harmless rework, never data corruption.
- [`pgTeasers.main()` hard-exits / uses its own arg parsing] → adapter wraps
  in try/except SystemExit and sets argv explicitly.
- [Restore swap needs exclusive access] → documented: stop the API/app during
  a manual rollback; the restore helper terminates connections via
  `pg_terminate_backend` before rename. Restore remains a manual,
  operator-invoked step (D4).
- [Snapshot size (~680 MB per run)] → retention: keep the last N snapshots
  (N configurable, default 5) — pruning is manual by default.
- [Module moves can break third-party references] → shims + full test suite
  run before/after the move.
- [Poison items (permanent failures) retry every night] → acceptable by
  design (cheap idempotent re-checks); the report surfaces items with
  attempts ≥ threshold (default 3) so the operator can intervene; repeated
  failures never mark a stage done.

## Migration Plan

1. `src/db/db_snapshot.py` (snapshot/verify/restore/swap) + unit tests.
2. Stage ledger helper (table + accessors + reconcile logic) + unit tests.
3. `src/riskiUpdate.py` orchestrator with `PhaseResult`/`RunContext`,
   criticality classes, phase adapters (item-outcome recording into the
   ledger), report rendering + unit tests (mocked phases).
4. Integration test (report data collection + ledger transitions) for
   report data collection.
5. Module restructure into `src/update/`/`src/search/` with shims; full test
   suite green.
6. README workflow section updated to the one-command flow + cron entry
   example (`flock`, exit codes, report path).

Rollback: revert the commit — the old per-script workflow remains documented
and functional at every step.

## Open Questions

- Should the orchestrator also prune old snapshots automatically (keep last
  N)? Default: report-only suggestion, pruning stays manual.
