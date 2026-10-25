# Tasks

## 1. Snapshot/restore helpers (`src/db/db_snapshot.py`)

- [ ] 1.1 Implement `create_snapshot(db_name, target_dir) -> Path`: `pg_dump -Fc` with date/time name, verify via `pg_restore --list` (table-of-contents must contain data tables); raise a typed error on failure; unit tests with a fake subprocess runner (verify `pytest src/tests -m unit`).
- [ ] 1.2 Implement `restore_snapshot(dump_path, db_name) -> str`: restore into a fresh `<db>_restore_<ts>` database, verify it, swap via rename (terminate connections first), keep the replaced database as `<db>_pre_restore_<ts>`; return the kept database name; operator-invoked only (no auto-restore in the pipeline); unit tests with fake subprocess runner.
- [ ] 1.3 Integration test against a scratch database: create a table with a row, snapshot, mutate, restore, verify the row is back (skip when no superuser/test DB available) (`pytest src/tests -m integration`).

## 2. Stage ledger (`enrichment-stage-tracking`)

- [ ] 2.1 Ledger table + accessors: `file_stage_status` (file key, stage, status done/failed/empty, reason, attempts, updated_at; PK (file, stage), created on demand); API: `record(file, stage, status, reason)`, `pending(stage)` (absent-or-failed rows), `summary(stage) -> {done, failed, empty}` counts; unit tests (`pytest src/tests -m unit`).
- [ ] 2.2 Reconciliation: `reconcile(stage, check_fn)` — rows marked `failed` whose artifact/data already satisfies the stage are marked `done` (reason "reconciled") without reprocessing; unit tests.
- [ ] 2.3 Poison-item query: items with `status='failed'` and `attempts >= N` (default 3) grouped by stage for the report; unit tests.

## 3. Orchestrator (`src/riskiUpdate.py`)

- [ ] 3.1 `PhaseResult`/`RunContext` dataclasses (name, criticality, status, duration, counters, errors) and the phase registry in design order (snapshot[critical], sync[critical], ocr, summaries, content, teasers, geo, tags); `--phases`/`--skip` CLI flags; unit tests with mocked phase adapters cover: default order, selection, skip reporting (verify `pytest src/tests -m unit`).
- [ ] 3.2 Phase adapters reusing existing entry points, recording per-item outcomes into the stage ledger: sync → `syncIncremental.sync()`; ocr → `pgOcr.run()` (failed PDFs → ledger `failed`); summaries → `pgSummarize._run_summarizer()`; content → `pgAddSummaries.main(argv)` (SystemExit-safe); teasers → `pgTeasers.main()` with explicit argv (SystemExit-safe); geo → `pgAddFileGeoRefs.run()` + `pgAddStreetRefs.main()` + `pgAddDistrictRefs.main()`; tags → `pgCategorise.main()`; unit tests assert each adapter passes the right arguments, captures failures and records ledger outcomes (`pytest src/tests -m unit`).
- [ ] 3.3 Failure semantics per criticality: on critical phase failure stop (report + exact restore command, no auto-restore); on best-effort phase failure record and continue with remaining phases; run reconciliation before each stage; unit tests cover both paths with failing phases (`pytest src/tests -m unit`).
- [ ] 3.4 Exit codes: 0 = all executed stages done/empty, 2 = partial (recorded stage failures), 1 = critical failure; unit tests (`pytest src/tests -m unit`).
- [ ] 3.5 Cron safety: `flock` exclusive-run lock (second invocation exits 0 with log line), per-phase timeout (configurable, phase recorded as failed on expiry, best-effort phases continue); unit tests with mocked long-running phase (`pytest src/tests -m unit`).
- [ ] 3.6 Report: markdown rendering of the `RunContext` (phases with duration/criticality/status, sync counters from the run row, per-stage done/failed/empty counts, poison items with attempts, row-count deltas for the main tables computed before/after sync, errors) written to the snapshot directory and re-rendered after every phase; path printed to stdout; unit tests assert report contents for a success, a partial, and a critical-failure run (`pytest src/tests -m unit`).
- [ ] 3.7 Integration test (ledger + report DB writes) for report data collection: run row counters, stage transitions and row-count deltas are reflected in the rendered report (`pytest src/tests -m integration`).

## 4. Module restructure

- [ ] 4.1 Create `src/update/` and `src/search/` packages; move pipeline modules (`oparlUpdate`, `oparlRunLog`, `syncIncremental`, `pgOcr`, `pgSummarize`, `pgAddSummaries`, `pgTeasers`, `pgAddFileGeoRefs`, `pgAddStreetRefs`, `pgAddDistrictRefs`, `pgCategorise`, `pgTagMgr`, `pgCoverage`, `pgAddDistricts`, `pgAddStreets`, `pgAddNameVectors`, `pgBackfillNameVecs`, `pgAddVecs`, `pgNameVecs`) into `src/update/` and search modules (`pgVecSearch`, `pgHybridSearch`, `pgTimeline`, `pgFileQuery`, `graphModel`, `pgResultSummarizer`, `apiServer`, `local_geo_matching`) into `src/search/`; move their tests alongside; full suite green (`python -m pytest src/tests -q`).
- [ ] 4.2 Re-export shims at the old `src/pg*.py` / `src/oparl*.py` paths (explicit public names) so `python src/pgOcr.py`, `python -m src.apiServer` and old imports keep working; add a unit test importing every shimmed name (`pytest src/tests -m unit`).
- [ ] 4.3 Update internal cross-imports to the new package paths (grep for `from src.pg`, `from src.oparl`, `src.pgGen` etc.) and rerun the full suite incl. integration tests (`python -m pytest src/tests -q`).

## 5. Documentation

- [ ] 5.1 README "Data update workflow" rewritten around `python src/riskiUpdate.py` (flags, criticality/failure semantics, stage ledger, report location) plus a cron example with `flock`, exit-code handling and report path; the manual per-script flow stays as an appendix describing the underlying phases.
- [ ] 5.2 `openspec validate --changes` passes; archive-ready summary in the change folder.
