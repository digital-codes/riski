# Tasks: api-search-expand

## 1. Core endpoints

- [x] 1.1 `src/apiServer.py`: FastAPI app with `/health`, `/search`, `/facets`, `/sessions/{id}`, CORS for local dev origins
- [x] 1.2 `graphModel.expand_neighbors`: generic depth-1 traversal driven by ADJACENCY incl. reverse entries (canonical edge direction) and direct-FK relations
- [x] 1.3 `/expand` endpoint with 404 on unknown/malformed node ids
- [x] 1.4 Integration tests (`test_integration_api.py`): contract sections, filter echo + 422, expand consistency, 404s (9 tests)

## 2. Frontend integration

- [x] 2.1 Switch the web app from static sampleData to `/search` (+ `/expand` on node demand) behind a configurable API base URL  *(api.js client, /api same-origin via vite proxy in dev; offline fallback to sampleData)*
- [x] 2.2 Merge `/expand` responses into the graph state (merge-by-id, positions preserved)  *(App.vue onExpand; DetailPanel "Nachbarn laden")*

## 3. Descoped (tracked as future work, see proposal.md)

- [x] 3.1 `/ask`: contextual follow-up questions with LLM query rewrite against session context — DESCOPED: needs prompt/session-context design; the in-memory session store is in place and remains available for a follow-up change
