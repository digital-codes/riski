## Why

The current data ingestion pipeline loads full data snapshots into PostgreSQL on each run, which is inefficient and can cause unnecessary load and downtime. Incremental updates reduce data transfer, improve performance, and enable near‑real‑time data availability.

## What Changes

- Add an incremental update process for PostgreSQL that only processes new or changed records since the last successful run.
- Introduce a timestamp tracking mechanism stored in a file.
- Update the existing fetch script to use `?createdSince=` queries when supported.
- Ensure safe shutdown handling to persist progress on interruption.

## Capabilities

### New Capabilities
- `incremental-postgres-update`: The system SHALL support incremental synchronization of PostgreSQL tables by fetching only records created or modified after a stored cursor timestamp.

### Modified Capabilities
- `postgres-fetch`: Updated to accept an optional `createdSince` parameter and to write files only when newer data is present.

## Impact

- Modifies the data ingestion scripts used in the CI pipeline.
- Adds a new state file (`last_run.txt`) to the project root.
- May require database administrators to verify that timestamp columns exist and are indexed for efficient queries.
