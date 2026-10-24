# Tasks

## 1. Parallel hybrid recall (D1)

- [x] 1.1 Refactor `hybrid_candidates` to a task list: per (table, enabled signal) build a callable; add module-level ThreadPoolExecutor (max_workers 12) with per-task connection from the read-only engine; add `force_sequential` flag (env `RISKI_PARALLEL_SIGNALS=0` honoured) keeping the current code path; per-task exception → log warning, empty candidate list; verify: unit test with a stubbed engine asserting tasks execute concurrently (two blocking tasks with sleeps complete in ~max not sum) and a raising task yields empty list without failing the search.
- [x] 1.2 Verify engine pool sizing for the fan-out (read-only engine `pool_size`/`max_overflow` accommodate 12 concurrent queries; adjust `src/db` defaults if needed); verify: integration smoke on live DB with signals toggled runs without pool-timeout warnings.
- [x] 1.3 Parity harness: live-DB test running a fixed set of real queries through sequential and concurrent paths (same filters/signal toggles) asserting identical `matched_entities` ordering and `file_candidates` scores; verify: `python -m pytest src/tests/test_integration_parity.py -q` green. *(Parity exposed non-deterministic SQL tie order on equal scores — fixed with deterministic `oparlKey` tiebreakers in all three recall ORDER BYs.)*

## 2. Facet cache (D2)

- [x] 2.1 Implement TTL cache in `pgHybridSearch.facets` (module-level, TTL 600s, `RISKI_FACET_TTL` override, 0 disables, deep-copy boundary) + `invalidate_facet_cache()`; verify: unit test with monkeypatched clock asserting second call skips recomputation and TTL expiry recomputes.
- [x] 2.2 Call `invalidate_facet_cache()` after the import step in `src/syncIncremental.py`; verify: unit test asserting the hook runs (monkeypatched invalidate called once after import).
- [x] 2.3 Wire the per-search facet block in the timeline flow to the same cache; verify: integration test asserting two consecutive `/search` calls with different queries reuse cached facets (facet block identical, no second aggregate scan — observable via query-count mock or timing). *(The timeline flow already calls the same `pgHybridSearch.facets` — one cache point covers `/facets` and per-search blocks; verified 0.25s → 0.1ms on hit.)*

## 3. Query-embedding cache (D3)

- [x] 3.1 Add `functools.lru_cache(maxsize=256)` wrapper in `pgTimeline.embed_query` path keyed by (model, text); bulk document-embedding paths must NOT use it; verify: unit test with a stubbed remote asserting one remote call for two identical `embed_query` invocations and distinct calls for distinct texts.
- [x] 3.2 Confirm no bulk path regressed: pgAddVecs/pgBackfillNameVecs embedding calls bypass the cache; verify: unit test or code-review assertion in test file that the wrapper is only applied to the query helper.

## 4. Decode/search overlap (D4)

- [x] 4.1 In `pgIntentRouter.ask`, submit the query-embedding pre-warm to the executor before `router.decode(query)` so embedding and decode run concurrently; verify: unit test with stubbed decoder + slow stubbed embedding asserting wall time ≈ max(decode, embed) not sum.
- [x] 4.2 Add `RISKI_PARALLEL_SIGNALS=0` kill-switch handling end-to-end (sequential path unchanged when disabled); verify: unit test asserting sequential execution when env unset to 1.

## 5. Verification

- [ ] 5.1 Full suite + `openspec validate api-latency-optimization`; verify: suite green, validation passes.
- [ ] 5.2 Before/after measurement on the live DB: record RISKI_TIMING output for 3 real `/search` + 3 `/ask` queries against the current main and the optimized branch; record numbers in `docs/` (or the task output) — target: hybrid phase < 60% of baseline, repeat-query embedding ≈ 0; verify: recorded comparison shows improvement without result drift (top_files identical).
