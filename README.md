# riski — Ratsinformationssystem erklären

> **Note on AI use:** this project is developed with heavy assistance from AI coding agents (Claude Code / opencode); LLMs are also a runtime component (summaries, teasers, OCR, embeddings) via the shared `src/remote` layer.

**riski** is a Python toolkit that makes the Karlsruhe [Ratsinformationssystem (RIS)](https://web1.karlsruhe.de/ris/oparl) — the city council's open-data portal — searchable and explainable. It downloads the council's OParl data (meetings, agenda items, papers, files, consultations), imports it into a PostgreSQL database with a typed, relationally-linked schema, and then enriches it with semantic layers: LLM-generated German summaries and teasers, document tags, geographic references (streets and districts), and vector embeddings. On top of that data it offers semantic search, graph queries, and an interactive timeline view that shows *when* and *in which context* a topic appeared in council business.

## How it works

The pipeline has four stages, all built on two shared layers in `src/`:

| Stage | Modules | What they do |
|---|---|---|
| **1. Acquire** | `oparlUpdate` | Incremental crawl of the OParl API (JSON + PDFs), with URL fixing and run-state bookkeeping. |
| **2. Import** | `pgGen` | Schema generator: detects entity types, relationships and scalar columns from the observed OParl JSON, creates main + association tables and imports everything (additive, non-destructive re-runs). |
| **3. Enrich** | `pgAddSummaries`, `pgAddNameVectors`, `pgAddVecs`, `pgAddStreets`/`pgAddDistricts` (+ `pgAddStreetRefs`/`pgAddDistrictRefs`), `pgTagMgr`, `pgAddTags`, `pgSummarize`, `pgTeasers` | Load streets/districts, link agenda items that mention them, manage tags, update file contents, generate LLM summaries and teasers, compute pgvector embeddings. |
| **4. Search & analyse** | `pgVecSearch`, `pgTimeline`, `pgFileQuery` | Cosine-similarity search over embeddings, an interactive CLI that builds a grouped 30-day timeline of related meetings/agenda items/papers for a query, and structural graph queries. |

### Shared layers

- **`src/db`** — centralised database access: credential resolution (`private.py` → environment → defaults, `POSTGRES_URL` override), a cached engine per role (read/write + read-only), `table_exists`, a generic PostgreSQL upsert helper, and a connection context manager.
- **`src/remote`** — centralised model access against OpenAI-compatible endpoints: `chat()`, `embed()` and `ocr()` with retry/back-off. Endpoints are configurable for fully local operation (llama.cpp / ollama) as well as hosted APIs; keys live in the git-ignored `src/private.py` or environment variables.

## Setup

1. **Database**: PostgreSQL with the [`pgvector`](https://github.com/pgvector/pgvector) extension:
   ```sql
   CREATE DATABASE riski_agentic;
   \c riski_agentic
   CREATE EXTENSION vector;
   ```
2. **Credentials**: create `src/private.py` (git-ignored) with `DB_USER`, `DB_PWD`, `DB_HOST`, `DB_NAME`, optionally read-only credentials `RO_USER`/`RO_PWD`, and model endpoint configuration (`EMB_*`, `SUMMARY_*`, `OCR_*`, `VIDEO_API_KEY`). Alternatively set `DB_*` / `POSTGRES_URL` / `CHAT_*` / `EMBED_*` environment variables. For test runs with database writes, `.env` may provide `RW_USER`/`RW_PWD`.
3. **Dependencies**: SQLAlchemy, psycopg2, pgvector, requests, numpy, pandas, geopandas (street/district loading), pytest (tests).

## Usage

Scripts can be run directly or as modules — both work:

```bash
# incremental crawl of new/changed OParl entities
python src/oparlUpdate.py

# (re)create/update the schema and import a directory of OParl JSON files
python src/pgGen.py /path/to/oparl/json

# one-off: rebuild content embeddings from a .npz vector dump
python src/pgAddVecs.py vectors.npz

# interactive semantic search with timeline output
python src/pgTimeline.py

# or as a package module
python -m src.pgVecSearch
```

## Tests

```bash
python -m pytest src/tests -m unit          # fast, mocked, no network
python -m pytest src/tests                  # full suite incl. live DB integration
python -m pytest src/tests -m integration   # only live-DB / live-endpoint tests
```

Integration tests run against the real `riski_agentic` database but only touch
`test_*`-prefixed tables, and skip automatically when credentials or live LLM
endpoints are unavailable.

## Further reading

- `docs/` — database DDL, pg reports, street-name data, visualisation notes
- `docs/20261023-hermes/` — cross-repo analysis of related Karlsruhe-RIS projects
- `openspec/` — capability specs describing the intended behaviour of each module
- `app/` — prototype web visualisation (Vite)
- `utils/` — auxiliary tooling (video trailer generation, knowledge-graph experiments, street geometry helpers)

## Incremental update — implementation status

The open change `openspec/changes/incremental-postgres-update` describes incremental
synchronisation of the PostgreSQL data. Much of it already exists in
`src/oparlUpdate.py` and `src/pgGen.py`, partly in a different form than originally
planned (the timestamp cursor moved from `last_run.txt` into the database — see the
archived change `track-oparl-update-runs`).

**Already implemented:**

| Planned | Status in the current code |
|---|---|
| Timestamp cursor tracking | ✅ Superseded and better: the `oparlUpdateRuns` table stores each run's baseline and end state in the database (DB is the sole source; `last_run.txt` was removed entirely). |
| `?createdSince=<timestamp>` queries | ⚠️ Partial: `oparlUpdate` applies `createdSince` only to the `bodies/0001` collection. All other collections (papers, agendaItems, meetings, people, consultations) are always fetched in full — unchanged resources are only skipped when writing files, which makes each run re-validate the whole graph. |
| Idempotent upsert (`ON CONFLICT DO UPDATE`) | ✅ `pgGen.insert_all` upserts on `oparlId`, updating only when the incoming `modified` timestamp is newer. |
| Graceful shutdown / cursor persistence | ✅ `SIGINT` is caught; the run is recorded with `success=false` and the items collected so far are persisted. |
| Timestamp validation | ✅ Superseded: the cursor lives in typed DB columns, not a text file. |
| Unit tests (timestamps, shutdown) + mocked integration tests | ✅ `src/tests/test_unit_oparlUpdate.py`, `src/tests/test_unit_oparlRunLog.py`, `src/tests/test_integration_oparlRunLog.py` (rollback-only DB writes). |
| README documentation | ✅ This section. |

**Still to be done:**

- **Extend `createdSince` to all collections** (papers, agendaItems, meetings, people,
  consultations) so runs only fetch what actually changed instead of re-validating
  everything — this is why a full crawl currently takes hours.
- **Endpoint-capability detection and fallback**: no logic exists to detect that an
  endpoint ignores `createdSince`; those endpoints should fall back to a full fetch
  with a warning (planned task 3.1).
- **Cover *modified* records, not only created ones.** OParl's `createdSince` only
  matches entity creation dates; entities modified after creation can be missed.
  Either use `modifiedSince` where the API supports it, or compare `modified`
  timestamps against the tracked baseline during import.
- **Direct-to-DB incremental sync is still two-phase.** The crawler only writes JSON
  files; updating PostgreSQL requires running `pgGen` separately. A single command
  that crawls *and* imports incrementally (or scheduling both together) does not exist.

## Potential improvements

Ideas that apply to this repo, distilled from `docs/20261023-hermes/riski-improvement-report.md`
(which also covers the related syndication/viewer/desinformationssystem projects):

- **Persist document categories.** Categorisation is currently regex-on-names only
  (`pgAddTags`), producing JSON reports that are never written back to the
  database. The OParl `term` field (`Antrag`, `Beschlussvorlage`, `Protokoll`,
  `Abstimmung`, …) is authoritative and should be mapped via a lookup table to a
  `category` stored on `Paper`/`File` rows (plus a document ↔ category
  association table for multi-category documents).
- **Categorise at ingestion time.** Hook the category resolution into
  `oparlUpdate` (and `pgGen`'s import) so new entities are categorised as they
  are persisted, with a one-off back-fill script for existing records.
- **Reuse the TagManager.** Categories can be treated as tags and stored through
  the existing `TagManager` many-to-many machinery instead of new ad-hoc code.
- **Enable faceted filtering downstream.** With categories persisted, semantic
  search (`pgTimeline`, `pgVecSearch`) and queries (`pgFileQuery`) can filter by
  document type, submitter/faction and district instead of guessing from
  filenames — reducing reliance on fragile filename heuristics.
