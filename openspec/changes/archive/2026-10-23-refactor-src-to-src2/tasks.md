# Tasks

## 1. Foundations: shared layers

- [x] 1.1 Fix log format strings (`"% (asctime)s"` → `"%(asctime)s"`) in `src2/db/__init__.py` and `src2/remote/__init__.py`; verify with a unit test that logger emission does not raise.
- [x] 1.2 Rewrite `remote._post` retry logic: real retry loop (`REMOTE_MAX_RETRIES`, default 3, short sleep), raise on final failure, no dummy response from `embed()`; keep chat dummy fallback only as last resort. Verify with mocked-HTTP unit tests (transient failure then success; exhausted retries raise).
- [x] 1.3 Add read-only engine support to `src2/db`: `get_engine(readonly=True)` resolving `RO_USER`/`RO_PWD` (fallback `DB_*`) with its own singleton; verify via unit test on URL construction and integration smoke `SELECT 1`.
- [x] 1.4 Wire `src/private.py` (LLM keys `EMB_*`/`OCR_*`/`RERANK_*`/`SUMMARY_*`, `DB_*`/`RO_*`) into `db`/`remote` config resolution (already the fallback chain — verify precedence `POSTGRES_URL` > `private.py` > env > defaults with unit tests) and confirm `git check-ignore src/private.py` still passes.
- [x] 1.5 Extend `remote` with `ocr(pdf_bytes)` migrated from `src/pgOcr.py` (429 retry, `OCR_*` env config); unit tests with mocked HTTP for success and 429-retry paths.

## 2. Repair the 3 already-migrated modules to parity

- [x] 2.1 Fix `src2/pgTagMgr.py`: remove undefined `session` (`NameError`) and restore full original API (`find_items_with_all_tags`, `find_items_with_any_tag`, `get_tags_for_item`, `add_tags_to_catalog`, `remove_tags_from_catalog`); port `test/test_pgTagMgr.py` to `src2/tests/test_pgTagMgr.py` against the new constructor and make it pass (integration, `test_*` tables only).
- [x] 2.2 Fix `src2/pgNameVecs.py`: preserve public API, remove dead `_make_vec_table`/unused imports, route embeddings through `remote.embed`; port `test/test_pgNameVecs.py` to `src2/tests/test_pgNameVecs.py` (mocked embed for unit part, live embed integration part) and make it pass.
- [x] 2.3 Fix `src2/pgSummarize.py`: move `prompt` to module scope (fixes `NameError`), remove duplicated `df.drop(...)` line; add unit test for `request_summary` with mocked `remote.chat` verifying request/response handling.

## 3. Migrate remaining src modules (design.md D5)

- [x] 3.1 Migrate `src/pgGen.py` → `src2/pgGen.py` (engine/config via `db`, drop `jsonTest.py`); unit tests for relationship/column detection and preservation logic with fixture JSON; integration test of schema-only mode against a scratch `test_*` schema; verify `--schema-only` run creates expected project tables and re-run preserves data.
- [x] 3.2 Migrate `src/oparlUpdate.py` → `src2/oparlUpdate.py`; unit tests for URL fixing and run-state bookkeeping with a stubbed HTTP layer; verify a mocked second run fetches only entities modified after run state.
- [x] 3.3 Migrate `src/pgFileQuery.py` → `src2/pgFileQuery.py` on the read-only engine; port query behavior to tests using `test_*` fixture tables; verify `find_unreferenced_files` and related-id queries match `src` output on the same fixture data.
- [x] 3.4 Migrate `src/pgTimeline.py` → `src2/pgTimeline.py` (read-only engine, `remote.chat`/`embed`, rerank env vars); unit tests for timeline window grouping (30-day) and result assembly with mocked model calls; verify JSON output structure matches `src` version on fixture data.
- [x] 3.5 Migrate `src/pgVecSearch.py` → `src2/pgVecSearch.py` (read-only engine, `remote.embed`); unit tests with mocked embed for ranking and score cutoff using fixture vectors.
- [x] 3.6 Migrate `src/pgAddNameVectors.py` → `src2/pgAddNameVectors.py` (`remote.embed` + `db.upsert`); verify with integration test on `test_*` tables that re-runs upsert instead of duplicating rows.
- [x] 3.7 Migrate `src/pgAddSummaries.py` → `src2/pgAddSummaries.py`; integration test mapping fixture markdown files to `test_*` file rows and updating content; unmatched files reported.
- [x] 3.8 Migrate `src/pgAddVecs.py` → `src2/pgAddVecs.py`; verify one-shot rebuild from a small `.npz` fixture on `test_*` tables.
- [x] 3.9 Migrate `src/pgAddTags.py` → `src2/pgAddTags.py` (read-only engine); unit test keyword-grouping logic with fixture names; verify exported JSON structure matches `src` version.
- [x] 3.10 Migrate `src/pgAddStreets.py`, `src/pgAddDistricts.py`, `src/pgAddStreetRefs.py`, `src/pgAddDistrictRefs.py`, `src/local_geo_matching.py` → `src2/` (engine via `db`); unit tests for `local_geo_matching` (boundary-safe matching, longest non-overlapping spans); integration test loads fixture streets/districts into `test_*` tables and builds association links.
- [x] 3.11 Add `src2/tests/test_parity.py`: reflection-based check that every migrated module exposes the same public API names/signatures as its `src/` counterpart (per design D6) and passes.

## 4. Test infrastructure, snapshot and full verification

- [x] 4.1 Finalize `src2/tests/conftest.py`: load `.env` (`RW_USER`/`RW_PWD`), engine fixtures, `mock_embed`/`mock_chat` fixtures, auto-skip marker for integration tests when credentials or live LLM endpoints are absent; verify `pytest -m unit` passes with no network and no live DB writes outside `test_*` tables.
- [x] 4.2 Take exactly ONE snapshot: `pg_dump --format=custom riski_agentic > /mnt_ai/data/riski/snapshots/riski_agentic_2026-10-23.dump` and verify the dump file is non-empty and readable with `pg_restore --list`; do not snapshot again for the rest of development.
- [x] 4.3 Run the full suite `pytest src2/tests -v` against live DB/endpoints; fix failures until green (writes limited to `test_*` tables); record run output.
- [x] 4.4 Verify untouched "new stuff" is unchanged: `git diff --stat src2/pgTeasers.py src2/pass1_entities_tfidf.py src2/pass2_cluster_words.py src2/migration_report.md` is empty.

## 5. Directory swap

- [x] 5.1 Grep repo for references to old paths (`from src `, `src/private`, `import src`) outside `app/` and update to the new package; verify no hits remain.
- [x] 5.2 Swap directories in one commit preparation: `git rm -r --cached src/` + remove working tree `src/` (only after suite green), `git mv src2 src`; verify `git status` shows `src/` deleted, new `src/` package added, and `src/private.py` still ignored (`git check-ignore src/private.py`).
- [x] 5.3 Re-run full test suite from the new `src/` location (`pytest src/tests -v`) and confirm green; confirm `.env`/`private.py`/snapshot dump are not in `git status` (no secrets staged).

## Workflow follow-up

- Restore the database from the snapshot (`pg_restore --clean --if-exists -d riski_agentic /mnt_ai/data/riski/snapshots/riski_agentic_2026-10-23.dump`) after user confirmation, when no other jobs are running.
- Commit the swap (user-approved commit step; no commit without explicit request).
- Archive the change after review.
