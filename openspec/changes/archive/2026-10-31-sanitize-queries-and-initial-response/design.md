# Design: sanitize-queries-and-initial-response

## Context

- Query entry points: `POST /search` (`SearchRequest.query`) and
  `POST /ask` (`AskRequest.query`), both `Field(min_length=1)`. FastAPI's
  validation errors return 422 — the requirement is 400 with a readable
  German message, so validation happens explicitly in the endpoint bodies,
  not via pydantic constraints.
- The query is echoed into LLM prompts (summarizer system/user content)
  and stored in the session result — the sanitation also bounds prompt
  injection surface.
- The work page (`app/src/components/WorkPage.vue`) opens with
  `DEFAULT_QUERY` from `instanceStore` (config `frontend.default_query`)
  and runs the staged pipeline via `runSearch()`; an existing
  `loadSampleFallback()` applies `app/src/assets/sampleData.json` (all
  stages at once) when the API is unreachable. The current sample file is
  stale: query "rückbau herrenalber strasse", contract before the
  graph-scope/expandable-types changes.
- The session-dependent interactions (refine, file toggles, expand, geo
  refetch) call API endpoints with the `sessionId` from stage 1 — a
  snapshot has no live session.

## Goals / Non-Goals

Goals:

- 400-reject invalid queries on `/search` and `/ask` with clear German
  messages; no retrieval or decision-model call for invalid input.
- Instant landing view for the default query from a bundled snapshot; API
  behaviour for every other query unchanged; offline fallback preserved.
- A capture script keeps the snapshot regenerable (never hand-edited).

Non-Goals:

- No rate limiting, authentication, or output sanitization (separate
  concerns).
- No general caching of arbitrary query responses — exactly ONE snapshot
  (the default query).
- No change to internal query handling downstream of the API (stop-term
  stripping etc. stays as is).

## Decisions

### D1: Explicit endpoint validation, not pydantic constraints

A `validate_user_query(query) -> str` helper in `src/apiServer.py` raises
`HTTPException(400, detail=<German message>)`; `/search` and `/ask` call it
first. Pydantic-level constraints would produce 422s with English
technical detail — the requirement asks for 400 + readable message.

Rules: trim; non-empty; length ≤ 250; allowed character classes = Unicode
letters (covers German umlauts/ß and other European letters), digits,
whitespace, and a punctuation set (`.,;:!?()[]{}„“"''\-–/&%+*#@=_` —
deliberately WITHOUT angle brackets, so HTML/script markup is rejected).
The punctuation set is an allow-list, so control characters, zero-width
characters and emoji fail. Rejects name the problem ("enthaelt unzulaessige
Zeichen" / "zu lang (maximal 250 Zeichen)" / "leer").

- Alternative: strip/normalize instead of reject — rejected: silently
  rewriting user input hides problems; rejection is explicit and cheap.

### D2: Snapshot = one JSON with all staged payloads, captured live

`scripts/capture_initial_response.py` runs the real pipeline for the
default query (`_stage1_search_fn` → `timeline_stage` → `graph_stage` →
`ResultSummarizer` → `/geo` collection) and writes
`app/src/assets/sampleData.json`:
`{query, ...stage1 fields, sessionId: null, timeline, graph (documents
scope, expandable_types included), geo_available, geo (FeatureCollection),
summary, summary_refused, snapshot: true}`.
`sessionId` is null — snapshot mode has no live session.

- Alternative: fetch-format file under `app/public/` — rejected: the
  existing bundled-asset import is offline-safe and versioned with the
  build; public/ would add a runtime fetch dependency.

### D3: Frontend routes the default query to the snapshot

`runSearch()`: when the submitted (trimmed) query equals `DEFAULT_QUERY`,
apply the snapshot directly (`applyStage1` + timeline + `applyGraph` with
`geo_available` + `geoFC` + summary slots) with `snapshotMode.value =
true` — zero API calls, no error banner, but a subtle hint
("Beispieldatensatz — Suche starten für Live-Ergebnisse"). Any other
query: API as today, `snapshotMode = false`. `loadSampleFallback` keeps
working for the unreachable case (reuses the same apply path + banner).

### D4: Snapshot-mode guard on session actions

A `snapshotMode` ref guards the session-dependent actions: refine button,
file toggles, expand (DetailPanel button) render disabled with the hint
"Beispielsatz — bitte neue Suche starten". Geo display works from the
snapshot's stored FeatureCollection (no /geo refetch loop — `fetchGeo`
short-circuits in snapshot mode).

- Alternative: silently no-op the actions — rejected: invisible failures
  confuse; the hint explains the state.

## Risks / Trade-offs

- [Snapshot goes stale as the pipeline/data evolves] → D2 capture script +
  a task to re-run it whenever the staged contract changes; the file says
  its capture date.
- [Default-query results drift from live] → acceptable for a landing
  demo; a "neue Suche" immediately goes live.
- [Allowed-punctuation allow-list too strict/lenient] → start with the
  common set; widen only with cause (rejection message is actionable).

## Migration Plan

Backend validation is additive (deploy anytime). Frontend ships with the
regenerated snapshot — build the frontend after running the capture
script. Rollback = revert.

## Open Questions

None.
