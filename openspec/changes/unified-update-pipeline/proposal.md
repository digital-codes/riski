# Proposal

## Why

Updating the database currently means running seven+ scripts in the right order
with the right flags and environment (`syncIncremental`, `pgOcr`, `pgSummarize`,
`pgAddSummaries --embed-missing`, `pgTeasers` with LLM env vars, three geo-ref
scripts, `pgCategorise`, `pgCoverage`) — easy to get wrong, no automatic
backup, no rollback when a step fails mid-way, and no single report of what the
run actually changed. The 2026-10-24 data update had to be coordinated by hand
across several sessions.

Amended 2026-10-25 after ops review: the auto-rollback idea (`pg_restore` on
any phase failure) is replaced by a retry-on-next-run philosophy — the
pipeline is additive and idempotent by design, so a per-item failure (e.g. one
OCR step) must neither block the rest of the run nor be marked done; it is
simply retried next run. A per-File stage ledger makes this explicit and
observable.

## What Changes

- **One command, `python src/riskiUpdate.py` (or `python -m src.riskiUpdate`)**,
  that executes the complete update as a sequence of phases:
  1. **Snapshot** — `pg_dump -Fc` the database to `/mnt_ai/data/riski/snapshots/`
     (verified with `pg_restore --list`) before anything is written.
  2. **Sync** — incremental crawl + `pgGen` import (reuses `syncIncremental`,
     which already guarantees the baseline only advances after a successful import).
  3. **Enrich** — OCR missing PDFs (`pgOcr`), summarise new markdown
     (`pgSummarize`), update `File.content` + targeted embeddings
     (`pgAddSummaries --embed-missing`), teasers (`pgTeasers`), geo references
     (`pgAddFileGeoRefs --prune`, `pgAddStreetRefs`, `pgAddDistrictRefs`),
     tags (`pgCategorise all`) — every step idempotent and resumable.
  4. **Report** — a markdown run report (per-phase stats, row deltas, tag/geo
     counts, coverage numbers, errors) written next to the snapshot.
  5. **Rollback on failure** — if any phase fails irrecoverably, restore the
     pre-run snapshot (`pg_restore` into a fresh database after rename/drop)
     and record the failure in the report.
- **Phase criticality** (amended 2026-10-25, after ops review): `sync`
  (crawl + import) is **critical** — on its failure the run stops and reports
  (the tracked baseline already stays put, so the next run re-fetches the
  window). All enrichment phases (OCR, summaries, content, teasers, geo,
  tags) are **best-effort** — a failure in one phase (e.g. OCR) is recorded
  and the run continues with the remaining phases. The pipeline heals by
  **retrying on the next run**, not by rolling back: every step is idempotent
  and only marks work done that actually succeeded, so failed items are
  picked up again automatically.
- **Per-File stage tracking** — every File advances through stages (OCR →
  summary → content+embeddings → teaser → geo → tags) tracked in a per-item
  ledger: a stage ends in `done`, `failed` (retried next run), or `empty`
  (terminal, with a recorded reason — e.g. no extractable text, no streets
  matched). A File's enrichment is complete when every stage is `done` or
  `empty`; the report lists failed stages and repeat offenders. See the new
  `enrichment-stage-tracking` capability.
- **Phase granularity**: each phase is individually skippable/selectable
  (`--phases sync,enrich` / `--skip enrich`) and resumable — a re-run skips
  completed work by design (all sub-steps are idempotent).
- **Cron contract**: safe for unattended daily invocation — an exclusive-run
  lock (overlapping invocations exit early), per-phase timeouts (a hung LLM
  phase cannot block the next day's run), and exit codes that mail(1) can act
  on (0 = all stages done, 1 = critical failure, 2 = partial success with
  failed stages).
- **Snapshot recovery, not auto-rollback** (amended 2026-10-25): the snapshot
  is a manual recovery point for the operator, not an automatic rollback. The
  restore helpers (verified restore target, rename swap) remain available and
  documented; the pipeline itself never drops or replaces the live database
  unattended — additive/idempotent re-runs are the recovery mechanism.
- **Cleaner module structure** with an obvious separation of concerns:
  - `src/update/` — acquisition & enrichment pipeline (`oparlUpdate`,
    `syncIncremental`, `pgOcr`, `pgSummarize`, `pgAddSummaries`, `pgTeasers`,
    `pgAddFileGeoRefs`, `pgAddStreetRefs`, `pgAddDistrictRefs`, `pgCategorise`,
    `riskiUpdate`, plus the shared `update_report` helper)
  - `src/db/` — database utilities (already exists; gains the snapshot/restore
    helpers `db_snapshot.py`)
  - `src/search/` — search & analysis surface (`pgVecSearch`, `pgHybridSearch`,
    `pgTimeline`, `pgFileQuery`, `graphModel`, `pgResultSummarizer`,
    `apiServer`, `local_geo_matching`)
  - **No breakage**: top-level `src/pg*.py` modules become thin re-export
    shims (`from src.update.pgOcr import *` style) so existing command lines,
    tests and cross-imports keep working.
- **Docs**: the README "Data update workflow" section is updated to the
  one-command flow (the manual step list remains documented as the underlying
  phases).

## Capabilities

### New Capabilities

- `update-orchestration`: the one-command update pipeline — phase execution
  and selection with criticality classes, pre-run snapshot with verification,
  manual snapshot-restore tooling, cron-safe operation (lock, timeouts, exit
  codes), and the run report.
- `enrichment-stage-tracking`: the per-File stage ledger — per-item status
  (`done`/`failed`/`empty` with reason) for every enrichment stage, driving
  retry-on-next-run and the coverage/poison-item reporting.

### Modified Capabilities

(none — `oparl-import` and `data-enrichment` behaviour is unchanged; the
orchestrator only composes existing, already-specified behaviour)

## Impact

- **Code**: new `src/riskiUpdate.py` (orchestrator) + `src/db/db_snapshot.py`
  (snapshot/restore/report helpers) + a stage-ledger helper module (per-File
  stage status table + accessors); existing scripts gain nothing more than
  being moved into `src/update/` (re-export shims at their old paths). Reuses:
  `syncIncremental.sync()`, `pgOcr.run()`, `pgSummarize._run_summarizer()`,
  `pgAddSummaries.main()`, `pgTeasers.main()`, `pgAddFileGeoRefs.run()`,
  `pgCategorise.main()`, `pgCoverage`, `oparlRunLog` stats.
- **Database**: one new on-demand table for the stage ledger (per-File, per-
  stage status). Snapshots land in the existing
  `/mnt_ai/data/riski/snapshots/` directory.
- **Risk**: enrichment phases that partially fail must leave no false "done"
  marks — the stage ledger is the source of truth, so each phase adapter must
  record item outcomes, not just phase-level exit codes; LLM-dependent phases
  can be long-running — per-phase timeouts and the incrementally re-rendered
  report keep cron runs bounded.
- **Tests**: unit tests for phase sequencing/skip/criticality logic, the stage
  ledger state machine, and the report; integration test for report data
  collection; snapshot helpers tested against a scratch database.
