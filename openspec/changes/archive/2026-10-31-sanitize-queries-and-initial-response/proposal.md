# Sanitize queries and canned initial response

## Why

Two gaps around the work page's query flow:

1. **User queries are unsanitized.** `/search` and `/ask` accept any string
   (`query: Field(min_length=1)`) — control characters, HTML/script
   payloads, absurd lengths (the query is echoed into LLM prompts and the
   stored summary) and whitespace-only input all pass. Robust input
   sanitation is expected before exposing the API beyond the first-party
   frontend.
2. **The initial view runs a full retrieval cycle.** The work page opens
   with the default query ("wo liegt die Governance für Digitalisierung bei
   der Stadt Karlsruhe") and executes the entire staged pipeline
   (recall → timeline → graph → summary → geo) just to render the landing
   state. The response for this ONE fixed query is deterministic enough to
   be shipped as a JSON file the frontend reads directly — faster initial
   paint, no backend dependency for the landing view. (An offline-sample
   mechanism already exists — `loadSampleFallback` + `app/src/assets/
   sampleData.json` — but its content is stale (different query, contract
   before the graph-scope/expandable-types changes) and it only engages
   when the API is unreachable.)

## What Changes

- **Query sanitation**: `/search` and `/ask` validate the query — allowed:
  letters (German alphabet incl. umlauts/ß), digits, whitespace and common
  punctuation; max 250 characters (about two lines); non-empty after
  trimming. Everything else → HTTP 400 with a clear German error message.
  Applies to user-facing query fields only (session/node-id endpoints
  unchanged).
- **Initial-query snapshot**: a capture script stores the complete staged
  response for the default query (stage-1 fields, timeline, documents-scope
  graph with `expandable_types`, summary, geo FeatureCollection) as
  `app/src/assets/sampleData.json`. The work page uses this file DIRECTLY
  for the default query (no backend round-trip); other queries hit the API
  as before. The file also remains the offline fallback (the stale error
  banner is shown only in the unreachable case, not in the canned-start
  case).
- Interactive follow-ups (refine, file toggles, expand) require a live
  session — the canned start disables them with a hint instead of failing.

## Capabilities

### New Capabilities

- `initial-query-snapshot` — the work page's default query is answered
  from a versioned JSON snapshot (captured from the real pipeline), used
  directly as the initial render and as the offline fallback; interactive
  session actions are disabled in snapshot mode.

### Modified Capabilities

- `search-api` — user query fields SHALL be validated (allowed character
  classes, 250-char maximum, non-empty); violations SHALL be rejected with
  HTTP 400 and a clear message.

## Impact

- `src/apiServer.py` — query validation helper applied in `/search` and
  `/ask` (400 responses); `SearchRequest`/`AskRequest` docs.
- `scripts/capture_initial_response.py` (new) — runs the staged pipeline
  for the default query and writes `app/src/assets/sampleData.json`.
- `app/src/components/WorkPage.vue` — canned-start path for the default
  query (no API cycle, no error banner), snapshot-mode guard for session
  actions.
- `app/src/assets/sampleData.json` — regenerated for the default query.
- `src/tests/` — sanitation unit tests (400 cases); snapshot loader test
  (frontend build-time check optional).
