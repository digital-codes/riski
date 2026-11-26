# Tasks: fix-stale-test-fixtures

## 1. kg stub fixtures (5-tuple File shape)

- [x] 1.1 `test_unit_kg_queries.py`: `_Eng`/`_Ctx` rows → 5-tuple (oparlKey, name, filename, date, teaser); extend assertions to teaser/year/path forms
- [x] 1.2 Keep prod code untouched; run file green

## 2. Location association-candidates robustness

- [x] 2.1 Tests assert cap-relative behaviour: truncation note ⇔ `total_files > cap` from the payload (no frozen location file counts); document the policy in the file docstring
- [x] 2.2 File green

## 3. Loader / content-chunk re-baseline

- [x] 3.1 `test_integration_pgAddLoaders.py`: provenance assertions per the unified `File_chunks` store (contentKind provenance, chunk-0 small docs); skip-with-reason on missing seeds
- [x] 3.2 `test_integration_contentChunks.py`: oversized-document chunking path against the CURRENT loader contract (no LLM), legacy dual-store references removed
- [x] 3.3 File green

## 4. Suite verification

- [x] 4.1 Full suite: only the known `oparlUpdate::first_run` audit-flake remains red (tracked by the audit-log change) — everything else green
- [x] 4.2 Doc note: suite-status section in README (green baseline + the deliberate drift policy)

## Workflow follow-up

- archive via `/opsx-archive` after apply.
