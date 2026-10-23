# Proposal: api-search-expand (DRAFT)

> Drafted as follow-up obligation from `categorization-indexing` task 5.2
> and `add-network-view` (interaction loop design). Finalize planning
> (specs/design/tasks) before implementation.

## Why

The web app currently ships query results as static JSON. The interactive
exploration loop needs a thin API so the frontend can run searches, expand
graph neighborhoods on click, and ask contextual follow-up questions
against a session.

## What Changes

- New FastAPI layer exposing:
  - `POST /search` — hybrid search (`query`, `filters`, `top_k`, `signals`)
    returning the full `search_and_build_timeline` result (timeline, graph
    contract section, `matched_entities`, `facets`, `applied_filters`);
    creates a server-side session.
  - `POST /expand` — depth-1 neighborhood of a node via the declarative
    adjacency map (same code path as initial traversal); returns additive
    nodes/edges for client-side merge-by-id.
  - `POST /ask` — follow-up question with LLM query rewrite against
    session context (selected entity ids + `File.content` excerpts);
    returns either a new search result or expansion, per user choice.
  - `GET /facets` — facet listing for filter UIs.
- Session state: in-memory dict (`file_sids`, entity ids, history) — no
  persistence for v1.

## Capabilities

### New Capabilities
- `search-api`: The API layer SHALL expose hybrid search, graph expansion,
  and contextual follow-up endpoints consuming the frozen search/graph
  contracts.

## Impact

- Depends on: `categorization-indexing` (hybrid recall + filters), the
  graph serialization of `add-network-view` (backend part), `src.db`/
  `src.remote` shared layers.
- Consumers: `add-network-view` frontend (dynamic updates), future
  multi-client use (MCP endpoint conceivable, cf. desinformationssystem).
- Open design questions for the full change: session expiry, expand depth
  limits, read-only DB enforcement, CORS/deployment.
