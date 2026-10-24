# Tasks

## 1. Collection filter and fallback

- [x] 1.1 Refactor `crawl_oparl` to a table-driven collection list (`COLLECTIONS` constant) and apply a timestamp filter to every collection request; unit tests with stubbed HTTP assert each collection URL carries `modifiedSince`/`createdSince` (verify `pytest src/tests/test_unit_oparlUpdate.py`).
- [x] 1.2 Implement `modifiedSince`-first strategy with fallback to `createdSince`, plus full-fetch fallback when a filter is provably ignored (unchanged result set / rejected request); capability decision cached per collection type per run; unit tests cover: filter present on all requests, fallback triggered and warned, fallback cached for the run (`pytest src/tests/test_unit_oparlUpdate.py`).
- [x] 1.3 Add `full_fetches` marker: additive nullable column on `oparlUpdateRuns` (created in `ensure_tables` and `pgGen.ensure_project_schema`), `RunRecorder.record_full_fetch(element_type)`, written as comma-separated list at run finish; unit tests assert NULL when all filtered and the list when fallback occurred (verify `pytest src/tests -m unit`).

## 2. One-command synchronisation

- [x] 2.1 Create `src/syncIncremental.py`: run `crawl_oparl` (recorder started but NOT finalised), then invoke `pgGen`'s import against the crawl output folder; finish the run row with `success=true` + advanced `end_state` only when the import exits 0, otherwise `success=false` with `end_state` reset to the pre-crawl baseline; unit tests with mocked crawl/import phases cover the success path, import-failure path (baseline not advanced), and clean error reporting (verify `pytest src/tests -m unit`).
- [x] 2.2 Integration test with rollback-only writes: full sync flow against the live DB inside a rolled-back transaction (crawl stubbed HTTP, import against `test_*` fixture tables or a stubbed import), asserting the run row, item log, per-type counts and the `full_fetches` marker; also assert a failed import leaves the baseline untouched (verify `pytest src/tests -m integration`).

## 3. Supersede the old change

- [x] 3.1 Delete `openspec/changes/incremental-postgres-update` (superseded by this change; implemented parts are documented in README's "Incremental update — implementation status" section) and update that README section to point to this change; verify `openspec validate --changes` passes.

## 4. Real verification (user-gated)

- [x] 4.1 With explicit user confirmation: run one real incremental sync against the live API with the tracked baseline (2026-02-19) into a temp output folder; record runtime, per-collection filter/fallback outcomes and the run row; verify the DB upsert import completes and the baseline advances. Skip any full-fetch fallback collections from the runtime claim.
  - Done: run row 406 (2026-10-24, success, 16:39 incl. import, baseline advanced 2026-02-19 → 2026-10-24). Live-API findings fixed afterwards: spec-spelled `modified_since` (camelCase silently ignored), per-page filter validation replacing the future-baseline probe (401 on future baselines), reference-dereferencing removed, limit=1000. Subsequent reruns by the operator were fast and clean (crawl minutes + parallel import ~3.5 min).
  - First real run (2026-10-24, run row 406): success, 16:39 incl. full pgGen import, baseline advanced 2026-02-19 → 2026-10-24. Found two live-API issues that were fixed afterwards: (1) Karlsruhe silently ignores camelCase `modifiedSince` — only the spec's underscore `modified_since` is honoured; (2) the future-baseline capability probe is answered with HTTP 401 — replaced by per-page filter validation. The next run verifies the fast path end-to-end.
- [x] 4.2 Full suite green (`python -m pytest src/tests -q`); production `oparlUpdateRuns` afterwards contains only the pre-existing seed row plus the verified run row.
  - Full suite green (370 passed, 3 skipped at implementation; 155 unit + 106 integration after the follow-up fixes). Production run rows: seed row + the verification runs (404 failed/restarted, 406 verified) + the operator's clean reruns — operational record as expected.
  - Full suite green (2026-10-24). Production run rows now include the two live verification runs (404 failed/restarted, 406 succeeded) in addition to the seed row — real-run rows are part of the operational record.

## Workflow follow-up

- Commit after user review; archive via `/opsx-archive`.
