## Why

Stakeholders need an up‑to‑date, single‑source report that summarises the RISKI project's data ingestion pipeline, migration status, and any open tasks. Such a report improves transparency, aids decision‑making, and provides a basis for future planning.

## What Changes

- Add a new **RISKI Report** capability that produces a Markdown document aggregating:
  - OParl → PostgreSQL schema mapping overview
  - Status of the PostgreSQL migration (`postgres-migration` change)
  - Current list of open issues and next steps
- The report will be generated under the `docs/` directory as `pg_report.md`.

## Capabilities

### New Capabilities
- `riski-report`: The system SHALL generate a comprehensive Markdown report covering schema mapping, migration status, and future work.

### Modified Capabilities
- *none*

## Impact

- Introduces a new documentation artifact (`docs/pg_report.md`).
- No code changes required beyond generating the report file.
