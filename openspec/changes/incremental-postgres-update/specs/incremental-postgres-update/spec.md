## ADDED Requirements

### Requirement: Incremental PostgreSQL Update
The system SHALL support incremental synchronization of PostgreSQL tables by fetching only records created or modified after a stored cursor timestamp.

#### Scenario: Successful incremental fetch
- **WHEN** the fetch script runs and `last_run.txt` contains a valid timestamp
- **THEN** the script queries OParl endpoints with `?createdSince=<timestamp>` and processes only new or updated records.

#### Scenario: No new records
- **WHEN** there are no records newer than the stored timestamp
- **THEN** the script performs no database writes and updates `last_run.txt` with the current timestamp.

## MODIFIED Requirements

### Requirement: PostgreSQL Fetch Script
The existing `postgres-fetch` script SHALL be updated to accept an optional `createdSince` parameter. When provided, it shall use this parameter to limit fetched data and shall update the timestamp cursor after successful processing.

#### Scenario: Fetch with createdSince
- **WHEN** the script receives a `createdSince` argument
- **THEN** it appends `?createdSince=<value>` to the request URL and processes the returned data accordingly.
