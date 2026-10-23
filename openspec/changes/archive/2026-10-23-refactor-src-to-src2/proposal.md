# Proposal

## Why

The project has two parallel Python source trees: `src/` (19 legacy scripts, each with its own copy of DB-connection boilerplate, credentials handling, and LLM API calls) and `src2/` (a partial refactor that introduces a shared database layer `src2/db` and a shared remote-LLM layer `src2/remote`, but so far only migrates 3 of the 19 files and is untested — several migrated modules contain real bugs). Maintaining two trees and per-script boilerplate is error-prone; the goal is a single, tested `src/` package built on the shared layers.

## What Changes

- **Complete the migration**: port the remaining `src/` modules into the refactored package (shared `db`/`remote` layers), fixing known bugs along the way (undefined `session` in `pgTagMgr`, broken retry logic in `remote._post`, `NameError` in `pgSummarize`, invalid log format strings, dead code in `pgNameVecs`). Two superseded files are dropped (`jsonTest.py`, superseded by `pgGen.py`; `pgTagTest2.py`, a superseded TagManager prototype — both recoverable from git history); `pgOcr.py` is folded into the shared remote client; `private.py` remains the git-ignored credentials source.
- **Behavior parity verification**: for every migrated module, verify its behavior matches the original `src/` implementation before the swap (parity checklist per module, validated by tests).
- **Test suite**: write pytest coverage for all migrated functionality — unit tests (mocked, always runnable) plus DB integration tests that run against the real `riski_agentic` Postgres using read/write credentials from `.env` (git-ignored), guarded by a one-time database snapshot taken before the test run and restored afterwards. Newer, unrelated code in `src2/` (`pgTeasers.py`, `pass1_entities_tfidf.py`, `pass2_cluster_words.py`, `migration_report.md`) is left untouched.
- **BREAKING — directory swap**: after parity is verified, `src2/` becomes the new `src/` and the old `src/` directory is removed from the repository (recoverable from git history). Import paths change from `src.*`-style script usage to the new package layout.
- **Credentials hygiene**: read/write DB credentials come from `.env` (`RW_USER`/`RW_PWD`), never committed; the shared DB layer keeps its existing `private.py` → environment-variable fallback chain.

## Capabilities

### New Capabilities

- `database-access-layer`: shared database access via `db` package — config resolution (`private.py` → env vars → safe defaults), process-wide engine singleton, `table_exists`, generic `upsert`, connection context manager, structured logging, and read-only role support for query-only modules.
- `remote-llm-client`: shared remote model access via `remote` package — `chat()` and `embed()` against OpenAI-compatible endpoints with env-driven configuration, correct retry semantics, error propagation, and OCR client support (migrated from `src/pgOcr.py`).
- `oparl-import`: OParl data acquisition — full schema generation/import (`pgGen`, superseding `jsonTest`) and incremental OParL crawling/updates (`oparlUpdate`).
- `data-enrichment`: enrichment of the imported OParl data — TagManager (tags + associations, full original API), NameVecs (pgvector name embeddings), content/summary loaders (`pgAddSummaries`, `pgAddNameVectors`, `pgAddVecs`), street/district loading and geo reference matching (`pgAddStreets`, `pgAddDistricts`, `pgAddStreetRefs`, `pgAddDistrictRefs`, `local_geo_matching`), and tag analytics export (`pgAddTags`).
- `semantic-search`: read/query paths — unreferenced-file and relation queries (`pgFileQuery`), vector search (`pgVecSearch`), and the interactive semantic search/timeline CLI (`pgTimeline`), all using read-only DB access.

### Modified Capabilities

(none — no specs exist yet; this change establishes the initial capability specs for the refactored package)

## Impact

- **Code**: all 19 files in `src/` are migrated into the refactored package; `src2/` becomes `src/` (directory swap; `git rm src/` + rename in the next commit). Legacy tests in `test/` target the old constructor signatures and are replaced by the new suite.
- **Imports/config**: modules now resolve credentials via `db` (`private.py` → `DB_*` env vars → defaults) and model endpoints via `remote` (`CHAT_*`, `EMBED_*`, `OCR_*` env vars); `private.py` remains supported but optional.
- **Database**: no schema changes; tests may create/drop temporary `test_*` tables and must restore the DB from the pre-test snapshot (`/mnt_ai/data/riski/snapshots`, single snapshot for the whole development phase). Note: the snapshot directory is currently owned by user `kugel` and not writable by the dev user — permissions must be adjusted before the snapshot step.
- **Dependencies**: no new runtime dependencies beyond what `src`/`src2` already use (SQLAlchemy, psycopg2, requests, pytest, pandas/nltk/rapidfuzz already present).
- **Security**: `.env` and snapshot artifacts stay out of git history (already git-ignored; verified).
