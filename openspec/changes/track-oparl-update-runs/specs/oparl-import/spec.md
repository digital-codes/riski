# Spec Delta

## MODIFIED Requirements

### Requirement: Incremental update
The incremental updater SHALL crawl the OParl API from the last recorded run state, download new or modified JSON/PDF documents, upsert changed entities, and store the new run state (baseline for the next crawl) in the tracking table. Malformed URLs from the API SHALL be fixed before download where the API deviates from the documented format. Every crawl run SHALL additionally be recorded in the database: one run row (with timestamps, the crawl baseline, success state and totals) plus a per-element log of every new or modified entity (element type, `oparlId`, `oparlKey`, status `new` or `modified`) and per-type counts of new and modified elements. The `last_run.txt` file SHALL be ignored completely: the tracking table is the sole source of the crawl baseline, and when the table has no rows the updater SHALL fall back to an epoch baseline, fetching everything.

#### Scenario: First run records state
- **WHEN** the updater runs and the tracking table has no rows (`last_run.txt` is ignored regardless of its content)
- **THEN** the crawl uses an epoch baseline, fetching everything, and the run is recorded in the table with that baseline and totals

#### Scenario: Second run only fetches changes
- **WHEN** the updater runs again after at least one recorded run and the API reports entities modified after that run's state
- **THEN** only those entities are fetched and upserted, the baseline comes from the latest table row (no file-based state is consulted), and each fetched entity appears in the run's item log with status `new` or `modified`

## ADDED Requirements

### Requirement: Run tracking tables
The system SHALL maintain additive tracking tables for crawl runs: `oparlUpdateRuns` (one row per run: timestamp, start/end, baseline, success flag, totals), `oparlUpdateRunItems` (one row per new/modified element: run reference, element type, `oparlId`, `oparlKey`, status `new`/`modified`), and per-run, per-type summary counts (`new_count`, `modified_count`). The tables SHALL be created automatically if missing and SHALL be readable by the read-only role.

#### Scenario: Tables created on first tracked run
- **WHEN** the updater runs against a database without the tracking tables
- **THEN** both tables are created and the run's rows are inserted

#### Scenario: New and modified elements are distinguishable
- **WHEN** a run fetches a resource whose output file did not exist and another whose stored copy is older than the fetched version
- **THEN** the item log contains a row with status `new` for the first and status `modified` for the second, and the per-type summary reflects both counts

#### Scenario: Run without database access reports the failure
- **WHEN** the database is unreachable during a crawl
- **THEN** the crawl completes its fetches with an epoch baseline, the missing run record is clearly reported (error, not silent), and the next run retries baseline resolution from the table

#### Scenario: Counts per type are queryable
- **WHEN** a run recorded 3 new and 2 modified `Paper` elements
- **THEN** the summary row for that run and type shows `new_count = 3` and `modified_count = 2` without requiring aggregation over the item log
