# Proposal

## Why

Debugging the /ask pipeline (intent routing, kg enrichment, thread/followup handling, response shaping) currently requires ad-hoc log greps across scattered uvicorn stdout captures (apiServer*.log, results/apiServer_run.log) with no unified record of what query came in, why it was routed a particular way, and what was sent back to the frontend. After kg-app-integration there is no way to reconstruct a single request end-to-end, which makes support and regression analysis slow and guesswork-heavy.

## What Changes

- Add an opt-in debug tracing facility for the API service: when enabled via an environment variable at uvicorn startup, all scripts involved in API interaction write structured debug entries to a fixed log file in a `log/` folder at the project root.
- Each debug entry contains an ISO-8601 timestamp, the source script/module, and a useful payload (not raw dumps) describing the event.
- The trace specifically records:
  - every incoming API query (endpoint, sanitized user query, request parameters, request id);
  - intent route decisions and their reasons (chosen intent, confidence, slot resolutions, fallback/clarification triggers, thread-turn classification);
  - every response sent towards the frontend (endpoint, response mode, key payload summaries such as result counts, summary/chips/related-docs presence, status).
- Activation is via env variable when starting the uvicorn API service (e.g. `RISKI_DEBUG_TRACE=1 uvicorn src.apiServer:app ...`); default is off, zero overhead when disabled, and no behavior change to responses.
- Scripts covered: apiServer.py (all query endpoints + response paths), pgIntentRouter.py, pgHybridSearch.py, pgTimeline.py, pgResultSummarizer.py, kg/kgQueries.py, kg/kgFollowups.py.

## Capabilities

### New Capabilities
- `api-debug-tracing`: Environment-gated end-to-end debug tracing of the API request flow — incoming queries, intent routing decisions with reasons, and frontend-bound responses — written to a fixed log file with timestamp and source identification.

### Modified Capabilities
(none — no requirement-level behavior of existing endpoints changes; tracing is passive observation)

## Impact

- **Code**: `src/apiServer.py` (endpoint wrappers/response paths), `src/pgIntentRouter.py`, `src/pgHybridSearch.py`, `src/pgTimeline.py`, `src/pgResultSummarizer.py`, `src/kg/kgQueries.py`, `src/kg/kgFollowups.py`, plus a new small tracing helper module under `src/`.
- **Operations**: new `log/` directory at project root (gitignored); env var documented in `API.md`; `scripts/restart-api.sh` and supervisor conf remain unchanged unless the env var is set externally.
- **Dependencies**: none new (stdlib logging only).
- **Performance**: when disabled, no handlers attached and negligible cost; when enabled, file-appender throughput is bounded by request rate and payloads are size-capped.
