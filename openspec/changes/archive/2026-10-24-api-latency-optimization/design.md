# Design

## Context

Measured per-request budget on the public box (single uvicorn worker,
`/ask`, RISKI_TIMING=1): decode 0.2–0.3s (SystemOne network) + embed_query
0.6–0.8s (remote API) + `hybrid_candidates` 1.5–1.9s (4 tables × up to 3
signals, strictly sequential) + `facets` 0.25s (full-table aggregates:
48,906 files, 13,820 papers, 18,950 agenda items) + related-object
traversal + LLM summary (seconds, already async client-side). All heavy
steps are I/O-bound remote/DB waits; nothing is CPU-bound. The result is
purely deterministic per (query, filters, signals), which makes caching and
parallelism safe.

Connection reality: `src/db` keeps one engine per role; SQLAlchemy pools
are not thread-safe per-connection, but `engine.connect()` per query is.
The read-only engine's default pool size must grow or be explicitly sized
for the parallel fan-out (max 12 concurrent queries in one request).

## Goals / Non-Goals

**Goals:**
- Cut `/search` wall time by overlapping the independent DB waits
  (target: hybrid phase from ~1.5–1.9s to ~0.5–0.7s on the public box).
- Make repeat traffic cheap: facet aggregates and query embeddings served
  from in-process caches.
- Zero result drift: parity harness comparing fused output before/after.

**Non-Goals:**
- LLM summary latency (already async client-side; server-side streaming is
  a separate future change).
- Cross-process caches (Redis etc.) — single-box deployment, in-process is
  sufficient.
- Changing ranking, filters, thresholds, or any response contract.
- Multiple uvicorn workers as a code change (operational flag, documented
  already).

## Decisions

### D1: Parallelize at the signal level with a bounded ThreadPoolExecutor
`hybrid_candidates` builds a list of `(label, callable)` — one per
(table, signal) with an enabled signal — and runs them on a module-level
`ThreadPoolExecutor` (max_workers = 12, matching the worst case; threads
are cheap for I/O waits). Each task opens its own `engine.connect()`
(extracted from the shared connection parameter — the function signature
gains an optional `engine` so the parallel path can create per-task
connections, while the sequential fallback keeps accepting `conn`).
Exceptions per task are caught and logged; that signal contributes an empty
list.

Alternatives rejected:
- *asyncio rewrite* — the call sites are sync (FastAPI sync handlers run
  in a threadpool anyway); a full async port touches every layer for no
  extra gain at 12 tasks.
- *Parallelize per table only* (4 tasks) — leaves the 3-signal fan-out
  serial; signal-level gets the max overlap since signals have very
  different durations (content vectors ~0.1s vs lexical ~0.4s).

### D2: Facet cache — TTL dict, invalidated by the sync pipeline
Module-level `{ts, payload}` cache in `pgHybridSearch`; TTL 600s
(`RISKI_FACET_TTL` env override, 0 disables). Invalidation: the sync
pipeline (`src/syncIncremental.py` import step) calls
`invalidate_facet_cache()` after pgGen completes. `facets()` returns the
cached payload verbatim (same dict content, deep-copied at the boundary to
protect callers from mutating the cache). The per-search facet block in the
timeline flow uses the same cache.

Alternative rejected: caching in the DB (materialized view) — adds DDL
maintenance for a 0.25s win; TTL in-process is enough.

### D3: Query-embedding LRU keyed by (model, text)
`functools.lru_cache(maxsize=256)` around a `_embed_cached(model, text)`
helper in `pgTimeline` — `embed_query` delegates to it. Content/document
embeddings (bulk paths in pgAddVecs/pgBackfillNameVecs) do NOT go through
it. numpy arrays are immutable-by-convention here; return as-is (same
object reuse is safe: callers only read).
Note: `lru_cache` is process-local; with `--workers N` each worker warms
its own — acceptable.

### D4: Decode/search overlap in `/ask`
`pgIntentRouter.ask` currently decodes (SystemOne, ~0.25s) *then* runs the
search (which internally embeds the query, ~0.7s). Both need only the raw
query — run `router.decode(query)` and the embedding fetch concurrently
via the same executor, then hand the embedding into
`search_and_summarize`. Because `search_and_summarize` embeds internally,
the overlap is implemented by pre-warming the D3 cache: submit
`_embed_cached` as a task before starting decode, so by the time the
search path asks for it, it's (usually) already resolved. Minimal
invasive change: two lines in `ask()`.

### D5: Parity harness before/after
A recorded-baseline test: run `hybrid_candidates` sequentially (a
`force_sequential` flag kept in the module for the test) and concurrently
over a set of real queries on the live DB; assert identical fused output
(scores and order). This test is the acceptance gate for D1 and guards
future refactors.

## Risks / Trade-offs

- [Thread-pool + engine pool exhaustion] → pool_size tuned explicitly
  (`pool_size=16, max_overflow=8` on the read-only engine creation is
  already the default in `src/db`; verified at D1 implementation); the
  executor is bounded at 12 so requests can't oversubscribe.
- [SQLite/blocking DB drivers break per-thread connections] → the project
  is PostgreSQL-only at runtime (psycopg2); unit tests that need the
  parallel path use the live-DB marker; `force_sequential` remains as
  fallback for odd environments.
- [Stale facets after manual DB writes outside syncIncremental] → TTL
  bounds staleness to 10 min; `RISKI_FACET_TTL=0` disables caching
  entirely.
- [lru_cache holds numpy arrays (~8KB each × 256)] → 2MB worst case,
  negligible; keyed by text so unbounded query growth is capped at 256
  entries.
- [Mistral/SystemOne latency variance dominates] → out of scope (non-goal);
  the overlap in D4 only hides the embedding wait.

## Migration Plan

1. Ship D1 + parity harness (biggest win, behavior-neutral).
2. Ship D2 + D3 (pure caches, env-flag kill switches).
3. Ship D4 (two-line overlap; relies on D3).
Rollback: each is independently revertible; caches disable via env
(`RISKI_FACET_TTL=0`), parallelism via `RISKI_PARALLEL_SIGNALS=0`
(added kill switch keeping the sequential path callable).

## Open Questions

- None blocking; kill-switch env names to be confirmed at implementation.
