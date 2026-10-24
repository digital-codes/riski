# oparl-import Specification

## Purpose

Covers acquisition of OParl open-data into the `riski_agentic` database: full schema generation/import of OParl entities with relationship and typed-column detection, plus incremental crawling of the Karlsruhe RIS OParl API.

## Requirements

### Requirement: Full schema generation
The schema generator SHALL crawl the OParl API starting from the system root, detect entity types and their relationships, create main tables plus many-to-many association tables (typed scalar columns derived from observed JSON, JSONB payload preserved), and import all discovered entities. Re-runs SHALL detect pre-existing tables and preserve existing data instead of dropping them, recording a preservation snapshot of what was found.

#### Scenario: Import into empty database
- **WHEN** the generator runs against a database without OParl tables and a reachable OParl endpoint
- **THEN** main and association tables for the OParl entity types exist and contain the imported entities with their `oparlKey`/`oparlId` and JSON payload

#### Scenario: Re-import preserves data
- **WHEN** the generator is run a second time on a database that already contains imported entities
- **THEN** existing rows are preserved (not dropped) and the run reports the preserved state

### Requirement: Project schema maintenance
The generator SHALL be able to ensure the project's own tables and indexes (streets, districts, content embeddings and related semantic-layer tables) exist without importing OParl data, via a schema-only mode.

#### Scenario: Schema-only migration
- **WHEN** the generator runs in schema-only mode against a database lacking the project tables
- **THEN** the project tables and indexes are created and no OParl crawling happens

### Requirement: Incremental update
The incremental updater SHALL crawl the OParl API from the last recorded run state, download new or modified JSON/PDF documents, upsert changed entities, and store the new run state (baseline for the next crawl) in the tracking table. Every crawl run SHALL additionally be recorded in the database: one run row (with timestamps, the crawl baseline, success state and totals) plus a per-element log of every new or modified entity (element type, `oparlId`, `oparlKey`, status `new` or `modified`) and per-type counts of new and modified elements. The `last_run.txt` file SHALL be ignored completely: the tracking table is the sole source of the crawl baseline, and when the table has no rows the updater SHALL fall back to an epoch baseline, fetching everything. The timestamp filter SHALL be applied to **every** crawled collection — using the OParl 1.1 spelling `modified_since` (so entities modified after creation are included; the API silently ignores the camelCase variant) with `created_since` as fallback, requesting large page sizes. Every fetched collection page SHALL be validated against the baseline: an honouring filter can never return items older than it, so a violating page triggers the fallback chain (next filter parameter, then a full fetch), and the run record SHALL mark full-fetched collections (`full_fetches`). Per the OParl 1.1 update mechanism, only the filtered collections, their pagination and PDF downloads SHALL be fetched — resource references inside items SHALL NOT be dereferenced (all entity types are covered by their collections).

#### Scenario: First run records state
- **WHEN** the updater runs and the tracking table has no rows (`last_run.txt` is ignored regardless of its content)
- **THEN** the crawl uses an epoch baseline, fetching everything, and the run is recorded in the table with that baseline and totals

#### Scenario: Second run only fetches changes
- **WHEN** the updater runs again after at least one recorded run and the API reports entities modified after that run's state
- **THEN** only those entities are fetched and upserted, the baseline comes from the latest table row (no file-based state is consulted), and each fetched entity appears in the run's item log with status `new` or `modified`

#### Scenario: All collections are filtered
- **WHEN** an incremental run starts with a tracked baseline
- **THEN** every collection request (consultations, papers, agendaItems, meetings, people, files, memberships, organizations, locations, bodies) carries a timestamp filter (`modified_since` or `created_since`), not only the bodies collection

#### Scenario: Resource references are not dereferenced
- **WHEN** a fetched collection page contains URLs of unchanged resources
- **THEN** only pagination links and PDF downloads are enqueued; individual resource references are not fetched (the filtered collections cover all entity types)

#### Scenario: Modified-after-creation entities are captured
- **WHEN** an entity was created before the baseline but modified after it, and the endpoint supports `modifiedSince`
- **THEN** the entity is fetched and logged with status `modified`

#### Scenario: Endpoint ignoring the filter falls back
- **WHEN** a collection returns the same unfiltered result set despite a timestamp filter (or rejects the request)
- **THEN** the collection is fetched in full for this run, a warning is logged, and the run record marks the collection as full-fetched

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

### Requirement: One-command synchronisation
The system SHALL provide a single entry point that performs an incremental crawl followed by importing the fetched data into PostgreSQL (reusing `pgGen`'s additive upsert import), so that one command brings the database from the last tracked baseline to the current API state. The crawl's end state SHALL only be recorded as advanced when the import phase completed successfully.

#### Scenario: Single command updates the database
- **WHEN** the synchronisation entry point runs against a tracked baseline
- **THEN** the incremental crawl fetches changed resources and the import upserts them into PostgreSQL without a separate manual `pgGen` invocation

#### Scenario: Import failure does not advance the baseline
- **WHEN** the import phase fails after a successful crawl
- **THEN** the error is reported, the run row is finished with `success=false`, and the tracking table's end state is not advanced, so the next run re-fetches the same resources
