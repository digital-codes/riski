# Design

## Context

See proposal.md — Why. The audit (2026-10-27) found the true porting
blockers beyond what is already configurable (DB via `DB_*`/`POSTGRES_URL`,
stop-terms file, meeting-web URL file, CLI flags for system URL/folders):

- `oparlUpdate.py:23-27` system URL/folders/log name as module constants;
  `:468,485` hardcoded `/bodies/0001`; `:41-76` Karlsruhe URL rewriter;
  `:229-230,375` transport constants.
- `geoGate.py:80` `\d{5}\s+Karlsruhe`; KA venue example in the LLM prompt.
- `pgAddFileGeoRefs.py:107` Rathaus-am-Marktplatz venue-noise regex.
- `pgCategorise.py:78-79` `Haushalt THH <n>`; `pgAddTags.py:66-102`
  document-type vocabularies; `pgAddOrgClassification.py:30-45` rules.
- `pgAddDistricts.py:65-73` GeoJSON attribute columns `NAME`/`NUMMER`.
- `intents.yaml` path fixed at `pgIntentRouter.py:36`; KA `groups` merge.
- Frontend: title/city strings, `GeoMap.vue:109` map center, legal pages,
  default query.
- `private.py` holds plaintext keys without env fallbacks.

## Goals / Non-Goals

**Goals:**
- A second instance (e.g. München) is creatable end-to-end with
  configuration only: new DB, new folders, new OParl backend.
- Karlsruhe default behavior byte-identical; existing tests untouched.

**Non-Goals:**
- Adopting it-at-m architecture elements (Kafka, LangGraph agent,
  Langfuse) — separate future changes.
- Non-German deployments (LLM prompts stay German).
- Multi-tenancy in one process — one config per process/instance.
- Removing `private.py` (kept, gains env fallbacks only).

## Decisions

### D1: One YAML file + env overlay, stdlib loader

`config/instance.yaml` with nested sections (`oparl`, `paths`, `geo`,
`rules`, `web`, `frontend`); loader `src/instanceConfig.py` (~100 lines,
stdlib `yaml` + `os.environ`) exposing `get_instance_config()` with
lru-cache and an env overlay (`RISKI_<SECTION>__<KEY>`, `__` splits).
Resolution: env → yaml → code defaults (Karlsruhe constants move into the
loader's `DEFAULTS` dict — single source of truth). Alternative considered:
pydantic-settings like it-at-m — rejected to stay dependency-light; the
nested-env convention mirrors theirs for future compatibility. Existing
separate config files (stop terms, meeting web URL, intents.yaml) keep
their own override hooks, but their *paths* also become instance-config
entries.

### D2: Body enumeration with config filter

`oparlUpdate` fetches `system.bodies` once per run (cached alongside the
system object already fetched) and crawls every discovered body; instance
config `oparl.bodies` optionally filters the set. If enumeration fails or
returns nothing, the run aborts with an explicit error (a silent
`/bodies/0001` fallback would crawl a wrong city's data). Backwards
compat: Karlsruhe's system exposes exactly body `0001`, so behavior is
unchanged.

### D3: URL rewrites as ordered regex list

`oparl.url_rewrites: [{pattern, replacement}]` replaces
`fix_karlsruhe_url`; Karlsruhe's rule ships as the default single entry,
other backends ship `[]`. Applied in `fix_urls_in_data` where the
Karlsruhe check sits today.

### D4: Matching rules with code defaults

- `rules.address_regex_city` (default "Karlsruhe") builds the
  `\d{5}\s+{city}` pattern; the GeoGate prompt's city references are
  formatted from the same value.
- `rules.venue_noise` (list of regex strings, default = the Karlsruhe
  Rathaus-am-Marktplatz rule).
- `rules.doc_type_canonicalization: {haushalt_codes: true|false}` — the
  `THH` product-code canonicalization is the only truly KA-specific rule;
  the generic document-type vocabularies (`pgAddTags`) stay German-council
  generic and remain code constants (config list optional later).
- `rules.org_classification` (list of `{pattern, label}` + fallback,
  default = today's `CLASSIFICATION_RULES`).
- `geo.district_columns: {name: NAME, number: NUMMER}` for the district
  GeoJSON schema.

### D5: `GET /instance` + frontend startup fetch

`apiServer` serves a whitelisted projection of the instance config
(`frontend` section + `web.meeting_url_template`); the Vue app fetches it
once at startup into a reactive store, falling back to the current
hardcoded strings when the endpoint is unreachable (sample-data mode).
`GeoMap.vue` center/zoom, `index.html` title (set at runtime), footer,
legal pages, `WorkPage` default query all read from the store. No build
step needed; `VITE_API_BASE` mechanism unchanged.

### D6: Bootstrap script + documentation

`scripts/bootstrap_instance.sh` (reads `RISKI_INSTANCE_CONFIG` +
`DB_NAME`/`POSTGRES_URL`): createdb → `pgGen` schema → `syncIncremental`
→ OCR/chunks/summaries/embeddings → `pgAddStreets`/`pgAddDistricts`/
geo refs → gate cleanup → serve. README section "Running a second
instance" with a München-flavoured example config. The script is
sequential/documented, not a new orchestration layer.

## Risks / Trade-offs

- [Config sprawl: two config layers (instance.yaml + existing per-feature
  files)] → instance.yaml only adds deployment-level entries; feature
  files keep their own resolution and are *referenced* (not duplicated) by
  it.
- [Tests coupled to Karlsruhe defaults] → defaults are code constants;
  tests keep passing unchanged; new tests cover a synthetic second config
  (env-overlay precedence, body enumeration with a stubbed system object,
  city-regex rebuild).
- [München's risi.muenchen.de may not be OParl 1.1 conformant (their
  extractor scrapes rather than speaks OParl)] → out of scope for this
  change; the config accepts any OParl-compliant system URL. A München
  run is the verification target *if* their OParl endpoint exists; else
  verification uses a second Karlsruhe instance (different DB + folders).
- [Prompt leakage of KA specifics in LLM gates] → city name formatted
  from config; the remaining KA example (Hebelstraße) becomes generic.

## Migration Plan

Additive rollout: loader + defaults first (no behavior change), then
crawler/enrichment switches reading through the loader, then `/instance` +
frontend, then bootstrap script. Rollback = remove the config file.
Karlsruhe production never needs an instance.yaml.

## Open Questions

- ~~Whether München exposes a standards-compliant OParl 1.1 endpoint at all~~
  — resolved 2026-10-27: **no**. Their `riski-extractor` is an HTML scraper
  (BeautifulSoup, POST-form pagination) against `risi.muenchen.de/risi`; all
  `/oparl*` paths return 503. München is not a verification target for this
  change. **Dresden is**: `https://oparl.dresden.de/system` is a live public
  OParl 1.1 system (SOMACOS Session, dl-de/zero-2-0, single body "0001") —
  the designated second-instance verification target. Verified quirk: body
  IDs are zero-padded (`/bodies/1/...` → HTTP 500, only `/bodies/0001/...`
  works), confirming D2 (enumerate body IDs from the system object, never
  construct them).
