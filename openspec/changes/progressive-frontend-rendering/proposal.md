# Proposal: Progressive frontend rendering

## Why

Today the frontend shows nothing until the entire search pipeline has finished: `/ask` and `/search` return intent, file list, timeline, and graph in one monolithic response, so the user stares at empty panes for the full request duration (~1.5 s warm, up to ~2.4 s cold on `/ask`). The file list only depends on recall (embedding + hybrid candidates + rerank), which is ready well before the timeline and graph are built — so the UI could already show meaningful content earlier.

## What Changes

- Split the monolithic search pipeline (`search_and_build_timeline` in `src/pgTimeline.py`) into staged server-side steps: recall → file list, then timeline, then graph.
- Add staged API endpoints: after `/ask` (or `/search`) returns intent + sessionId + `top_files` immediately, the client fetches the timeline and then the graph for that session in follow-up calls (same two-phase pattern already used by `/summarize` and `/geo/{sessionId}`).
- Frontend (`app/src/components/WorkPage.vue`): replace the single all-or-nothing `applyResult` with per-stage updates — the file list pane renders as soon as the first response arrives, the timeline pane when the second stage returns, the network view last.
- `TimeLine.vue` currently derives both the file list and the timeline from one prop; split it so each card can be filled and show a loading state independently.
- All other panes keep their existing behavior: summary/topic list via `/summarize`, map via `/geo/{sessionId}` — unchanged.

## Capabilities

### New Capabilities

- `staged-results`: Server-side staged delivery of search results per session — the file list is available after recall, the timeline after timeline building, the graph last; each stage is fetchable separately by sessionId.

### Modified Capabilities

- `search-api`: The `Search Endpoint` requirement changes from "full result contract in one response" to a staged contract (first response returns intent-related fields, sessionId and `top_files`; timeline and graph are fetched via follow-up endpoints).
- `intent-routing`: The `Ask endpoint` requirement changes accordingly — `/ask` returns the staged first response plus decoded intent; timeline/graph follow via the staged endpoints.
- `site-shell`: The `Work page hosts the search UI and scrolls` requirement is extended so panes render progressively with per-pane loading indicators instead of appearing all at once.

## Impact

- **Backend**: `src/apiServer.py` (new staged endpoints, session store usage), `src/pgTimeline.py` (split `search_and_build_timeline` into recall / timeline / graph stages), `API.md` (documented contract change).
- **Frontend**: `app/src/api.js` (new fetch wrappers), `app/src/components/WorkPage.vue` (staged state updates, per-pane loading flags), `app/src/components/TimeLine.vue` (independent file-list/timeline props + loading states).
- **API contract**: **BREAKING** for any client relying on receiving `timeline` and `graph` inside the `/ask`/`/search` response body. In this prototype the only consumer is the bundled frontend, which is updated in the same change.
- No database schema, import, or enrichment changes.
