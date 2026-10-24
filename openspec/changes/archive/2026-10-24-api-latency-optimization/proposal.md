# Proposal: API Latency Optimization

## Why

The public deployment answers `/ask` and `/search` in ~3–5s per request,
noticeably slower than the dev box. Instrumented timings show the time is
dominated by *sequential* waits: 4 candidate tables × 3 recall signals are
queried one after another (~1.5–1.9s of hybrid search), the facet listing
recomputes aggregates over ~49k files on every request (~0.25s), the query
embedding re-fetched from the remote API even for repeated queries
(~0.6–0.8s), and the decision-model decode + search run strictly serial
inside `/ask` (~0.3s + search). None of these change the result — they are
scheduling and caching work.

## What Changes

- **Parallel hybrid recall**: the per-table, per-signal candidate queries in
  `pgHybridSearch.hybrid_candidates` run concurrently in a thread pool
  (12 independent read-only queries) instead of sequentially; results are
  fused exactly as before, so result parity is preserved.
- **Facet cache**: `pgHybridSearch.facets` results are cached in-process
  with a TTL (default 10 min) and invalidated after data syncs; `GET
  /facets` and per-search facet blocks reuse the cache.
- **Query-embedding cache**: small LRU keyed by (model, text) for query
  embeddings, so repeat queries skip the remote embedding round-trip.
- **`/ask` decode overlap**: the decision-model call starts while the query
  embedding is fetched (both are independent, pure network waits), shaving
  ~0.3s off every routed request.
- No change to result contracts, ranking semantics, filter semantics, or
  the `/ask` routing behavior — all optimizations are scheduling/caching
  layers behind the same responses.

## Capabilities

### New Capabilities

- (none)

### Modified Capabilities

- `semantic-search`: performance requirements — hybrid recall SHALL issue
  independent signal queries concurrently; facet listings and query
  embeddings SHALL be cached with bounded staleness. Result parity: the
  fused result for a given query/filters/signals combination MUST be
  identical to the sequential implementation.

## Impact

- **Modified**: `src/pgHybridSearch.py` (concurrent signals, facet cache),
  `src/pgTimeline.py` (embedding cache, decode/search overlap helper),
  `src/pgIntentRouter.py` (overlap usage), optionally `src/apiServer.py`
  (cache warmup on startup).
- **New**: small cache helpers (thread pool + TTL cache) — stdlib
  `concurrent.futures` + a dict-based TTL, no new dependencies.
- **Concurrency model caveat**: SQLAlchemy connections are not shared
  across threads; each parallel query uses its own connection from the
  read-only engine pool (pool growth bounded by the signal count).
- **Unaffected**: frontend, `/expand`, graph building, intent config, tests
  except performance/parity additions.
