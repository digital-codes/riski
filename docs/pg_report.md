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

### Create vector extension

create extension vector;


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


## Appendix B - Interactive commands 

### start psql
> psql postgresql://<usr>:<pwd>@localhost/<db>

### connect
> \c <db>

### list schemas
> \d

=> normally tables are in schema "public"

### Table naming

double quotes seem to be required here like:

> select * from "Consultation" limit 10;

Why is that?

``` 
    PostgreSQL folds unquoted identifiers to lower‑case.
    If a table was created like

    CREATE TABLE "Body" ( … );
    the name is stored exactly as Body (capital B).
    When you later write

    SELECT * FROM Body;
    PostgreSQL rewrites it to body (all lower‑case), which does not match the real object, so you get

    ERROR:  relation "body" does not exist
    The only way to refer to that exact mixed‑case name is with double quotes:

    SELECT * FROM public."Body";

``` 

### Export

Structure only:
> pg_dump -U <user> -W -d <db> -s -f <db>_struct.sql -h localhost

Leave out *-s* to dump data as well.

### Import 

sudo -u postgres psql  -d <created dabase>  -f sql_from_export.sql

### Add read only user
-- 1. Connect to DB
GRANT CONNECT ON DATABASE target_db TO readonly_user;

-- 2. Schema access
GRANT USAGE ON SCHEMA public TO readonly_user;

-- 3. Existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- 4. Future tables (run as the owner of the tables!!!)
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT SELECT ON TABLES TO readonly_user;



