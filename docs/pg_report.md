# OParl → PostgreSQL Migration Report

## Overview
This report summarizes how the OParl data model is mapped to a PostgreSQL schema and details the migration script (`src/dbPgGen.py`). The goal is to replace the existing MariaDB ingestion pipeline with PostgreSQL, enabling native vector storage (`pgvector`) and powerful `jsonb` indexing while preserving any custom tables that may already exist in the target database.

## 1. Schema Mapping

| OParl Entity | PostgreSQL Table | Key Columns | Relationships |
|--------------|------------------|------------|---------------|
| `System` | `System` | `sid` (PK), `oparlId` (unique), `oparlKey`, `type`, `created`, `modified`, `data` (jsonb) | None (top‑level) |
| `Body` | `Body` | same as above + `systemSid` (FK → `System`) | FK to `System` |
| `LegislativeTerm` | `LegislativeTerm` | same + `bodySid` (FK → `Body`) | FK to `Body` |
| `Organization` | `Organization` | same + `bodySid` (FK → `Body`) | FK to `Body` |
| `Person` | `Person` | same + `bodySid` (FK → `Body`), `locationSid` (FK → `Location`) | FK to `Body`, `Location` |
| `Membership` | `Membership` | same + `organizationSid` (FK → `Organization`), `personSid` (FK → `Person`) | FK to `Organization`, `Person` |
| `Meeting` | `Meeting` | same | Many‑to‑many via association tables (e.g., `Meeting__agendaItem__AgendaItem`). |
| `AgendaItem` | `AgendaItem` | same + `meetingSid` (FK → `Meeting`), `consultationSid` (FK → `Consultation`) | FK to `Meeting`, `Consultation` |
| `Paper` | `Paper` | same + `bodySid` (FK → `Body`) | FK to `Body` |
| `Consultation` | `Consultation` | same + `meetingSid`, `paperSid`, `agendaItemSid` (FKs) | FK to `Meeting`, `Paper`, `AgendaItem` |
| `File` | `File` | same + fields `accessUrl`, `downloadUrl`, `mimeType`, `content` | No direct FKs; linked via association tables. |
| `Location` | `Location` | same + address fields (`description`, `locality`, `postalCode`, …) | No direct FKs. |

**Scalar Columns** – Top‑level scalar attributes that are not relationships are added as explicit columns (e.g., `Person.givenName`, `File.mimeType`). Column names are sanitized (`safe_col_name`) and quoted when they clash with PostgreSQL reserved words.

**Association Tables** – Every many‑to‑many list from OParl becomes an association table named `<src>__<field>__<tgt>` with composite primary key (`srcSid`, `tgtSid`).

## 2. Migration Script (`src/dbPgGen.py`)

1. **Engine Configuration** – Uses `postgresql+psycopg2` URL from `private.py`.
2. **JSON Storage** – Stores the raw OParl payload in a `jsonb` column (`data`).
3. **Upsert Logic** – Inserts rows with `ON CONFLICT (oparlId) DO UPDATE` and updates only when the incoming `modified` timestamp is newer. This ensures incremental updates without data loss.
4. **Schema Creation** – `metadata.create_all(engine)` creates missing tables only; existing tables (including custom vector tables) are left untouched.
5. **Scalar Column Migration** – After initial creation, the script adds any newly discovered scalar columns using `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.
6. **Foreign‑Key Population** – A second pass populates `<field>Sid` columns using the `oparlId → sid` map built after the base insert.
7. **Association Insertion** – Populates many‑to‑many association tables, also using `ON CONFLICT DO NOTHING` to avoid duplicates.

## 3. Preserving Custom Tables
The script never drops tables (`DROP_ALL` is forced to `False`). A safety check ensures that only tables listed in the OParl schema are created or altered. Custom tables such as `entity_vectors` remain untouched.

## 4. Testing & Validation
* Unit tests verify creation on a fresh DB, proper upserts when `modified` changes, and that unrelated tables are not affected.
* CI integrates the script into a temporary PostgreSQL container to guarantee repeatable builds.

## 5. Next Steps
* Add GIN indexes on the `data` column for fast OParl‑specific queries.
* Extend the script to support bulk vector insertion into a `pgvector`‑enabled table.
* Keep the documentation (`README.md`) updated with usage examples and required `private.py` settings.

---
*Generated as part of the `postgres-migration` OpenSpec change.*

## Appendix A – Creating the PostgreSQL database & user

### 1️⃣ Switch to the PostgreSQL system account
```bash
sudo -i -u postgres
```

### 2️⃣ Start psql
```bash
psql
```

### 3️⃣ Create a role (user)
```sql
CREATE ROLE riski_user WITH
    LOGIN
    PASSWORD 'StrongPassword!123'
    CREATEDB;
```

### 4️⃣ Create the database
```sql
CREATE DATABASE riski
    OWNER riski_user
    ENCODING 'UTF8'
    LC_COLLATE 'en_US.UTF-8'
    LC_CTYPE   'en_US.UTF-8'
    TEMPLATE   template0;
```

### 5️⃣ Grant privileges
```sql
GRANT ALL PRIVILEGES ON DATABASE riski TO riski_user;
\c riski
GRANT ALL PRIVILEGES ON SCHEMA public TO riski_user;
```

### 6️⃣ Verify the connection
```bash
psql postgresql://riski_user:StrongPassword!123@localhost/riski
```

### 7️⃣ Use in RISKI
Add to `private.py`:
```python
DB_USER = 'riski_user'
DB_PWD  = 'StrongPassword!123'
DB_NAME = 'riski'
```

*These steps are safe for local development and give the user just enough rights to let `src/dbPgGen.py` create tables and upsert data while preserving any custom tables (e.g., `entity_vectors`).*