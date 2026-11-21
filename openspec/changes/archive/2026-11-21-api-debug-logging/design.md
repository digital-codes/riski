# Design

## Context

The API service (`src/apiServer.py`, uvicorn entry `src.apiServer:app`) handles query endpoints (`/search`, `/ask`, `/followup`, `/timeline`, `/graph`, `/summarize`, `/expand`, `/facets`) and delegates to `pgIntentRouter.py` (intent classification, fallback ladder, thread turns, clarification), `pgTimeline.py`/`pgHybridSearch.py` (recall), `pgResultSummarizer.py` (summary), and `kg/kgQueries.py`/`kg/kgFollowups.py` (kg enrichment, followup threads). Each module already uses named `logging.getLogger("riski.…")` loggers, but there is no unified request-scoped trace and no dedicated log folder — logs are scattered across uvicorn stdout captures. Env config is plain `os.getenv` throughout (no pydantic-settings, no dotenv in src). See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- One fixed, append-only debug trace file under `<project root>/log/` reconstructing a request end-to-end.
- Zero behavior change and near-zero cost when the env flag is off.
- Request correlation: one request id linking query → intent route decision → response.
- Minimal-invasive instrumentation callable from every involved script without importing API-layer objects.

**Non-Goals:**
- Distributed/OpenTelemetry-style tracing infra; request timing metrics (already covered by `riski.timing` / `RISKI_TIMING`).
- Tracing of ingestion/update pipeline scripts (only scripts involved in API interaction).
- Log rotation/compression management (single fixed file; ops may truncate/archive manually).
- Runtime toggling without restart.

## Decisions

**D1 — Tracer helper module `src/apiTrace.py` (stdlib logging only).**
A small module exposing `trace(event: str, request_id: str|None = None, **fields)` and `trace_enabled()`. Internally uses a dedicated logger `"riski.apitrace"` with a `logging.FileHandler` on `<project_root>/log/api_debug.log` (UTF-8, append mode), configured lazily at first use. Rationale: every target module already uses stdlib logging, so no new dependency and no formatter drift; a dedicated logger avoids the console StreamHandler that `db.get_logger()` would attach. Alternative considered: reusing per-module loggers with a shared file handler — rejected because entries would lose the single-line structured contract and the fixed source field.

**D2 — Structured single-line entries (JSON lines).**
Each entry is one JSON object per line: `{"ts": "<ISO-8601 with tz>", "src": "<module name>", "req": "<request id>", "event": "<event name>", ...fields}`. `ts`/`src`/`event` are always present; `req` present for request-scoped events. Single-line JSON is append-safe, greppable (`grep '"req": "r123"'`), and parseable by tools. Alternatives: plain-text f-strings (harder to filter by request), Python logfmt (less standard tooling).

**D3 — Activation: `RISKI_API_TRACE` env var, captured once at import time.**
`trace_enabled()` reads `os.getenv("RISKI_API_TRACE")` in the style of existing flags (`KG_APP_INTEGRATION`, `RISKI_TIMING`): truthy = on. The check is a cached module-level value read at first call (effectively at uvicorn startup since the app imports modules at startup), so per-call cost when disabled is a single `if`. When disabled, no FileHandler is created and `log/` is not created. Naming: `RISKI_API_TRACE` follows the established `RISKI_*` prefix and is distinct from `RISKI_TIMING` to avoid semantic confusion.

**D4 — Log file path anchored at project root, not CWD.**
The service is started from the repo root in all known setups (restart-api.sh, supervisor, API.md), but to be robust the path is anchored via `src/_bootstrap.py`-style resolution: the module computes `<parent of src package>/log/api_debug.log`. If `log/` does not exist at first write, the tracer creates it. File is opened lazily on first traced event, and entries are flushed per-line via the stdlib handler (`delay=True` on FileHandler to defer file creation).

**D5 — Request correlation via FastAPI middleware.**
A small ASGI/FastAPI middleware in `apiServer.py` generates `request_id = uuid4().hex[:12]` per HTTP request, stores it in a `contextvars.ContextVar`, and calls `tracer.trace("http_request", …)` with endpoint + method. All downstream modules read the request id from the ContextVar (or accept it explicitly where a context is already passed). This instruments every endpoint uniformly — including future ones — without wrapping each handler manually. Alternatives: passing a request id through every function signature (invasive, large diff), or relying on uvicorn access logs (no request-scoped correlation with internal events).

**D6 — Instrumentation points (minimum set for full request reconstruction).**
- `apiServer.py` middleware: `http_request` (method, path, query params summary) on entry; `http_response` (status, mode, payload summary: result_count, has_summary, related_count, chips_count, followups_count) on exit — response summary computed from the already-built dict, never the raw body.
- `pgIntentRouter.py` (in `decode`/`resolve` and the fallback/clarification branch points): `intent_route` with selected intent, confidence, top scores/reasons, slot resolutions; `intent_fallback` (step taken, reason); `clarification_mode` (trigger reason); `thread_turn` (classification + reason from `classify_thread_turn`).
- `pgHybridSearch.py` / `pgTimeline.py`: `recall` events with stage, query text (sanitized, capped), filter facets, hit counts — enough to trace "all queries from API" through recall.
- `pgResultSummarizer.py`: `summarizer` event with input document count and grounded-statement count.
- `kg/kgQueries.py` / `kg/kgFollowups.py`: `kg_related`, `kg_topic_focus`, `kg_followups`, `kg_thread` events with counts and mode.
All payloads are flat primitive fields; lists capped to first N items.

**D7 — Payload hygiene.**
- Truncation helper: strings capped at ~300 chars with `"…"` suffix marker; lists capped at 5 items plus `"_truncated": true`.
- No secrets: DB URLs, `STATE_TOKEN_SECRET`, tokens, and credentials are never fields; sealed state tokens are logged only as their first 8 chars for correlation.
- The tracer never raises: all writes wrapped so failures log once to `"riski.kg.app"`-style existing warning loggers and are then suppressed (failure latch).

**D8 — `.gitignore` entry for `log/`.**
Add `log/` to `.gitignore` next to the existing log ignores so traces never get committed.

## Risks / Trade-offs

- [Concurrent appends from multiple workers] → Single-line JSON + `delay=True` lazy open keeps appends atomic per line for practical sizes; if the deployment ever uses multiple uvicorn workers, per-request lines may interleave but remain parseable (request id provides correlation).
- [Trace file grows unbounded while enabled] → Documented as opt-in, session-scale tool; ops truncates or archives manually. Rotation deliberately out of scope (Non-Goal).
- [Slight latency when enabled] → Payload construction only runs when flag is on (`if trace_enabled()` guards at call sites via cheap wrapper); JSON serialization of small dicts is negligible vs. the 100ms+ pipeline.
- [ContextVar propagation] → FastAPI/Starlette runs sync endpoints in threadpool workers; ContextVar set in pure-ASGI middleware is copied into the handler context by Starlette, so downstream reads work; modules called outside a request (scripts, warmup) see `None` and log with `req: null`.

## Migration Plan

1. Ship tracer module + instrumentation behind default-off flag — no deployment change.
2. To use: `RISKI_API_TRACE=1` in the environment when starting uvicorn (e.g. `RISKI_API_TRACE=1 uvicorn src.apiServer:app --host 127.0.0.1 --port 11384` or export in restart script/session); verify via one `/ask` request and `grep` on `log/api_debug.log`.
3. Rollback: unset the env var and restart — file stops being written; no code path depends on the tracer.
4. Document the flag and the log file in `API.md` (monitoring section).

## Open Questions

- Exact env var name (`RISKI_API_TRACE` proposed vs `RISKI_DEBUG_TRACE`): purely a naming choice, can be decided at implementation without affecting specs/tasks.
