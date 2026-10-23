# Proposal: categorization-indexing

## Why

Search and exploration quality is limited by three gaps:

1. **Categorization is fragmented and unpersisted.** `Paper.paperType` exists
   as an authoritative column but is unused downstream; `pgAddTags` regex
   groups (≈ overlapping semantics) are only written to JSON reports; the
   generic tag infrastructure (`pgTagMgr`, `{item}_tags` + assoc tables) is
   specified but not populated. Three vocabularies describe "what kind of
   document is this" — none queryable.
2. **Name fields are indexed but never searched.** pgGen already creates
   trigram GIN indexes on `name` for Paper, File, AgendaItem, Meeting and a
   btree on `paperType`, but the search path (`pgTimeline`) is vector-only
   over `File.contentEmbeddings`. Lexical recall over names is free
   performance-wise and reaches Papers/AgendaItems/Meetings directly —
   enabling graph entry points beyond files.
3. **No faceted filtering.** Users cannot constrain results to e.g. papers
   of a certain type, consultations decided in a given year, agenda items
   with a certain outcome (`result`), or by district/submitter — although
   the columns (paperType, result, role, dates) and association tables
   (districts, later tags) exist.

Deliberately **out of scope**: content chunking / re-embedding (~50k files,
not worth the churn given the existing reranker) and importing raw full
text into Postgres (the `content`/`teaser` pyramid plus name search is
deemed sufficient; revisit later without contract changes).

## What Changes

- **Canonical tag model**: extend the existing `{item}_tags` infra with
  `scheme` (document-type | topic | district | submitter | …), `source`
  (papertype | oparl-keyword | name-regex | llm), and `confidence`; unify
  `paperType`, regex groups, and later LLM categories into it.
- **Category derivation**: backfill tags from `paperType` (authoritative),
  regex pass over names, and batch-LLM pass over `File.teaser` where the
  deterministic passes fail.
- **Provenance & coverage**: `File.contentKind` marker (fulltext vs. LLM
  summary — the cutoff decision); coverage report for
  content/teaser/embedding/name-vector gaps; single re-derivation pipeline
  order (teaser → tags → vectors stay in sync).
- **Provided-field harvest (spike-driven)**: probe `Paper.data` JSON for
  `keyword[]`, `originator*`, `mainFile`; harvest into columns/associations
  if populated, else record "not populated" and stop.
- **Hybrid search**: fuse trigram-lexical recall on name columns, name
  vectors (`{item}_name_vecs`), and content vectors (`contentEmbeddings`)
  via reciprocal-rank fusion, then rerank as today. No schema churn —
  indexes already exist.
- **Faceted filters**: structured filter model applied to search results
  and carried through to the answer set: `paperType`, date/year range,
  `AgendaItem.result`, `Consultation.role`/`authoritative`, tags by scheme,
  district. Filters SHALL compose with the graph contract as node
  attributes so the network view (add-network-view) can expose the same
  facets.

> **NOTE — follow-up obligations (do not lose):** after this change, we
> MUST return to the API contract and visualization:
> 1. The interactive API layer (`/search`, `/expand`) for the frontend
>    exploration loop (`add-network-view` design §"interaction loop").
> 2. `add-network-view` tasks 4.x consume this change's outputs: tags as
>    node `attrs`, facet filters in the UI, Person/semantic edges.
> This change therefore freezes the *search result + filter* JSON contract
> early so both consumers can rely on it.

## Capabilities

### Modified Capabilities
- `data-enrichment`: canonical tag model with schemes/provenance, teaser-
  based category derivation, contentKind provenance marker, provided-field
  harvest.
- `semantic-search`: hybrid multi-signal recall (lexical + name vectors +
  content vectors) with RRF fusion, and structured faceted filters.

### New Capabilities
- *none* (facets extend semantic-search; tags extend data-enrichment)

## Impact

- **Code**: `src/pgTagMgr.py` (scheme/source/confidence columns),
  new `src/pgCategorise.py` (derivation + backfill), `src/pgGen.py`
  (contentKind column, tag tables), `src/pgTimeline.py` (hybrid recall +
  filters + facets in results), coverage/report script.
- **Database**: tag assoc columns (additive), `File.contentKind` (additive),
  optional harvested columns from `data` JSON (additive). No breaking
  changes; no re-embedding.
- **Consumers**: `add-network-view` (node attrs, facets), future API layer
  (filter parameters), search results JSON (new `facets` + `filters`
  sections — additive).
