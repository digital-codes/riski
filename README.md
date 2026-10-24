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
# one-command incremental synchronisation (crawl + DB import)
python src/syncIncremental.py

# incremental crawl only (no DB import)
python src/oparlUpdate.py

# (re)create/update the schema and import a directory of OParl JSON files
python src/pgGen.py /path/to/oparl/json

# OCR PDFs that have no extracted markdown yet (Mistral OCR backend)
python src/pgOcr.py

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

## Data update workflow

The full pipeline for bringing the database from "last run" to "now".
Every step is **idempotent and resumable** — re-running never duplicates
rows and skips already-processed items.

```bash
# 0) Snapshot (hard prerequisite — do not skip)
PGPASSWORD=... pg_dump -Fc -h localhost -U riski -d riski_agentic \
    -f /mnt_ai/data/riski/snapshots/riski_agentic_$(date +%F).dump
pg_restore --list /mnt_ai/data/riski/snapshots/riski_agentic_*.dump   # verify

# 1) Crawl + import in one command. Writes JSON/PDFs under
#    /mnt_ai/data/odd26/ris/{ko,ko_pdf}, then imports via pgGen.
#    The tracked baseline (oparlUpdateRuns) advances only when the
#    import succeeds.
python src/syncIncremental.py
#    Two-phase alternative: python src/oparlUpdate.py  &&  python src/pgGen.py /mnt_ai/data/odd26/ris/ko
#    Import parallelism: RISKI_IMPORT_WORKERS (default 4) threads. Observed
#    profile (2026-10-24): 1 Python core at ~100%, Postgres backends at ~5%
#    each — expected, see the GIL note under "Import performance notes" below.
#    Incremental mechanics (OParl 1.1 update mechanism): all 9 Karlsruhe
#    collections are requested with modified_since=<baseline> (spec
#    underscore spelling — the camelCase variant is silently ignored!),
#    page size limit=1000, only pagination links and PDF downloads are
#    followed (resource references are never dereferenced). Every
#    collection page is validated against the baseline (an honouring
#    filter never returns older items); a violating page falls back to
#    created_since, then to a full fetch (visible in
#    oparlUpdateRuns.full_fetches). The same
#    approach is used by the independent karlsruhe-oparl-syndication
#    crawler (github.com/digital-codes/karlsruhe-oparl-syndication), which
#    additionally reconciles fully every 7 days — a reasonable pattern to
#    adopt via cron for this pipeline too.
#    Note: pgGen must see the FULL ko/ directory (not just new files) —
#    association URLs are resolved within the passed directory only.

# 2) OCR: for every PDF in ko_pdf without ko_extracted/<stem>.md, run
#    Mistral OCR (keys in src/private.py: OCR_URL/OCR_KEY). Large
#    documents are OCR'd only up to the first 12 pages (--max-pages 0
#    disables the cap). Skips existing outputs; failures are logged.
python src/pgOcr.py

# 3) Summaries: for markdown >8000 chars, store an LLM summary
#    (≤8000 chars, mistral-small) instead of the full text; smaller
#    files are copied unchanged. Run from the data directory (relative
#    ./ko_extracted → ./ko_sums) or pass explicit dirs:
python src/pgSummarize.py --src-dir /mnt_ai/data/odd26/ris/ko_extracted \
                          --dst-dir /mnt_ai/data/odd26/ris/ko_sums

# 4) File contents + embeddings: match ko_sums markdown to File rows
#    (by filename stem) and update File.content/contentKind.
#    --embed-missing embeds ONLY files without a contentEmbeddings row.
python src/pgAddSummaries.py -s /mnt_ai/data/odd26/ris/ko_sums \
                             -f /mnt_ai/data/odd26/ris/ko_extracted \
                             --embed-missing
#    (use -e instead of --embed-missing to re-embed everything)

# 5) Teasers: LLM teaser for every File that has content but no teaser.
#    Needs DB credentials + an OpenAI-compatible LLM endpoint
#    (local ollama by default; override for hosted APIs):
RISKI_USER=riski RISKI_PASSWORD=... \
RISKI_LLM_URL=https://api.mistral.ai RISKI_LLM_MDL=mistral-small-2603 \
RISKI_LLM_API_KEY=... \
python src/pgTeasers.py

# 6) Geo references (idempotent, existing pairs are skipped):
python src/pgAddFileGeoRefs.py --prune   # file name/teaser → streets/districts
python src/pgAddStreetRefs.py            # agenda item names → streets
python src/pgAddDistrictRefs.py          # agenda item names → districts

# 7) Tags/categories: papertype backfill → name-regex → teaser LLM
#    escalation. Skips already-tagged items (use --force to re-run LLM).
python src/pgCategorise.py all

# 8) Verify:
python src/pgCoverage.py
```

**Duplicate-safety guarantees:** `pgGen` upserts on `oparlId` (newer
`modified` wins), `pgSummarize`/`pgOcr`/`pgTeasers` skip existing
outputs, `pgAddFileGeoRefs`/street/district refs preload existing pairs,
`pgCategorise` skips already-tagged items, embeddings upsert on
`oparlKey`. A crash mid-run is recovered by simply re-running the step.

**Notes:**
- The canonical data dirs (`/mnt_ai/data/odd26/ris/ko*`) are owned by the
  `kugel` user; steps 2–3 write markdown there and must run as that user
  (or with `--out-dir`/`--dst-dir` pointed at a writable mirror that is
  copied back afterwards), e.g. when running as `agent`:

  ```bash
  # steps 2–3 with a writable mirror
  python src/pgOcr.py --out-dir /home/agent/ris_update/ko_extracted_new
  python src/pgSummarize.py --src-dir /mnt_ai/data/odd26/ris/ko_extracted \
                            --dst-dir /home/agent/ris_update/ko_sums_new
  # copy the new markdown into the canonical folders (as kugel, or with
  # write permission) — the DB is populated from the mirrors either way
  cp /home/agent/ris_update/ko_extracted_new/*.md /mnt_ai/data/odd26/ris/ko_extracted/
  cp /home/agent/ris_update/ko_sums_new/*.md      /mnt_ai/data/odd26/ris/ko_sums/
  ```
- File matching in step 4 works on the numeric filename stem
  (`00030895.md` ↔ `File.filename = "00030895.pdf"`); files without a
  markdown source keep `content IS NULL` (they are skipped by search).
- `pgGen` detects new scalar columns/tables from the observed JSON and
  adds them additively — new OParl fields never require a rebuild.

### Import performance notes (GIL)

The import's parallelism (`RISKI_IMPORT_WORKERS`, default 4) is thread-based.
Observed profile (2026-10-24, full 107k-entity import): **1 Python core at
~100%, Postgres backends at ~5% each**. This is expected, not a
misconfiguration: the GIL pins Python-side work (statement compilation, row
building, JSON/entity parsing) to a single core, and the worker threads only
overlap the network/disk waits — which is exactly where the measured gain
comes from (full import 7.5 → 3.5 min). Adding workers will not raise CPU
utilization. True multi-core would require multiprocessing (expensive here:
~0.5–1 GB of entity state per worker would need to be shipped between
processes) or a faster JSON parser (`orjson`) for pass 1 — the latter is the
cheap future win.

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
evaluates each document against the question and summarizes only the
relevant ones. The per-document verdict (berücksichtigt /
nicht berücksichtigt) is rendered in the document list at the end of the
summary — the model's own refusal note is parsed for the machine-readable
verdict (map gating, pre-exclusion) but stripped from the displayed text,
since the list already carries it. A provenance footer states the
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

#### Refine and per-file control

The summary is built from the fast **teaser layer**; a **"Verfeinern"**
button in the summary pane re-runs the summarizer with the **full document
content** (prompt header names the layer) — the previous summary stays
visible while the refined one is generated. The document list
(checkbox, name as download link, berücksichtigt/nicht berücksichtigt)
renders once — directly under the summary text and in the PDF export —
driven by the structured per-file metadata: excluding a file removes it from the summary's document set and
re-runs the summarizer over the remaining files (always full content, since
it follows a user action). Files the model refused start excluded. Both
features call `POST /summarize {refine, exclude}`; exclusions persist in the
session until the next search.

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

Implemented as of 2026-10-24 (open change
`openspec/changes/incremental-oparl-sync`, tasks 1.x–3.x done; the DB is
current through 2026-10-14 via the documented data update workflow). The
timestamp cursor lives in the database (`oparlUpdateRuns` table — sole
source of truth, see the archived change `track-oparl-update-runs`).

| Planned | Status in the current code |
|---|---|
| Timestamp cursor tracking | ✅ The `oparlUpdateRuns` table stores each run's baseline and end state in the database (DB is the sole source; `last_run.txt` was removed entirely). |
| `?modified_since=`/`?created_since=` queries | ✅ Every collection (all 9 Karlsruhe types incl. files/memberships/organizations/locations) is requested with `modified_since` first (captures modified-after-creation entities); `created_since` is the fallback. NOTE: the parameters must use the underscore spelling from the OParl 1.1 spec — the API **silently ignores** the camelCase variant (`modifiedSince`), which an earlier version of this crawler used. Page size `limit=1000` cuts pagination requests ~100×. |
| Endpoint-capability detection and fallback | ✅ When an endpoint provably ignores a filter (older resources returned) or rejects it (HTTP error), the crawler falls back — first to the other parameter, then to a full fetch with a warning. Fallback usage is visible in the run row (`oparlUpdateRuns.full_fetches`). |
| Cover *modified* records, not only created ones | ✅ Via `modified_since`-first (see above). |
| One-command synchronisation | ✅ `src/syncIncremental.py` runs the incremental crawl and then `pgGen`'s import against the crawl output. The run row is finalised (and the baseline advanced) only after a successful import; on failure the baseline is reset to the pre-crawl window. |
| Idempotent upsert (`ON CONFLICT DO UPDATE`) | ✅ `pgGen.insert_all` upserts on `oparlId`, updating only when the incoming `modified` timestamp is newer. |
| Graceful shutdown / cursor persistence | ✅ `SIGINT` is caught; the run is recorded with `success=false` and the items collected so far are persisted. |
| Unit tests (timestamps, shutdown) + mocked integration tests | ✅ `src/tests/test_unit_oparlUpdate.py`, `src/tests/test_unit_oparlRunLog.py`, `src/tests/test_unit_syncIncremental.py`, `src/tests/test_integration_oparlRunLog.py`, `src/tests/test_integration_syncIncremental.py` (rollback-only DB writes). |
| README documentation | ✅ This section + the data update workflow above. |

**Remaining:**

- **Real-run verification** (`openspec/changes/incremental-oparl-sync`
  task 4.1, user-gated): one live `syncIncremental` run to confirm the
  Karlsruhe API honours `modifiedSince` (the fallback ensures correctness
  either way) and that typical runs finish in minutes.

## Potential improvements

Ideas that apply to this repo, distilled from `docs/20261023-hermes/riski-improvement-report.md`
(which also covers the related syndication/viewer/desinformationssystem projects):

**Recently implemented** (2026-10-23, see `openspec/changes/archive/`):
canonical tag model with provenance (`pgTagMgr` + `pgCategorise`, papertype
backfill at 100% coverage), hybrid multi-signal search with faceted
filters and match-type provenance, name vectors for all entity tables,
the network graph view with OParl association edges, the FastAPI search
API, and query-guided async summaries.

**Recently implemented** (2026-10-24): `modified_since`-first incremental
crawling for all collections with capability fallback and run-row
visibility (`oparlUpdateRuns.full_fetches`), one-command synchronisation
(`syncIncremental`), batch PDF OCR (`pgOcr`, Mistral backend, first-12-pages
cap for large documents), targeted incremental embeddings
(`pgAddSummaries --embed-missing`), the missing
`contentEmbeddings.oparlKey` unique constraint (self-healed at startup),
and a data update that brought the DB from 2026-05-21 to 2026-10-14.

**Still open:**

- **LLM tag backfill for remaining items** — name-regex misses escalate
  to the teaser-based LLM pass; `python src/pgCategorise.py all`
  continues it (idempotent/resumable). File coverage is now ~82%, AgendaItem ~28%.
- **Submitter/faction facet** — OParl `originator*`/`submitter` fields are
  unpopulated in this corpus (verified by spike); would need rule-based
  derivation like the desinformationssystem project's `submitter.py`.
- **Semantic-similarity edges** — pairwise cosine over `contentEmbeddings`
  within an answer set, rendered as a "mesh" layer in the network view.
- **`/ask` endpoint** — contextual follow-up questions with LLM query
  rewrite against the session context (session store already in place).
- **graphGL 3D renderer** — time as third axis / color, behind a toggle.
- **Full text in Postgres** — raw text lives on disk only; a bounded
  `fulltext` column + tsvector would enable FTS beyond name trigrams.
- **Name-vector backfill** — `pgBackfillNameVecs` covers ~97–98% per table.
