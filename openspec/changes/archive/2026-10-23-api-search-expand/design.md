# Design: api-search-expand

## Context

The interactive exploration loop needs the frontend to run searches, grow
graphs, and read facets. All data primitives already exist:
`search_and_summarize` (hybrid search + filters + graph + summary),
`graphModel.ADJACENCY` + `expand_neighbors` (generic depth-1 traversal),
`facets` listing. The API is a thin FastAPI layer over them.

## Decisions

1. **Endpoints**: `POST /search` (full contract + sessionId), `POST /expand`
   (additive nodes/edges for merge-by-id), `GET /facets`, `GET /health`,
   `GET /sessions/{id}` (debug). Sessions are in-memory only (v1).
2. **Expand engine**: `graphModel.expand_neighbors` — driven purely by the
   declarative `ADJACENCY` map, with `reverse` entries so Files find their
   Papers while edges keep canonical direction (merge-safe). New relation
   types need only a map row.
3. **CORS**: permissive for local vite dev origins.
4. **`POST /ask` (contextual follow-up questions with LLM query rewrite)
   is deferred** — needs session-context prompt design; separate task.

## Migration Plan

Implement endpoints + expand engine + tests; run via
`uvicorn src.apiServer:app --port 8000`; frontend switches from static
sampleData to `/search` when convenient.
