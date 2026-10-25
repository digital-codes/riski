# Proposal

## Why

Two map defects, observed with the default query "wo liegt die Governance
für Digitalisierung bei der Stadt Karlsruhe":

1. **Header-address false positives.** The map shows "Hebelstraße"
   referencing "Antrag Nr 7 (SPD, Digitalisierung)" — but that street only
   appears in the document's sender/recipient address block (Briefkopf).
   The chain: markdown starts with the address block → the teaser is built
   from the content start → the literal street/district matcher
   (`pgAddFileGeoRefs`, name + teaser) matches the address street → a
   geo link is written. The reference has nothing to do with the document's
   main content.
2. **Disabled documents leak into the map.** `/geo` gates on the
   summarizer's refusal verdict (`summary_refused`) but not on the user's
   document exclusion set (`summary_excluded`) — a document the user has
   switched off in the summary list still contributes map items (document
   #2 in the list, not enabled, supplies the Hebelstraße hit).

## What Changes

- **LLM geo gate (`src/geoGate.py`, class `GeoGate`)** — every street/
  district ↔ file link (and agenda-item link) gets a verdict from the
  summary model: does the mention belong to the main content, or is it
  boilerplate (Briefkopf address, footer, Behörden/firm address, venue,
  Impressum)? One batched LLM call per document (all candidate names in
  one prompt), input = `File.content` (bounded) + the matched names with
  their match context. Verdicts stored on the association rows:
  `gate_status` (`content` | `boilerplate` | `unsure`), `gate_reason`,
  `gated_at`, `gate_model`.
- **Gate at write time** — `pgAddFileGeoRefs.match_files` (and the
  agenda-item ref creators `pgAddStreetRefs` / `pgAddDistrictRefs`) consult
  the gate for newly created links; `boilerplate` links are never shown.
  LLM unavailable ⇒ rows left `gate_status = NULL` (shown, flagged for the
  next cleanup run).
- **One-off cleanup** — `src/pgGeoGateCleanup.py` gates all existing
  `NULL` rows (resumable: the NULL query is the cursor; `--dry-run`,
  `--limit`, `--reprocess unsure`, `--purge-boilerplate`). Existing data is
  *marked*, not deleted (map filtering makes marks sufficient; deletion is
  an optional flag).
- **Map gating (server + already-working client refresh)** — `/geo`
  additionally excludes the session's `summary_excluded` files; the
  frontend already re-fetches `/geo` after every toggle/refine
  (`App.vue` calls `fetchGeo()` on each exclusion change), so updating the
  list updates the map with no client changes. `collect_geo` filters
  `gate_status` (hide `boilerplate`; show `content`, `unsure` and legacy
  `NULL` so the map keeps working while the cleanup runs).

## Capabilities

### New Capabilities

- `geo-gating`: LLM-based relevance gate for street/district geo
  references — prompt contract, verdict storage, write-time gating and the
  resumable cleanup pass.

### Modified Capabilities

- `map-view`: georeference collection excludes user-disabled documents;
  the GeoJSON endpoint filters gate status.

## Impact

- **Code**: new `src/geoGate.py` (uses the shared `src.remote` chat layer →
  summary model, no new dependencies); small integrations in
  `pgAddFileGeoRefs`/`pgAddStreetRefs`/`pgAddDistrictRefs`; `pgGeo.collect_geo`
  gate filter; `/geo` exclusion filter; new cleanup script.
- **Database**: additive columns on the four geo association tables
  (`gate_status`, `gate_reason`, `gated_at`, `gate_model`) — created on
  demand, no schema rebuild.
- **Cost**: one summary-model call per document that has new geo links
  (batched names per call), plus the bounded one-off cleanup pass over
  existing links.
- **Risk**: LLM misclassifies a genuine content mention as boilerplate —
  mitigated by the `unsure` verdict (shown, not hidden) and by keeping the
  row (recoverable, re-gatable with `--reprocess`).
- **Tests**: unit tests for prompt building/verdict parsing with a stubbed
  chat client; gate filter and exclusion filter tests; cleanup resumability.
