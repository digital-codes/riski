# Design

## Context

Deployment today: one uvicorn worker (`riski-api.supervisor.conf`, bound to
127.0.0.1:11384), all endpoints are sync `def` → FastAPI executes them in
the anyio threadpool (default 40 threads). DB pool: `pool_size=16,
max_overflow=8` (`src/db/__init__.py:92`) sized for the hybrid-recall
fan-out of up to 12 concurrent per-signal queries per request
(`change: api-latency-optimization`). The inline LLM summary in `/search`
has a 90 s timeout with retries (`src/remote`). Sessions are an in-memory
dict with no eviction (`src/apiServer.py:62`).

## Goals / Non-Goals

**Goals:**
- Make the concurrency limits explicit, configurable, and graceful under
  saturation (queue or 503, never 500).
- Move the LLM out of the `/search` hot path by default.
- Stop the unbounded session growth.
- Give operators a documented capacity model (what limits what).

**Non-Goals:**
- No multi-worker/session-store rework (Redis, sticky sessions) — documented
  as future paths; the projected load does not need it.
- No async rewrite of the endpoints — the threadpool is sufficient once the
  LLM moves out of the hot path.
- No rate limiting here (that is `api-security-hardening`'s domain).

## Decisions

**D1 — Default `summarize=false` on `/search`.** The async `/summarize`
endpoint and the frontend's render-then-fill flow already exist; the inline
default only serves non-interactive callers, who can pass `summarize=true`
explicitly. Alternative: keep the default and make the summary async inside
the handler — rejected (doubles request lifetime complexity; the async
endpoint is the better contract). Breaking change, documented.

**D2 — Semaphore over the hybrid fan-out.** A process-wide
`threading.BoundedSemaphore` (configurable, default 24) around the per-signal
query bursts bounds total DB pressure; with the pool at 16+8 this keeps at
least two heavy searches concurrent while preventing the 12-connection burst
pattern from exhausting the pool. Alternative: shrink the fan-out itself —
rejected (that trades search latency, the exact thing
`api-latency-optimization` bought).

**D3 — Explicit saturation responses.** Pool/semaphore timeouts surface as
503 with `Retry-After` (not 500); apache's `ProxyTimeout` (see
`deployment-config`) is set above the longest legitimate request so the
proxy never converts a slow-but-healthy request into a 502.

**D4 — Session eviction: TTL + max size, oldest-first.** A lazy sweep on
session insert (no background thread) evicts entries older than the TTL and
trims to the cap. Rationale: sessions hold full result objects (graph +
timeline), which are large; 1000 sessions is generous for the projected
load. Alternative: cap-only or TTL-only — rejected (each alone is
insufficient: TTL-only still grows with burst traffic, cap-only breaks
long-lived sessions unpredictably).

**D5 — Config via environment, documented defaults.**
`RISKI_DB_POOL_SIZE`, `RISKI_DB_MAX_OVERFLOW`, `RISKI_DB_POOL_TIMEOUT`,
`RISKI_MAX_WORKER_THREADS`, `RISKI_SESSION_TTL`, `RISKI_SESSION_MAX`. The
supervisor unit sets nothing new by default; defaults preserve or improve
current behaviour.

## Risks / Trade-offs

- [Default flip breaks inline-summary clients] → documented breaking change;
  the shipped web app already uses `/summarize`; `summarize=true` still
  works.
- [Semaphore adds queueing latency under load] → bounded waits (≤ pool
  timeout) with a clear 503; better than opaque 500s and pool thrash.
- [Lazy eviction lets the store exceed the cap briefly] → acceptable; the
  sweep runs on every insert, so overshoot is bounded by in-flight requests.

## Migration Plan

1. Pool/timeout env config in `src/db` + unit tests.
2. Fan-out semaphore in the search path + unit test.
3. Session eviction + unit tests.
4. Default `summarize=false` + README/API.md note + updated integration
   tests.

Rollback: revert the commit; the default flip is the only externally
visible change.

## Open Questions

- Should `/ask` also stop summarizing inline by default? (It has the same
  shape; deferred until `/search` behaviour ships.)
