# Spec Delta

## Purpose

Deployment-instance configuration: a second instance of the pipeline (new
database, new download folders, another city's OParl backend) is created by
configuration only — one instance config file with environment overrides —
without editing source code. Karlsruhe remains the shipped default.

## ADDED Requirements

### Requirement: Instance configuration file and resolution order

The system SHALL read instance-specific settings (OParl system URL, data
directories, geo sources, matching rules, branding, map center, default
query) from a single config file, overridable per entry by environment
variables (`RISKI_<SECTION>__<KEY>`). Resolution order: environment, then
config file, then code defaults; no config SHALL mean today's Karlsruhe
behavior.

#### Scenario: Second instance without code edits
- **WHEN** an instance config names another OParl system URL, a different
  database name and different data directories
- **THEN** crawl, import, enrichment and serving run against that instance
  with no source-file changes

#### Scenario: Environment wins
- **WHEN** an instance config value is also provided as an environment
  variable
- **THEN** the environment variable is used

#### Scenario: No config means Karlsruhe defaults
- **WHEN** no instance config file exists and no overrides are set
- **THEN** the pipeline behaves exactly as the current Karlsruhe deployment

### Requirement: OParl bodies are enumerated from the system object

The crawler SHALL discover the body IDs to crawl from the OParl `system`
object's `bodies` list instead of a hardcoded body ID. An instance config
entry MAY restrict the crawl to a subset of discovered body IDs; all
discovered bodies SHALL be crawled otherwise. A backend that fails body
enumeration SHALL abort the run with a clear error rather than silently
crawling a wrong body.

#### Scenario: Non-default body IDs are crawled
- **WHEN** the configured OParl system exposes bodies with IDs other than
  "0001"
- **THEN** the crawler enumerates them from the system object and crawls
  their collections

#### Scenario: Configured subset
- **WHEN** the instance config lists specific body IDs
- **THEN** only those bodies' collections are crawled

### Requirement: Crawler transport parameters are configurable

Page size, request delay and URL-rewrite rules SHALL come from the instance
configuration (defaults preserving today's Karlsruhe values: page size 1000,
delay 0.25 s). URL rewrites SHALL be an ordered list of regex/replacement
pairs applied to fetched URLs; the current Karlsruhe `web1.karlsruhe.de`
rewriter SHALL be expressible as one such entry, and an empty list SHALL
mean no rewriting.

#### Scenario: Backend-specific rewriting
- **WHEN** the configured backend serves document URLs that need
  rewriting before download
- **THEN** each configured regex/replacement pair is applied to fetched
  URLs in order

### Requirement: City-specific matching rules are configuration

The address-block boilerplate heuristic (house number + postal code +
city), the venue-noise patterns, the document-type canonicalization rules
(e.g. Karlsruhe's `Haushalt THH <n>` product codes) and the organization
classification name-regex rules SHALL be read from the instance config,
with the current Karlsruhe rules as code-level defaults. The organization
classification default SHALL fall back to the configured fallback label.

#### Scenario: Address heuristic for another city
- **WHEN** the instance config names "München" as city
- **THEN** the address-block regex matches `<PLZ> München` instead of
  `<PLZ> Karlsruhe`

#### Scenario: Document-type rules for another backend
- **WHEN** the configured backend uses document-type names without
  Karlsruhe product-code conventions
- **THEN** canonicalization falls through verbatim for unknown patterns
  instead of misclassifying them

### Requirement: Instance endpoint and frontend branding

The API SHALL expose `GET /instance` returning the frontend-relevant
instance settings: display title, city name, legal/imprint and privacy
links, data-source list, map center/zoom, and the default search query.
The web app SHALL fetch this at startup and render branding, map view
center and legal pages from it instead of hardcoded strings.

#### Scenario: Frontend adapts to the instance
- **WHEN** the app starts against an API serving a different instance
  config
- **THEN** title, footer, legal texts, map center and default query come
  from `GET /instance`

### Requirement: Fresh-instance bootstrap

The repository SHALL provide a documented bootstrap path (script + README
section) that creates a fresh database (name/credentials via the existing
`DB_*`/`POSTGRES_URL` resolution), generates the schema, runs crawl →
import → OCR → summaries → embeddings → geo loading from the configured
sources, and starts the API — entirely driven by the instance config.

#### Scenario: Second instance end-to-end
- **WHEN** the bootstrap script runs with a second instance's config
- **THEN** a new database is populated from the configured OParl backend
  and the API serves it, without touching the original instance's database
  or data directories
