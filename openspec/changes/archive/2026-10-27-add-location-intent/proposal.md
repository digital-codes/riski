# Proposal

## Why

Location-targeting questions ("informationen zum friedrichsplatz", "was passiert
am friedrichsplatz", "friedrichsplatz") are answered today by the generic
topic-search pipeline: candidates come from name trigrams, name vectors and
content-chunk vectors, are capped at `top_k` (default 10) and filtered by a
0.8 rerank cutoff. Georeferences are never a retrieval signal, so the ~132
visible files linked to Friedrichsplatz are found only insofar as generic
embedding similarity happens to surface them — measured on the typo'd query
"Freidrichsplatz", the lexical signal alone recalls only 3 files. A dedicated
location intent can use the existing geo association tables as the retrieval
path and recall all linked documents deterministically, typo-tolerantly.

## What Changes

- New intent `ask_location` in `config/intents.yaml` for queries whose primary
  target is a place (street, square, district; later POIs), routed to a new
  location-scoped handler.
- New Postgres-based location resolver: `word_similarity(lower(name),
  lower(:query))` over `Street` and `District` names (~1,915 + 27 rows,
  milliseconds, typo-tolerant, no tokenization). The matcher runs on every
  routed query; a location-suffix list ("straße", "platz", "weg", …) only
  lowers the acceptance threshold — it never gates on its own.
- New slot source type `trigram` in `src/pgIntentRouter.py` slot resolution
  (today: `db` with `where_regex` and `hard` only), resolving a `location`
  slot to top-k matched locations with a minimum score; ambiguous matches
  (e.g. "Friedrichsplatz" vs "Friedrichstraße") are reported in the response
  note, following the `resolve_gremium` pattern.
- New route handler `location_scoped_search`: retrieves agenda items and files
  via the geo association tables (`Streets_items_AgendaItems`,
  `Streets_items_Files`, `Districts_items_AgendaItems`, `Districts_items_Files`,
  boilerplate-gated rows excluded), then reuses the existing rerank →
  `top_files` → summary pipeline unchanged. Falls back to unscoped hybrid
  search when no location resolves confidently.
- Prepared for later POI addition: the resolver reads a unified location
  vocabulary (street + district now; POI table slot reserved), so adding POIs
  is a data change, not a routing change.

## Capabilities

### New Capabilities

- `location-search`: location detection and location-scoped retrieval —
  resolving place references in a query against the geo vocabulary
  (streets, districts, later POIs) and using the geo association tables as
  the document recall path with the standard rerank/summarize/map pipeline
  on top.

### Modified Capabilities

- `intent-routing`: the slot vocabulary requirement gains a new value source
  type (trigram similarity against a database table, returning best-matching
  rows for a free-text query rather than exact/regex matches); the intent
  configuration gains the `ask_location` intent with its route and slot.

## Impact

- `config/intents.yaml` — new intent definition + location suffix list.
- `src/pgIntentRouter.py` — new slot source type, location resolution helper
  (mirrors `resolve_gremium`), routing entry for the new handler.
- New retrieval helper (likely `src/pgLocationSearch.py`) querying the geo
  association tables; gated per the `geo-gating` capability.
- `POST /ask` response contract extended with the resolved location(s) —
  additive, no breaking change; existing intents, `search_topic` fallback and
  decision-model degradation behavior unchanged.
- No new extensions or schema objects required: `pg_trgm` is already created
  (`src/pgGen.py`); at current vocabulary size no index is needed (measured
  26 ms cold / ~2 ms warm sequential scan). Unified location view/POI table
  is explicitly deferred.
