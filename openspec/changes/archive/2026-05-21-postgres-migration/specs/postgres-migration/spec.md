## ADDED Requirements

### Requirement: PostgreSQL Migration for OParl
The system SHALL support migrating OParl JSON data into a PostgreSQL database, creating tables only when they do not exist and updating rows when the source object reports a newer `modified` timestamp. Existing PostgreSQL tables that are not part of the OParl schema (e.g., vector tables) MUST remain untouched.

#### Scenario: Fresh PostgreSQL instance
- **WHEN** the script is executed against an empty PostgreSQL database
- **THEN** it creates all OParl tables and inserts every entity from the JSON files.

#### Scenario: Incremental update with modifications
- **WHEN** an OParl object with the same `oparlId` already exists but the incoming JSON has a newer `modified` timestamp
- **THEN** the script updates the existing row with the new scalar fields and refreshed `data` JSON.

#### Scenario: Existing custom tables are preserved
- **WHEN** the PostgreSQL database already contains tables unrelated to OParl (e.g., `entity_vectors`)
- **THEN** the script does not drop or alter those tables.
