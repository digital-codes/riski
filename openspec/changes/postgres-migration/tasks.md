## 1. Setup

- [ ] 1.1 Add `psycopg2-binary` (or `psycopg2`) to `requirements.txt`
- [ ] 1.2 Ensure a PostgreSQL database is available locally (default connection parameters) and create it if missing

## 2. Script Migration

- [x] 2.1 Copy `references/postgres/dbGen.py` to `src/dbPgGen.py`
- [x] 2.2 Update imports: replace MySQL JSON with PostgreSQL `JSONB`
- [x] 2.3 Change engine URL to use `postgresql+psycopg2` and read credentials from `private.py`
- [x] 2.4 Replace `INSERT … IGNORE` with SQLAlchemy `insert().on_conflict_do_nothing()` for initial inserts
- [x] 2.5 Add upsert logic: on conflict on `oparlId`, update row only when incoming `modified` is newer
- [x] 2.6 After `metadata.create_all`, run a lightweight migration step that adds any missing scalar columns using `ALTER TABLE … ADD COLUMN IF NOT EXISTS`

## 3. Preserve Existing Tables

- [x] 3.1 Ensure the script never drops tables that are not part of the OParl schema (remove the `DROP_ALL` flag or make it optional)
- [x] 3.2 Add a safety check that only OParl tables (`AgendaItem`, `Body`, …) are created/altered

## 4. Testing & Validation

- [x] 4.1 Write unit tests that verify:
   - New tables are created on a fresh DB
   - Existing rows are updated only when `modified` is newer
   - Custom tables (e.g., `entity_vectors`) remain untouched
- [x] 4.2 Run the script on a sample JSON dump and inspect the PostgreSQL schema
- [x] 4.3 Add CI step to execute the script against a temporary PostgreSQL container

## 5. Documentation

- [x] 5.1 Update README with usage instructions for `dbPgGen.py`
- [x] 5.2 Document environment variables or `private.py` settings for PostgreSQL connection

## 6. Reporting

- [x] 6.1 Write a concise Markdown report summarising the OParl‑to‑PostgreSQL schema mapping and migration steps, and place it in the `docs` folder.

- [x] 5.1 Update README with usage instructions for `dbPgGen.py`
- [x] 5.2 Document environment variables or `private.py` settings for PostgreSQL connection
