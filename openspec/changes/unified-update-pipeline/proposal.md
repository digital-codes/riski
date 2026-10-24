# Proposal

## Why

Updating the database currently means running seven+ scripts in the right order
with the right flags and environment (`syncIncremental`, `pgOcr`, `pgSummarize`,
`pgAddSummaries --embed-missing`, `pgTeasers` with LLM env vars, three geo-ref
scripts, `pgCategorise`, `pgCoverage`) — easy to get wrong, no automatic
backup, no rollback when a step fails mid-way, and no single report of what the
run actually changed. The 2026-10-24 data update had to be coordinated by hand
across several sessions.

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
- **Phase granularity**: each phase is individually skippable/selectable
  (`--phases sync,enrich` / `--skip enrich`) and resumable — a re-run skips
  completed work by design (all sub-steps are idempotent).
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
  and selection, pre-run snapshot with verification, snapshot restore on
  failure, and the run report.

### Modified Capabilities

(none — `oparl-import` and `data-enrichment` behaviour is unchanged; the
orchestrator only composes existing, already-specified behaviour)

## Impact

- **Code**: new `src/riskiUpdate.py` (orchestrator) + `src/db/db_snapshot.py`
  (snapshot/restore/report helpers); existing scripts gain nothing more than
  being moved into `src/update/` (re-export shims at their old paths). Reuses:
  `syncIncremental.sync()`, `pgOcr.run()`, `pgSummarize._run_summarizer()`,
  `pgAddSummaries.main()`, `pgTeasers.main()`, `pgAddFileGeoRefs.run()`,
  `pgCategorise.main()`, `pgCoverage`, `oparlRunLog` stats.
- **Database**: no schema changes. Snapshots land in the existing
  `/mnt_ai/data/riski/snapshots/` directory.
- **Risk**: `pg_restore` rollback must be defensive (never drop the live DB
  before a verified restore target exists); LLM-dependent phases can be
  long-running — the report must show per-phase timing and exit codes.
- **Tests**: unit tests for phase sequencing/skip logic and the report;
  integration test (rollback-only) for the report data collection; snapshot
  helpers tested against a scratch database.
