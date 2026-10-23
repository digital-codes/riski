## ADDED Requirements

### Requirement: RISKI Report Generation
The system SHALL generate a Markdown report (`docs/pg_report.md`) that aggregates the OParl → PostgreSQL schema mapping, the status of the `postgres-migration` change, and a list of open issues and next steps for the RISKI project.

#### Scenario: Generate up‑to‑date report
- **WHEN** the script `src/generate_report.py` is executed
- **THEN** a file `docs/pg_report.md` is created or overwritten containing the combined sections:
  - Schema overview (copied from `docs/pg_report.md` existing content)
  - Migration status (derived from `openspec/changes/postgres-migration/tasks.md`)
  - Open issues summary (hard‑coded list or read from a TODO file)
