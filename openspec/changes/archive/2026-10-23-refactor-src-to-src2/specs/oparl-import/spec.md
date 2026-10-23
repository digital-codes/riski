# Spec Delta

## Purpose

Covers acquisition of OParl open-data into the `riski_agentic` database: full schema generation/import of OParl entities with relationship and typed-column detection, plus incremental crawling of the Karlsruhe RIS OParl API.

## ADDED Requirements

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
The incremental updater SHALL crawl the OParl API from the last recorded run state, download new or modified JSON/PDF documents, upsert changed entities, and persist the new run timestamp so the next run starts from it. Malformed URLs from the API SHALL be fixed before download where the API deviates from the documented format.

#### Scenario: First run records state
- **WHEN** the updater runs with no previous run state
- **THEN** it crawls from the configured start point and writes a run-state file with the current time

#### Scenario: Second run only fetches changes
- **WHEN** the updater runs again with valid run state and the API reports entities modified after that state
- **THEN** only those entities are fetched and upserted, and the run state advances
