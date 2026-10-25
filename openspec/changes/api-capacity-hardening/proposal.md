# Proposal

## Why

The API currently degrades in an invisible way under real usage: every
`POST /search` runs an inline LLM summary by default (`summarize=True`),
pinning a threadpool thread and an LLM slot for 10–90 s; the hybrid recall
fan-out can consume up to 12 of the 24 pooled database connections per
request, so only ~2–3 heavy searches run in parallel and further requests
wait on pool checkout (30 s timeout → spurious 500s); the anyio threadpool
(40) and the single uvicorn worker bound everything else. Capacity today is
roughly 2–5 concurrent interactive users. Meanwhile an unbounded in-memory
session store grows with every search — a slow leak that becomes an outage
on a long-lived process.

## What Changes

- **`/search` defaults `summarize=false`** — the LLM summary moves out of the
  hot path; clients use the existing `POST /summarize` follow-up (the web app
  already renders results first and fills the summary in asynchronously).
  `summarize=true` remains available for non-interactive consumers.
- **Bounded per-request DB fan-out** — a semaphore caps concurrent per-signal
  queries of the hybrid recall (currently up to 12 connections per request)
  so one heavy search cannot starve the pool; requests queue briefly at the
  semaphore instead of failing at pool checkout.
- **Right-sized threadpool and pool** — the anyio worker thread limit is
  raised (configurable) and the DB pool/overflow settings are documented and
  made configurable via environment; `pool_timeout` set explicitly so
  saturation degrades as 503 + `Retry-After`, not raw 500s.
- **Bounded session store** — `_sessions` gains TTL eviction (default 2 h)
  and a maximum size (default 1000; oldest evicted). `sessionId`s in a
  worker restart remain ephemeral (documented: sessions are in-memory, not
  persistence).
- **Worker-count decision documented** — with default round-robin proxying,
  multiple uvicorn workers break session-backed endpoints (`/geo`,
  `/summarize`); this change documents the constraint and the two viable
  scale-out paths (sticky sessions at the proxy, or stateless session
  tokens) without implementing them. Capacity target for this change: 1
  worker handles the projected load (a public RIS portal, not a high-traffic
  site).

## Capabilities

### Modified Capabilities

- `search-api`: search endpoint default summarization moves to the async
  follow-up; sessions gain TTL/size bounds; pool saturation returns 503.

### New Capabilities

(none)

## Impact

- **Code**: `src/apiServer.py` (default flag, session eviction, 503 path),
  `src/pgTimeline.py` / `src/pgHybridSearch.py` (fan-out semaphore),
  `src/db/__init__.py` (pool config via env). No schema changes.
- **Risk**: clients relying on `/search` returning `summary` inline will see
  it absent unless they pass `summarize=true` or call `/summarize` — the web
  app already uses the async pattern, so the migration is a default flip plus
  a documented breaking-change note.
- **Tests**: unit tests for session eviction (TTL + size), semaphore
  acquisition path, and the 503-on-pool-saturation response.
