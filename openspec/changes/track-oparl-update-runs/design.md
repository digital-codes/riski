# Design

## Context

`src/oparlUpdate.py` performs incremental OParl crawls and persists only a `last_run.txt` timestamp; `should_save()` already knows for each fetched resource whether the output file is new (missing) or being replaced (incoming `modified` newer than stored). The DB layer (`src/db`) provides the shared engine and the additive `ensure_project_schema` pattern from `pgGen.py`. See proposal.md for motivation; the spec delta defines the behaviour.

## Goals / Non-Goals

**Goals:**
- Durable, queryable record of every OParl crawl run: when, with what baseline, success state, and what changed (per element and per type).
- Item-level log (`oparlUpdateRuns` / `oparlUpdateRunItems`) plus per-run/per-type counts.
- Zero-risk integration: logging must never break or slow down the crawl meaningfully.

**Non-Goals:**
- No changes to the crawl logic itself (URLs, pagination, PDF handling).
- No changes to `pgGen`'s import (tracking reflects *fetches*, not DB imports).
- No UI/API on top of the tables (query via SQL for now).
- No back-fill of past runs (only `last_run.txt` exists historically; nothing to reconstruct).

## Decisions

**D1 — Two tables + summary counts.** 
`oparlUpdateRuns`: `id` (identity PK), `run_timestamp` (run start, unique key for idempotence), `baseline` (the `createdSince` value used), `finished_at`, `success` (bool), `total_new`, `total_modified`, `errors` (int, failed fetches). 
`oparlUpdateRunItems`: `id`, `run_id` FK → runs (CASCADE delete), `element_type` (OParl class name from `type` URL, e.g. `Meeting`), `oparl_id`, `oparl_key`, `status` (`new` | `modified`), `recorded_at`; unique on (`run_id`, `oparl_id`) for idempotence. 
`oparlUpdateRunTypeCounts`: `run_id` FK, `element_type`, `new_count`, `modified_count`, unique on (`run_id`, `element_type`) — directly satisfies "number of new and modified elements together with the type" without aggregation.
Alternative (single table with JSON counts) rejected: not queryable/indexable per type.

**D2 — New module `src/oparlRunLog.py`.** Owns the table definitions (additive create-if-missing, mirroring `ensure_project_schema` style), the `RunRecorder` class with `start(baseline)`, `record_item(...)`, `finish(...)`, and a degraded mode when the DB is unreachable: fetches continue, but the missing run record is reported as a visible error (the baseline cannot advance without the table). `oparlUpdate.py` instantiates it — the crawl code only calls the recorder; all SQL lives in the new module. It also owns baseline resolution (D6).

**D3 — "New vs. modified" semantics = file-level, same as `should_save`.** A resource whose output file did not exist is `new`; a resource replacing an older stored copy is `modified`. This is decided in `crawl_oparl`/`process_resource` where `should_save` already computes it — the comparison result is passed to the recorder instead of being recomputed. Collection wrappers (lists) are logged only when actually saved; their nested entities become their own item rows when fetched individually.

**D4 — Engine role.** The recorder uses the shared **read/write** engine (`db.get_engine()`): the crawl is an offline batch job, and the RW credentials come from `private.py`/env as everywhere else. Read-only role gets SELECT on the new tables via the existing `ALTER DEFAULT PRIVILEGES` convention (best-effort `GRANT SELECT` after table creation).

**D5 — Idempotence & partial runs.** Run identity is `run_timestamp` (ISO start time). If a run is re-executed with the same timestamp (e.g. after a crash replay), item rows are upserted on (`run_id`, `oparl_id`) and counts recomputed, so no duplicates. An interrupted crawl (`KeyboardInterrupt`) still finishes its run row with `success=false` and whatever items were recorded — matching the existing graceful-shutdown behaviour.

**D6 — Run state lives exclusively in the DB; `last_run.txt` is ignored completely.** Baseline resolution: (1) explicit `--last-date` CLI override, (2) latest row in `oparlUpdateRuns` (its `end_state`, falling back to its `baseline`), (3) epoch default when the table is empty or the DB is unreachable — i.e. fetch everything. No file-based fallback exists. The table is seeded once with a baseline of **19 Feb 2026, CET** (`2026-02-19T00:00:00+01:00`), inserted as a marker run row (`success=true`, zero totals) as part of this change; an empty table deliberately means "fetch everything".

**D7 — Verification writes with rollback only.** Integration tests bind the recorder to a connection whose transaction is rolled back at test end (Postgres DDL/DML is transactional), instead of delete-cleanup. No real crawl sessions are run as part of testing; real-API checks are limited to single requests through `process_resource`/`RunRecorder` inside rolled-back transactions.

## Risks / Trade-offs

- [Crawl hot loop gets a DB insert per changed resource] → Items are batched in memory and flushed every `progress_every` resources (same pattern as `pgAddStreetRefs`); typical crawls change few resources per run.
- [RW credentials may be absent on machines that only crawl] → Without a writable DB the run record cannot be stored and the baseline cannot advance; the error is logged clearly and the next run re-resolves from the table. DB connectivity is required for reliable incremental baselines.
- [Tracking tables only exist after the first tracked run] → Additive create-if-missing at recorder start; also added to `pgGen.ensure_project_schema` so schema-only migrations create them.
- [`oparlKey` may be absent on list payloads] → Item rows store it as NULL; `oparl_id` (unique per element) is the real key.

## Migration Plan

1. Implement `src/oparlRunLog.py` + unit tests (mocked engine).
2. Wire the recorder into `oparlUpdate.crawl_oparl` / `process_resource` / `main`.
3. Add table creation to `pgGen.ensure_project_schema` + integration test.
4. Grant SELECT to the read-only role (best-effort, matches existing convention).
5. Run one real incremental crawl to validate end-to-end (writes rows for the run).

Rollback: drop the three tables; the crawler ignores a missing recorder silently. No existing behaviour depends on the tables.

## Open Questions

(none)
