# RISKI – OParl Full Report

## 1. OParl fundamentals
OParl is a standardized, JSON‑based web API that provides read‑only access to parliamentary information systems. It defines a fixed set of object types (`System`, `Body`, `LegislativeTerm`, `Organization`, `Person`, `Membership`, `Meeting`, `AgendaItem`, `Paper`, `Consultation`, `File`, `Location`). Each object has required fields (`id`, `type`, `created`, `modified`) and optional attributes. The specification mandates canonical URLs, pagination, and filter parameters (`createdSince`, `modifiedSince`, `omit_internal`).

## 2. Accessing resources
A typical OParl endpoint is `https://example.org/oparl/v1.1/`. Resources are reachable via collection URLs, e.g. `/meeting`, `/person`. Filters allow incremental crawling:
```
GET https://example.org/oparl/v1.1/meeting?createdSince=2024-01-01T00:00:00Z&limit=100
```
The response contains a `data` array, a `pagination` object, and `links.next` for further pages.

## 3. Data‑model sketch (PostgreSQL)
The migration maps each OParl entity to a PostgreSQL table. Below is a concise excerpt (see `docs/pg_report.md` for the full mapping):

| OParl Entity | PostgreSQL Table | Key columns | Relationships |
|--------------|------------------|------------|---------------|
| `System` | `System` | `sid` (PK), `oparlId` (unique), `oparlKey`, `type`, `created`, `modified`, `data` (jsonb) | – |
| `Body` | `Body` | same + `systemSid` (FK → `System`) | FK to `System` |
| `Person` | `Person` | same + `bodySid` (FK → `Body`), `locationSid` (FK → `Location`) | FK to `Body`, `Location` |
| `Meeting` | `Meeting` | same | Many‑to‑many via association tables (e.g. `Meeting__agendaItem__AgendaItem`) |
| `File` | `File` | same + `accessUrl`, `downloadUrl`, `mimeType`, `content` | Linked via association tables |

Scalar attributes (e.g. `Person.givenName`) are added as explicit columns; many‑to‑many lists become association tables named `<src>__<field>__<tgt>`.

## 4. Incremental OParl update (archived change)
The archived `incremental-oparl-update` change introduced a timestamp‑based crawler (`src/oparl_update.py`). It stores the last successful run in `last_run.txt` and uses the `createdSince` filter to fetch only new or modified objects, reducing bandwidth and processing time. Graceful SIGINT handling ensures the cursor is persisted on interruption.

## 5. PostgreSQL migration (excerpt)
* **Engine** – `postgresql+psycopg2` via SQLAlchemy.
* **JSON storage** – raw OParl payload stored in a `jsonb` column (`data`).
* **Upsert logic** – `INSERT … ON CONFLICT (oparlId) DO UPDATE` updates rows only when the incoming `modified` timestamp is newer.
* **Schema creation** – `metadata.create_all()` creates missing tables; existing custom tables (e.g., `entity_vectors`) are left untouched.
* **Scalar‑column migration** – missing scalar columns are added with `ALTER TABLE … ADD COLUMN IF NOT EXISTS` after the initial schema creation.

These mechanisms make the ingestion pipeline idempotent and ready for vector‑based extensions.

## 6. Conclusions
The RISKI project now has:
* A clear description of the OParl API and how to retrieve data incrementally.
* A PostgreSQL data model that mirrors the OParl schema while supporting scalar columns and many‑to‑many relationships.
* An efficient incremental crawler and a robust migration script that preserve existing custom tables.
* This consolidated report (`docs/riski_full_report.md`) serves as a single source of truth for developers, data engineers, and stakeholders.
