# Proposal

## Why

Incremental OParl updates currently leave only a single `last_run.txt` timestamp behind — there is no durable record of *when* data was fetched, *what* changed (new vs. modified), or *which* entities were affected. Diagnosing crawl problems, auditing data freshness, or building "what's new since my last visit" features is impossible without parsing the raw JSON output folders. A database-backed run log closes this gap.

## What Changes

- **New tracking tables** in the `riski_agentic` database (owned by this project, like `Street`/`District`):
  - `oparlUpdateRuns` — one row per crawl run: run timestamp, start/end time, crawl baseline (`createdSince` value), success state, and total new/modified counts.
  - `oparlUpdateRunItems` — one row per fetched element that was new or modified: element type (class, e.g. `Meeting`), `oparlId`, `oparlKey`, status (`new` | `modified`), and the run it belongs to.
  - Per-run/per-type counts (`new_count`, `modified_count`) are stored alongside the item log (aggregated summary per run and type) so the "number of new and modified elements by type" is directly queryable without recomputation.
- **Crawler integration**: `oparlUpdate` records each run and every new/modified resource into these tables at fetch time, using the shared DB layer. PDF downloads and failed fetches are recorded in the run row (no item rows).
- **Run state moves to the database**: the new `oparlUpdateRuns` table becomes the sole source of the crawl baseline. `last_run.txt` is ignored completely (no reads, no writes, no fallback logic). The table is seeded once with a baseline of **19 Feb 2026 (CET)**; an empty table means "fetch everything" (epoch baseline).
- **Failure safety**: DB logging failures must be handled carefully — the run state lives in the DB, so a failing write surfaces a clear error instead of silently losing the baseline; the crawl itself still completes.
- **Verification discipline**: database writes during test/verification happen only inside transactions that are rolled back; no real crawl sessions are run as part of testing.
- **Idempotence**: re-running tracking insertion for the same run does not duplicate rows (run identity by start timestamp).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `oparl-import`: the incremental-update requirement gains a companion behaviour — every crawl run MUST be recorded in the database (run metadata, per-type new/modified counts, and a per-element log of new/modified entities).

## Impact

- **Code**: `src/oparlUpdate.py` (run/item recording; new tracking module, e.g. `src/oparlRunLog.py`), tests in `src/tests/`.
- **Database**: two new tables created additively (via `ensure_project_schema`-style logic so existing databases gain them on next run); no changes to existing tables.
- **Risk**: crawl runs without DB connectivity still succeed (best-effort logging); the read-only role gains SELECT visibility on the new tables.
- **Specs**: delta on `oparl-import` only.
