## Why

The existing OParl ingestion pipeline uses MariaDB/MySQL, which lacks native support for vector storage and efficient similarity search. Migrating to PostgreSQL enables the use of `jsonb`, `pgvector` extensions and powerful indexing for embedding vectors while preserving the full OParl data model.

## What Changes

- Add a PostgreSQL‑compatible version of `dbGen.py` (named `dbPgGen.py`).
- Switch the SQLAlchemy engine to use `psycopg2`.
- Replace MySQL‑specific JSON type with PostgreSQL `JSONB`.
- Use `ON CONFLICT DO NOTHING` instead of MySQL `INSERT … IGNORE`.
- Preserve any existing PostgreSQL tables (e.g., vector tables) – the script will only create missing OParl tables or alter existing ones when the OParl schema reports modifications (`modified` timestamps).

## Capabilities

### New Capabilities
- `postgres-migration`: The system SHALL support incremental migration of OParl JSON data into PostgreSQL, creating tables only when absent and updating rows when OParl objects report a newer `modified` timestamp.

### Modified Capabilities
- *none* (the migration adds a new backend; existing capabilities remain unchanged).

## Impact

- Introduces a new Python script in `src/dbPgGen.py`.
- Requires the `psycopg2-binary` (or `psycopg2`) package.
- Existing MariaDB database remains untouched; PostgreSQL can coexist.
- Future components that need embedding vectors can now store them directly in PostgreSQL.
