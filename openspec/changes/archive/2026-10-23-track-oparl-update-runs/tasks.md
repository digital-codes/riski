# Tasks

## 1. Tracking module

- [x] 1.1 Create `src/oparlRunLog.py` with the three table definitions (`oparlUpdateRuns`, `oparlUpdateRunItems`, `oparlUpdateRunTypeCounts` per design D1), additive create-if-missing, and best-effort `GRANT SELECT` to the read-only role; verify a unit test asserts the DDL statements issued on a mocked engine.
- [x] 1.2 Implement `RunRecorder` (`start(baseline)`, `record_item(element_type, oparl_id, oparl_key, status)`, `record_error()`, `finish(success)`) with in-memory batching, upsert-based idempotence on (`run_id`, `oparl_id`) and unique (`run_id`, `element_type`), plus baseline resolution per design D6 (latest table row → epoch default when the table is empty or the DB is unreachable; `last_run.txt` is ignored completely) and a degraded mode that reports a visible error when the DB is unreachable; unit tests cover: item batching/flush, new/modified status handling, duplicate-item upsert (no duplicates), summary counts recomputation, baseline resolution order (table row, empty table → epoch, no file involvement), and degraded-mode error visibility (verify with `pytest src/tests -m unit`).

## 2. Crawler integration

- [x] 2.1 Wire the recorder into `src/oparlUpdate.py`: resolve the baseline via the recorder (latest table row → epoch; `--last-date` override wins; `last_run.txt` ignored), create the run at crawl start, record each saved resource as `new`/`modified` where `should_save`/`process_resource` already decides it, count failed fetches, finish the run row on normal exit, KeyboardInterrupt and exception paths (graceful shutdown keeps `success=false` and partial items), and **remove all writes to `last_run.txt`**; unit tests with stubbed HTTP + mocked recorder verify: run row created/finished, statuses match file-level semantics, baseline comes from the table after the first recorded run, no file-based fallback exists, and a DB failure surfaces a visible error while the crawl still completes (`pytest src/tests/test_unit_oparlUpdate.py`).
- [x] 2.2 Add the three tracking tables to `pgGen.ensure_project_schema` (additive, non-destructive); extend the existing integration test `test_re_run_preserves_data` to assert the tables exist after a schema-only run (`pytest src/tests/test_integration_pgGen.py`).

## 3. End-to-end verification

- [x] 3.1 Integration test on `test_*` tables: run `crawl_oparl` with stubbed HTTP against a recorder bound to the real engine using renamed test tables (or a `run_timestamp` fixture unique to the test), then assert via SQL: run row with baseline/totals, item rows with correct statuses, per-type counts (`new_count`/`modified_count`) match the items; verify re-running the same run timestamp does not duplicate rows (`pytest src/tests -m integration`).
- [x] 3.2 Run one real incremental crawl (`python src/oparlUpdate.py` with a short `--last-date`) against `riski_agentic` and verify the run row + item/summary rows are populated and queryable, and that a read-only user can SELECT them; record the query output.
- [x] 3.3 Verify full suite green (`python -m pytest src/tests -q`) and that `last_run.txt` is never modified by a crawl (checksum before/after), and that a DB failure during a crawl surfaces a clear error while the fetches complete (simulate with an invalid `POSTGRES_URL`).

## Workflow follow-up

- Commit after user review; archive via `/opsx-archive` once implemented.
