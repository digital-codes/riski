# Design

## Context

`src/` holds 19 legacy scripts; every one builds its own SQLAlchemy engine (via the git-ignored `src/private.py`) and some duplicate hand-rolled LLM HTTP calls. `src2/` is a partial refactor: a shared `db` layer, a shared `remote` layer, 3 migrated modules (`pgTagMgr`, `pgNameVecs`, `pgSummarize` — all with known bugs and none functionally tested), and 3 brand-new scripts (`pgTeasers`, `pass1_entities_tfidf`, `pass2_cluster_words`) that are unrelated to the legacy code. The legacy tests in `test/` only cover 2 modules and use the old constructor signatures. See proposal.md for scope and the explore findings in `src2/migration_report.md`.

Constraints:
- `src/private.py` (git-ignored, verified via `git check-ignore`) now exists and holds the LLM keys/endpoint config (`EMB_*`, `SUMMARY_*`, `OCR_*`, `RERANK_*`, `DB_*`, `RO_*`); migrated modules consume it through the shared `db`/`remote` config resolution, never by direct import.
- Integration tests use read/write DB credentials from `.env` (`RW_USER`/`RW_PWD`, git-ignored); snapshot dir `/mnt_ai/data/riski/snapshots` is world-writable; DB is large — **exactly one snapshot** for the whole development phase.
- Local LLM endpoints (chat `localhost:8080/v1`, embed `localhost:8085/v1`, ollama `localhost:11434`) may or may not be running during tests.

## Goals / Non-Goals

**Goals:**
- Single refactored package: all 19 `src/` modules migrated onto shared `db`/`remote` layers.
- Verified behavior parity between each migrated module and its `src/` original, enforced by tests.
- Full pytest suite: mocked unit tests (always runnable) + DB integration tests (snapshot/restore-guarded).
- Directory swap: `src2/` → `src/`, old `src/` removed from the next commit.

**Non-Goals:**
- No changes to the "new stuff" (`pgTeasers.py`, `pass1_entities_tfidf.py`, `pass2_cluster_words.py`, `migration_report.md`) — untouched.
- No DB schema migrations of production tables; tests only create/drop their own `test_*` tables (snapshot/restore covers any accidents).
- No new external services; no rewrite of OParl crawling logic beyond what parity requires.

## Decisions

**D1 — Directory swap via `git mv`, done last.** Development continues in `src2/`; the swap (`git rm -r src/`, `git mv src2/ src/`) is a single final commit step after the full suite passes. Alternative (swap first, refactor in place) was rejected because it breaks every legacy test and script path at once and mixes mechanical moves with logic changes.

**D2 — Fix migrated modules to restore parity, don't shrink scope.** `pgTagMgr` regains the 5 missing public methods (`find_items_with_all_tags`, `find_items_with_any_tag`, `get_tags_for_item`, `add_tags_to_catalog`, `remove_tags_from_catalog`); `pgNameVecs` keeps the old public API (adapted to the new constructor); `pgSummarize`'s `prompt` scoping bug and duplicate filter line are fixed. Old `test/` suites are ported to the new signatures rather than deleted.

**D3 — `db` layer extensions needed for parity:**
- Read-only engine: `get_engine(readonly=True)` resolved from `RO_USER`/`RO_PWD` (fallback to `DB_*`), separate singleton per role. Used by `pgFileQuery`, `pgTimeline`, `pgVecSearch`.
- Fix the invalid log format strings (`"% (asctime)s"` → `"%(asctime)s"`) in `db` and `remote`.
- Keep `upsert()`/`table_exists()`/`db_connection()` as the canonical helpers; migrated modules use them instead of hand-rolled `ON CONFLICT` SQL where equivalent.

**D4 — `remote` layer fixes and extension:**
- Rewrite `_post`: retry loop actually loops (`REMOTE_MAX_RETRIES`, default 3, short sleep); raise on final failure; no dummy fallback for `embed()`. `chat()` dummy fallback is kept only as a last resort so offline unit tests can pass — integration tests assert real responses.
- Add `ocr(pdf_bytes)` (migrated from `src/pgOcr.py`) with 429-retry, configured by `OCR_*` env vars. Alternative (separate module) rejected: same HTTP/retry concerns.
- Fix duplicated log format string.

**D5 — Migration mapping for the 16 unported modules:**

| src file | Destination | Notes |
|---|---|---|
| `pgGen.py` | `src2/pgGen.py` | engine via `db`; `private.DB_*` → `db` config; `jsonTest.py` dropped (superseded, kept in git history) |
| `oparlUpdate.py` | `src2/oparlUpdate.py` | no DB changes; keep run-state file logic |
| `pgFileQuery.py` | `src2/pgFileQuery.py` | read-only engine |
| `pgTimeline.py` | `src2/pgTimeline.py` | `remote.chat`/`remote.embed` + rerank env vars; read-only engine |
| `pgVecSearch.py` | `src2/pgVecSearch.py` | `remote.embed`; read-only engine |
| `pgAddNameVectors.py` | `src2/pgAddNameVectors.py` | `remote.embed` + `db.upsert` |
| `pgAddSummaries.py` | `src2/pgAddSummaries.py` | `db` config |
| `pgAddVecs.py` | `src2/pgAddVecs.py` | one-shot loader, engine via `db` |
| `pgAddTags.py` | `src2/pgAddTags.py` | read-only engine |
| `pgAddStreets.py`, `pgAddDistricts.py` | `src2/` same names | engine via `db` |
| `pgAddStreetRefs.py`, `pgAddDistrictRefs.py` | `src2/` same names | engine via `db` |
| `local_geo_matching.py` | `src2/local_geo_matching.py` | pure functions, unchanged |
| `pgOcr.py` | folded into `remote` | `perform_ocr` becomes `remote.ocr` |
| `pgTagTest2.py` | dropped | superseded prototype of the TagManager (hardcoded creds); recoverable from git history |
| `private.py` | not migrated | git-ignored credentials module, consumed via `db`/`remote` config resolution |

**D6 — Test layout and strategy.** Tests live in the package (`src2/tests/`, becoming `src/tests/`):
- `conftest.py`: loads `.env` (never committed); fixtures for engine; `mock_embed`/`mock_chat` fixtures monkeypatching `remote`.
- Unit tests (`test_unit_*`): no network, no DB writes beyond throwaway `test_*` tables created by the fixtures themselves; pure logic (geo matching, retry logic, config resolution, tag-vector SQL generation) fully mocked.
- Integration tests (`test_integration_*`): marked `@pytest.mark.integration`, run against live `riski_agentic`; create/drop only `test_*`-prefixed tables; skipped automatically if `.env` credentials are absent.
- Ported legacy suites (`test_pgTagMgr`, `test_pgNameVecs`) adapted to the new API; `src2/tests/test_core.py` kept, extended with OCR config tests.
- Each migrated module gets a parity check: same public API names/signatures as the `src/` original (asserted in a `test_parity.py` via reflection) plus behavior tests.

**D7 — Snapshot/restore protocol (one snapshot).** Before the first integration test run: `pg_dump --format=custom riski_agentic` → `/mnt_ai/data/riski/snapshots/riski_agentic_2026-10-23.dump` (single file, ~one shot for the whole dev phase). After the full test phase (and after any suspected corruption): `pg_restore --clean --if-exists -d riski_agentic <dump>`. Restore is executed manually/at the end of tasks, not per test run. A task in tasks.md explicitly gates the final restore.

## Risks / Trade-offs

- [Integration tests write to a large production DB] → Only `test_*`-prefixed tables are written; suite is snapshot-guarded; restore step is explicit and single.
- [Local LLM endpoints may be down] → Unit tests mock `remote`; integration tests that need live endpoints are skipped with a clear message when endpoints are unreachable.
- [Parity of `pgGen.py` (787 lines, most complex) is hard to verify by test alone] → Parity = preserved public API + schema-only mode tested against a scratch schema + code review diff checklist recorded in the module's migration note.
- [`jsonTest.py` dropped] → Superseded by `pgGen.py`; recoverable from git history.
- [Directory swap breaks external references to `src/`] → Grep repo for `src/` imports before swap (only `test/` and docs expected); app/ uses its own `src/` (vite app) and must not be touched.
- [Snapshot/restore via `pg_restore --clean` on a live DB locks tables] → Restore is only run when no other jobs are active; user is notified before the restore step.

## Migration Plan

1. Fix `db`/`remote` layers (D3, D4) with unit tests.
2. Repair the 3 migrated modules to full parity (D2) and port their legacy tests.
3. Migrate the 16 remaining modules (D5), each with unit tests first, then integration tests.
4. Run the full suite (one snapshot taken before first integration run).
5. Swap directories (`git rm -r src/ && git mv src2/ src/`), fix import paths/docs references, commit.
6. Restore DB from snapshot after final confirmation (explicit, manual step).

Rollback: the swap is a single commit — revert it to restore both directories; DB is restored from the snapshot dump.

## Open Questions

(none — snapshot dir permissions resolved; `.env` credentials present; LLM-endpoint availability handled by test skipping)
