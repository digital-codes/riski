# Tasks: api-search-expand

## 1. Core endpoints

- [x] 1.1 `src/apiServer.py`: FastAPI app with `/health`, `/search`, `/facets`, `/sessions/{id}`, CORS for local dev origins
- [x] 1.2 `graphModel.expand_neighbors`: generic depth-1 traversal driven by ADJACENCY incl. reverse entries (canonical edge direction) and direct-FK relations
- [x] 1.3 `/expand` endpoint with 404 on unknown/malformed node ids
- [x] 1.4 Integration tests (`test_integration_api.py`): contract sections, filter echo + 422, expand consistency, 404s (9 tests)

## 2. Frontend integration

- [ ] 2.1 Switch the web app from static sampleData to `/search` (+ `/expand` on node demand) behind a configurable API base URL
- [ ] 2.2 Merge `/expand` responses into the graph state (merge-by-id, positions preserved)

## 3. Deferred

- [ ] 3.1 `/ask`: contextual follow-up questions with LLM query rewrite against session context (needs prompt design; session store already in place)
