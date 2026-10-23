# riski — Ratsinformationssystem erklären

> **Note on AI use:** this project is developed with heavy assistance from AI coding agents (Claude Code / opencode); LLMs are also a runtime component (summaries, teasers, OCR, embeddings) via the shared `src/remote` layer.

**riski** is a Python toolkit that makes the Karlsruhe [Ratsinformationssystem (RIS)](https://web1.karlsruhe.de/ris/oparl) — the city council's open-data portal — searchable and explainable. It downloads the council's OParl data (meetings, agenda items, papers, files, consultations), imports it into a PostgreSQL database with a typed, relationally-linked schema, and then enriches it with semantic layers: LLM-generated German summaries and teasers, document tags, geographic references (streets and districts), and vector embeddings. On top of that data it offers semantic search, graph queries, and an interactive timeline view that shows *when* and *in which context* a topic appeared in council business.

## How it works

The pipeline has four stages, all built on two shared layers in `src/`:

| Stage | Modules | What they do |
|---|---|---|
| **1. Acquire** | `oparlUpdate` | Incremental crawl of the OParl API (JSON + PDFs), with URL fixing and run-state bookkeeping. |
| **2. Import** | `pgGen` | Schema generator: detects entity types, relationships and scalar columns from the observed OParl JSON, creates main + association tables and imports everything (additive, non-destructive re-runs). |
| **3. Enrich** | `pgAddSummaries`, `pgAddNameVectors`, `pgBackfillNameVecs`, `pgAddVecs`, `pgAddStreets`/`pgAddDistricts` (+ `pgAddStreetRefs`/`pgAddDistrictRefs`), `pgTagMgr`, `pgCategorise`, `pgAddTags`, `pgSummarize`, `pgTeasers`, `pgCoverage` | Load streets/districts, link agenda items that mention them, manage tags with provenance (scheme/source/confidence), derive canonical document-type categories, update file contents, generate LLM summaries and teasers, compute pgvector embeddings (content + name vectors), report enrichment-layer coverage. |
| **4. Search & analyse** | `pgVecSearch`, `pgHybridSearch`, `pgTimeline`, `pgFileQuery`, `graphModel`, `pgResultSummarizer`, `apiServer` | Hybrid multi-signal search (trigram lexical + name vectors + content vectors, RRF-fused, faceted filters), query-guided German summaries, graph serialization/expansion over the OParl association tables, and a FastAPI layer serving the interactive web app. |

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

# (re)derive canonical document-type tags (papertype → name-regex → LLM)
python src/pgCategorise.py all          # or: papertype | regex | llm

# coverage report over all enrichment layers (content, teasers, vectors, tags)
python src/pgCoverage.py

# name-vector backfill (resume-safe; ~8 vectors/s with 6 workers)
python src/pgBackfillNameVecs.py --workers 6

# interactive semantic search with timeline output (results + graph +
# facets; saves to app/src/assets/sampleData.json)
python src/pgTimeline.py

# or as a package module
python -m src.pgVecSearch
```

## Interactive search — web app + API

```bash
uvicorn src.apiServer:app --port 8000   # API (also: interactive /docs)
cd app && npm run dev                   # web app (vite dev server)
```

The app (`app/`, Vue 3 + ECharts) issues hybrid searches against the API
and renders the answer set three ways: a 30-day timeline, an interactive
**network graph** (files, papers, agenda items, meetings, consultations,
organizations and their OParl relations), and a query-guided German
**summary**. Clicking a node opens a detail panel with the OParl record,
the PDF download (files) and the public meeting-calendar page (meetings,
agenda items with their TOP anchor). "Nachbarn laden" expands a node's
depth-1 neighborhood into the graph (merge-by-id, positions preserved).

In production the API is expected under the same origin at `/api/...`
(the dev setup proxies `/api` to `localhost:8000` via vite; override with
`VITE_API_BASE`).

### How search works

Three recall signals are fused per entity type by reciprocal-rank fusion
and re-ranked by the LLM reranker:

1. **Lexical** — pg_trgm trigram similarity over the indexed `name`
   columns (Paper, File, AgendaItem, Meeting).
2. **Name vectors** — pgvector cosine over `{item}_name_vecs` (embedded
   from raw names).
3. **Content vectors** — pgvector cosine over `contentEmbeddings`.

Structured filters (`paperType`, year range, `AgendaItem.result`,
`Consultation.role`/`authoritative`, tags by scheme, district,
organization) are applied pre-fusion; results carry a match-type
provenance (`match`/`signals`: which signals found each entry and at what
distance) and a facet listing for filter dropdowns.

### Deployment-specific configuration (`config/`)

Two config files keep city-specific knowledge out of the code:

- **`config/lexical_stop_terms.txt`** — terms with no discriminative
  power (e.g. the city name). Stripped from both query and names for the
  lexical signal, and from the query before its name-vector embedding.
  The vector tables themselves stay decoupled: changing the list never
  requires re-embedding.
- **`config/meeting_web_url.txt`** — base URL of the public meeting
  calendar; the graph appends `termin-<meeting number>` (agenda items
  link to their `#dtop<top>` anchor). Missing file → no calendar links.

Both paths can be overridden in `private.py` / environment
(`LEXICAL_STOP_TERMS_FILE`, `MEETING_WEB_URL_FILE`).

### Map view for georeferenced queries

Queries that hit documents linked to streets or districts (e.g. "Rückbau
der Herrenalber Straße") get a **map view** at the bottom of the page.
The data is already there: `pgAddStreetRefs`/`pgAddDistrictRefs` link
agenda items to the Street/District tables, which carry GeoJSON
geometries (WGS84, no reprojection needed). The API exposes them as a
GeoJSON FeatureCollection under `GET /geo/{session_id}` — streets as
lines, districts as polygons, each popup naming the linked agenda items.
The frontend (`GeoMap.vue`, Leaflet — adapted from the klimaDashboard
project's `SimpleMap.vue`) loads the layer lazily, only when the search
result carries `geo_available: true`; the SummaryCard header then shows a
"Karte verfügbar — weiter unten" note.

Point layers (POIs) are future work: e.g. road constructions from
transparenz.karlsruhe.de via the TBA geoserver WFS would add exactly the
"where is the Baustelle on my street" dimension.

### Summaries

The summary is a separate step (`pgResultSummarizer`), not part of the
search: `/search` returns immediately, the frontend fetches `POST
/summarize` asynchronously and fills the SummaryCard when it arrives.
The summary is **query-guided** — it condenses ALL fetched document
teasers with respect to the question, states the question, and names the
key documents. Teasers (not full text) keep the LLM call fast.

Wide searches can fetch off-topic documents, so the summarizer first
evaluates each document against the question, summarizes only the
relevant ones, and appends a note listing the refused documents
("Nicht berücksichtigte Dokumente"). A provenance footer states the
model, endpoint and token usage — plus inference time, energy and
emissions when the endpoint reports them (`remote.chat` passes the
`usage`/`impact` fields through). The footer is part of the stored
summary and therefore included in the PDF export.

The refusal verdict is machine-parseable (`result["summary_refused"]`):
refused documents are listed by their `Datei <Nummer>` identifier from
the prompt's numbered document list, and the map view gates on it —
georeferences from refused documents are excluded (the frontend refetches
`/geo` when the verdict arrives). The refusal strictness is a prompt
lever (`_SYSTEM_PROMPT` in `src/pgResultSummarizer.py`): if refusals feel
too aggressive — e.g. topically related documents dropped as redundant —
tighten the instruction to refuse only clearly unrelated documents; if
noise leaks through, sharpen it in the other direction.

### Performance instrumentation

`src/timing.py` provides `@timed` / `timed_block` (stdlib-only) used
across the search pipeline, including per-signal hybrid timings. Output
is `[timing] <label>: <seconds>s` on stdout; disable with
`RISKI_TIMING=0`.

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
- `openspec/specs/` — capability specs describing the intended behaviour of each module (`search-api`, `network-view`, `result-summarizer`, `semantic-search`, `data-enrichment`, …)
- `openspec/changes/archive/` — implemented change histories (incl. the 2026-10-23 search/network work)
- `config/` — deployment-specific settings (lexical stop terms, meeting calendar base URL)
- `utils/` — auxiliary tooling (video trailer generation, knowledge-graph experiments, street geometry helpers)

## Incremental update — implementation status

The open change `openspec/changes/incremental-oparl-sync` describes incremental
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

**Recently implemented** (2026-10-23, see `openspec/changes/archive/`):
canonical tag model with provenance (`pgTagMgr` + `pgCategorise`, papertype
backfill at 100% coverage), hybrid multi-signal search with faceted
filters and match-type provenance, name vectors for all entity tables,
the network graph view with OParl association edges, the FastAPI search
API, and query-guided async summaries.

**Still open:**

- **LLM tag backfill for remaining items** — AgendaItem coverage is at
  ~28% (name-regex misses escalate to the teaser-based LLM pass; run
  `python src/pgCategorise.py llm`).
- **Submitter/faction facet** — OParl `originator*`/`submitter` fields are
  unpopulated in this corpus (verified by spike); would need rule-based
  derivation like the desinformationssystem project's `submitter.py`.
- **Semantic-similarity edges** — pairwise cosine over `contentEmbeddings`
  within an answer set, rendered as a "mesh" layer in the network view.
- **`/ask` endpoint** — contextual follow-up questions with LLM query
  rewrite against the session context (session store already in place).
- **graphGL 3D renderer** — time as third axis / color, behind a toggle.
- **contentEmbeddings coverage** — 93.7% → 100% (files without embeddings).
- **Full text in Postgres** — raw text lives on disk only; a bounded
  `fulltext` column + tsvector would enable FTS beyond name trigrams.
- **Extend `createdSince` to all collections** in `oparlUpdate` (see the
  incremental-update section above) — the biggest crawl-time win.
