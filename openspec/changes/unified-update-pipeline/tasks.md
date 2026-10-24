# Tasks

## 1. Snapshot/restore helpers (`src/db/db_snapshot.py`)

- [ ] 1.1 Implement `create_snapshot(db_name, target_dir) -> Path`: `pg_dump -Fc` with date/time name, verify via `pg_restore --list` (table-of-contents must contain data tables); raise a typed error on failure; unit tests with a fake subprocess runner (verify `pytest src/tests -m unit`).
- [ ] 1.2 Implement `restore_snapshot(dump_path, db_name) -> str`: restore into a fresh `<db>_restore_<ts>` database, verify it, swap via rename (terminate connections first), keep the replaced database as `<db>_pre_restore_<ts>`; return the kept database name; unit tests with fake subprocess runner.
- [ ] 1.3 Integration test against a scratch database: create a table with a row, snapshot, mutate, restore, verify the row is back (skip when no superuser/test DB available) (`pytest src/tests -m integration`).

## 2. Orchestrator (`src/riskiUpdate.py`)

- [ ] 2.1 `PhaseResult`/`RunContext` dataclasses (name, status, duration, counters, errors) and the phase registry in design order (snapshot, sync, ocr, summaries, content, teasers, geo, tags); `--phases`/`--skip`/`--auto-restore`/`--last-date` CLI flags; unit tests with mocked phase adapters cover: default order, selection, skip reporting (verify `pytest src/tests -m unit`).
- [ ] 2.2 Phase adapters reusing existing entry points: sync → `syncIncremental.sync()`; ocr → `pgOcr.run()`; summaries → `pgSummarize._run_summarizer()`; content → `pgAddSummaries.main(argv)` (SystemExit-safe); teasers → `pgTeasers.main()` with explicit argv (SystemExit-safe); geo → `pgAddFileGeoRefs.run()` + `pgAddStreetRefs.main()` + `pgAddDistrictRefs.main()`; tags → `pgCategorise.main()`; unit tests assert each adapter passes the right arguments and captures failures (`pytest src/tests -m unit`).
- [ ] 2.3 Failure semantics: on phase failure stop; without `--auto-restore` report the failure + exact restore command; with `--auto-restore` call `restore_snapshot` and document the rollback in the report; unit tests cover both paths with a failing phase (`pytest src/tests -m unit`).
- [ ] 2.4 Report: markdown rendering of the `RunContext` (phases with duration/status, sync counters from the run row, enrichment counters, row-count deltas for the main tables computed before/after sync, errors) written to the snapshot directory and re-rendered after every phase; path printed to stdout; unit tests assert report contents for a success and a failure run (`pytest src/tests -m unit`).
- [ ] 2.5 Integration test (rollback-only DB writes) for report data collection: run row counters and row-count deltas are reflected in the rendered report (`pytest src/tests -m integration`).

## 3. Module restructure

- [ ] 3.1 Create `src/update/` and `src/search/` packages; move pipeline modules (`oparlUpdate`, `oparlRunLog`, `syncIncremental`, `pgOcr`, `pgSummarize`, `pgAddSummaries`, `pgTeasers`, `pgAddFileGeoRefs`, `pgAddStreetRefs`, `pgAddDistrictRefs`, `pgCategorise`, `pgTagMgr`, `pgCoverage`, `pgAddDistricts`, `pgAddStreets`, `pgAddNameVectors`, `pgBackfillNameVecs`, `pgAddVecs`, `pgNameVecs`) into `src/update/` and search modules (`pgVecSearch`, `pgHybridSearch`, `pgTimeline`, `pgFileQuery`, `graphModel`, `pgResultSummarizer`, `apiServer`, `local_geo_matching`) into `src/search/`; move their tests alongside; full suite green (`python -m pytest src/tests -q`).
- [ ] 3.2 Re-export shims at the old `src/pg*.py` / `src/oparl*.py` paths (explicit public names) so `python src/pgOcr.py`, `python -m src.apiServer` and old imports keep working; add a unit test importing every shimmed name (`pytest src/tests -m unit`).
- [ ] 3.3 Update internal cross-imports to the new package paths (grep for `from src.pg`, `from src.oparl`, `src.pgGen` etc.) and rerun the full suite incl. integration tests (`python -m pytest src/tests -q`).

## 4. Documentation

- [ ] 4.1 README "Data update workflow" rewritten around `python src/riskiUpdate.py` (flags, snapshot/restore semantics, report location); the manual per-script flow stays as an appendix describing the underlying phases.
- [ ] 4.2 `openspec validate --changes` passes; archive-ready summary in the change folder.
