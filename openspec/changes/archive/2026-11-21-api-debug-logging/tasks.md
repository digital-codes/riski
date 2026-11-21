# Tasks

## 1. Tracer module

- [x] 1.1 Create `src/apiTrace.py` with `trace_enabled()` (cached `RISKI_API_TRACE` env check, default off), `trace(event, req=None, **fields)`, truncation helpers (300-char strings, 5-item lists), and a fail-safe wrapper that suppresses write errors after logging one warning — verify with a unit test in `src/tests/` that asserts disabled mode creates no file and enabled mode writes one JSON line with `ts`, `src`, `event` keys
- [x] 1.2 Configure the dedicated `"riski.apitrace"` logger with a lazy UTF-8 append `FileHandler` at `<project root>/log/api_debug.log` (path anchored to the src package parent, `log/` created on first write) — verify unit test: entries land in `log/api_debug.log` regardless of the CWD the test process runs from, and each entry is a single parseable JSON line
- [x] 1.3 Add `log/` to `.gitignore` and verify `git status` stays clean after a traced test run

## 2. Request correlation in the API layer

- [x] 2.1 Add a request-id `ContextVar` plus FastAPI middleware in `src/apiServer.py` that generates `req` (uuid4 hex, 12 chars), emits `http_request` (method, path, sanitized query summary) on entry and `http_response` (status, mode, payload summary: result_count, has_summary, related_count, chips_count, followups_count — never the raw body) on exit — verify with a unit/integration test that one `/ask` call produces both entries carrying the same `req` value
- [x] 2.2 Ensure modules called outside a request context (warmup, scripts importing `src.apiTrace`) trace with `req: null` without errors — verify via existing import-time smoke (module imports cleanly with and without the env flag set)

## 3. Intent routing trace

- [x] 3.1 Instrument `src/pgIntentRouter.py` decision points: `intent_route` (selected intent, confidence, top scores, slot resolutions), `intent_fallback` (ladder step, reason), `clarification_mode` (trigger reason), `thread_turn` (classification + reason from `classify_thread_turn`) — verify with unit tests using the existing intent-router test fixtures: one routed query, one fallback case, one clarification case, one follow-up thread case, each asserting the expected event and reason fields in the trace file
- [x] 3.2 Confirm trace never alters routing behavior — verify the full existing `src/tests/` intent-router test suite passes unchanged with the flag enabled

## 4. Recall and summarizer trace

- [x] 4.1 Instrument `src/pgHybridSearch.py` and `src/pgTimeline.py` stage entries with `recall` events (stage, sanitized capped query, filters, hit counts) so every query from the API through recall is traceable — verify with an integration test hitting `/search` that asserts a `recall` entry linked to the request id
- [x] 4.2 Instrument `src/pgResultSummarizer.py` with a `summarizer` event (input document count, grounded-statement count) — verify via existing summarizer tests (or a new one) that the entry appears on an `/ask` call

## 5. KG layer trace

- [x] 5.1 Instrument `src/kg/kgQueries.py` (`kg_related`, `kg_topic_focus` with counts) and `src/kg/kgFollowups.py` (`kg_followups`, `kg_thread` with mode; state tokens only as first 8 chars) — verify with the existing `test_unit_kg_*` tests extended/parametrized with the flag on, asserting entries appear with the request id when invoked in request context

## 6. Integration verification and documentation

- [x] 6.1 Run `scripts/test_kg_api.py` E2E against a locally started `RISKI_API_TRACE=1 uvicorn src.apiServer:app` instance and confirm `log/api_debug.log` reconstructs one full request: http_request → recall → intent_route (+fallback/thread events where applicable) → kg events → http_response, all sharing one `req` value
- [x] 6.2 Restart the same service without the env flag, repeat one `/ask` request, and confirm no new entries are written and `/ask` responses match the untraced baseline (flag-off neutrality check)
- [x] 6.3 Document the flag, log file location, and entry format in the monitoring section of `API.md` — verify the documented startup command (`RISKI_API_TRACE=1 uvicorn src.apiServer:app ...`) runs as written

## Workflow follow-up

- Archive the change after the review requirements are satisfied.
- Verify the archived result.
