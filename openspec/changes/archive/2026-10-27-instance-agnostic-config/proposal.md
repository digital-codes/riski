# Proposal

## Why

The pipeline is tuned to one deployment: the Karlsruhe OParl backend, its
data directories, its geo sources and its council vocabulary are wired into
code as constants (`/bodies/0001`, `web1.karlsruhe.de`, `/mnt_ai/data/odd26/ris/ko`,
`\d{5}\s+Karlsruhe` address regex, KA venue-noise and document-type rules,
frontend branding/map center). Running a second instance against another
city's OParl backend (e.g. München's `risi.muenchen.de`, cf. it-at-m/riski)
currently means editing source code. The it-at-m comparison also showed the
same pipeline pattern is portable — their extractor/backend is fully
env-configured (`RISKI__*` nested settings).

## What Changes

- **Instance config file** (`config/instance.yaml`, path overridable via
  env `RISKI_INSTANCE_CONFIG`): city name, OParl system URL, data
  directories (crawl/extracted/sums/pdf), log file name, geo sources
  (street-name source, district GeoJSON path + attribute column names),
  address-block regex city name, venue-noise patterns, meeting-web URL
  shape, map center/zoom, branding strings (title, footer, legal links),
  default search query, CORS origins. Every entry overridable by env
  (`RISKI_<SECTION>__<KEY>`), resolution order env → instance.yaml →
  current constants (Karlsruhe stays the shipped default, zero regression).
- **Crawler instance-independence** (`oparlUpdate`): enumerate OParl bodies
  from the `system` object instead of the hardcoded `/bodies/0001`;
  configurable page size and request delay (defaults keep today's values);
  the `fix_karlsruhe_url` URL rewriter becomes a configurable URL-rewrite
  list (empty for other backends).
- **Instance-agnostic enrichment rules**: the deterministic address-block
  heuristic builds its regex from the configured city name; venue-noise and
  document-type canonicalization (`Haushalt THH <n>`) and org
  classification rules move to the instance config (code defaults =
  today's Karlsruhe rules).
- **Frontend instance config**: the API serves an `/instance` endpoint with
  branding, legal links, map center, default query and data-source list;
  the Vue app reads them at startup instead of hardcoded strings
  (`VITE_API_BASE` mechanism unchanged).
- **Fresh-instance bootstrap**: `scripts/bootstrap_instance.sh` documents
  the full path — new database (name via `DB_NAME`/`POSTGRES_URL`),
  `pgGen` schema creation, crawl → import → OCR → enrichment → geo load
  from configured sources → serve. README section "Running a second
  instance".
- **Credential hygiene** (additive): `src/private.py` keeps working, but
  every key/endpoint gains an environment-variable fallback so a second
  instance needs no edited source file.

## Capabilities

### New Capabilities

- `instance-config`: deployment-instance configuration — one config file +
  env overrides covering OParl endpoint, data dirs, geo sources, city-specific
  matching rules and frontend branding; body enumeration from the OParl
  system object; fresh-instance bootstrap.

### Modified Capabilities

- `oparl-import`: the crawler reads bodies/page-size/delay/URL-rewrites from
  instance configuration instead of constants; `fix_karlsruhe_url` becomes
  config-driven.
- `data-enrichment`: the address-block boilerplate heuristic derives its
  city regex from instance config; venue-noise patterns and document-type
  canonicalization rules are configuration, not code constants.

## Impact

- New: `config/instance.yaml` (+ loader `src/instanceConfig.py`),
  `scripts/bootstrap_instance.sh`, `GET /instance`.
- Changed: `oparlUpdate.py` (bodies, page size, delay, URL rewrites),
  `geoGate.py`/`pgGeoGateCleanup.py` (address regex), `pgAddFileGeoRefs.py`
  (venue noise), `pgCategorise.py`/`pgAddTags.py`/`pgAddOrgClassification.py`
  (rules from config with code defaults), `pgAddDistricts.py` (column names),
  `apiServer.py` (`/instance`), `app/` (startup fetch of instance config),
  `db/__init__.py` (no change needed — already env-resolvable).
- Compatibility: with no `config/instance.yaml` present, behavior is
  byte-identical to today (Karlsruhe defaults); all existing tests keep
  passing unchanged.
- Not in scope: Kafka/event-driven architecture, LangGraph chat agent,
  Langfuse observability (it-at-m features worth adopting separately);
  non-German deployments (LLM prompts stay German by design).
