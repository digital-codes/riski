# Spec Delta

## MODIFIED Requirements

### Requirement: Incremental update
The incremental updater SHALL crawl the OParl API from the last recorded run state, download new or modified JSON/PDF documents, upsert changed entities, and store the new run state (baseline for the next crawl) in the tracking table. Every crawl run SHALL additionally be recorded in the database: one run row (with timestamps, the crawl baseline, success state and totals) plus a per-element log of every new or modified entity (element type, `oparlId`, `oparlKey`, status `new` or `modified`) and per-type counts of new and modified elements. The `last_run.txt` file SHALL be ignored completely: the tracking table is the sole source of the crawl baseline, and when the table has no rows the updater SHALL fall back to an epoch baseline, fetching everything. The timestamp filter SHALL be applied to **every** crawled collection — using `modifiedSince` where the endpoint supports it (so entities modified after creation are included) and `createdSince` otherwise. When an endpoint provably ignores or rejects the filter, the updater SHALL fall back to fetching that collection in full for the current run, log a warning, and mark the collection as full-fetched in the run record.

#### Scenario: First run records state
- **WHEN** the updater runs and the tracking table has no rows (`last_run.txt` is ignored regardless of its content)
- **THEN** the crawl uses an epoch baseline, fetching everything, and the run is recorded in the table with that baseline and totals

#### Scenario: Second run only fetches changes
- **WHEN** the updater runs again after at least one recorded run and the API reports entities modified after that run's state
- **THEN** only those entities are fetched and upserted, the baseline comes from the latest table row (no file-based state is consulted), and each fetched entity appears in the run's item log with status `new` or `modified`

#### Scenario: All collections are filtered
- **WHEN** an incremental run starts with a tracked baseline
- **THEN** every collection request (papers, agendaItems, meetings, people, consultations, bodies) carries a timestamp filter (`modifiedSince` or `createdSince`), not only the bodies collection

#### Scenario: Modified-after-creation entities are captured
- **WHEN** an entity was created before the baseline but modified after it, and the endpoint supports `modifiedSince`
- **THEN** the entity is fetched and logged with status `modified`

#### Scenario: Endpoint ignoring the filter falls back
- **WHEN** a collection returns the same unfiltered result set despite a timestamp filter (or rejects the request)
- **THEN** the collection is fetched in full for this run, a warning is logged, and the run record marks the collection as full-fetched

## ADDED Requirements

### Requirement: One-command synchronisation
The system SHALL provide a single entry point that performs an incremental crawl followed by importing the fetched data into PostgreSQL (reusing `pgGen`'s additive upsert import), so that one command brings the database from the last tracked baseline to the current API state. The crawl's end state SHALL only be recorded as advanced when the import phase completed successfully.

#### Scenario: Single command updates the database
- **WHEN** the synchronisation entry point runs against a tracked baseline
- **THEN** the incremental crawl fetches changed resources and the import upserts them into PostgreSQL without a separate manual `pgGen` invocation

#### Scenario: Import failure does not advance the baseline
- **WHEN** the import phase fails after a successful crawl
- **THEN** the error is reported, the run row is finished with `success=false`, and the tracking table's end state is not advanced, so the next run re-fetches the same resources
