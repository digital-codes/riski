# Design

## Context

`src/oparlUpdate.py` implements the incremental crawl with DB-backed run tracking (archived change `track-oparl-update-runs`). Its key limitation: the `createdSince` filter is only appended to the `bodies/0001` collection; the other five collections are always fetched in full, so each run re-validates the whole graph (~1,800+ resources, hours of runtime). `pgGen.insert_all` already upserts idempotently on `oparlId` (newer-`modified` wins), so imports are safe to re-run. The superseded change `incremental-postgres-update` identified the same gaps against an outdated design; its README documentation (`Incremental update — implementation status`) lists what exists and what is missing.

## Goals / Non-Goals

**Goals:**
- Timestamp-filtered fetching for **all** collections, using `modifiedSince` where supported so modified-after-creation entities are captured.
- Conservative fallback: full fetch per collection when a filter is provably ignored/rejected, with the fallback visible in the run record.
- A single entry point for crawl + import with a consistent tracking guarantee (baseline only advances after a successful import).
- Typical incremental runs complete in minutes, not hours.

**Non-Goals:**
- No change to the JSON output format, DB schema, or `pgGen`'s import semantics.
- No parallel/concurrent crawling (sequential with politeness delays stays).
- No back-fill of historical data.
- No scheduler/cron setup — the entry point is a CLI, not a daemon.

## Decisions

**D1 — Filter strategy per collection.** Each collection is tried with `modified_since=<baseline>` first (OParl 1.1 spec spelling — the camelCase `modifiedSince` variant is **silently ignored** by Karlsruhe, verified live 2026-10-24). Capability detection is per-page: every fetched collection page is validated against the baseline (an honouring filter can never return items older than it; listings are sorted newest-first, so a violating page appears as soon as the walk reaches older items). A violating page falls back to `created_since`, and if that also violates, to a full fetch (recorded via `record_full_fetch`). A future-baseline probe was rejected after implementation: Karlsruhe answers future-dated filter values with HTTP 401 (non-deterministically an empty 200 earlier the same day), making the probe unreliable.

*Alternative considered:* always full-fetch and filter client-side (current behaviour). Rejected as the default because it is exactly the hours-long runtime this change removes; it remains the fallback.

**D2 — Fallback visibility.** The recorder gains a `record_full_fetch(element_type)` call; the run row stores a `full_fetches` text field (comma-separated collection types, NULL when all were filtered). This is a single nullable column on the existing `oparlUpdateRuns` table — additive, no new table.

**D3 — One-command sync.** New `src/syncIncremental.py`: runs `crawl_oparl(...)` with the recorder, then invokes `pgGen.main(directory)` against the crawler's output folder. Ordering guarantee for the baseline: the crawl phase does **not** finalise the run row itself; the sync entry point finishes it with `success=True` only after the import phase exits 0. On import failure the run row is finished with `success=false` and `end_state` set to the *pre-crawl baseline* (so the next run re-fetches the same window). Standalone `oparlUpdate` keeps its current behaviour (records its own successful run).

**D4 — Baseline comparison at import time (defence in depth).** `pgGen.insert_all` already ignores upserts whose incoming `modified` is not newer than the stored one — no change needed; modified-after-creation entities that slip through a `createdSince`-only filter are still not *created* in the DB, so D1's `modifiedSince`-first strategy is the primary fix, not the import filter.

**D5 — Crawl scope configuration.** The collection list stays in `crawl_oparl` but moves into a module-level constant (`COLLECTIONS = ["consultations", "papers", "agendaItems", "meetings", "people"]`) so the filter/fallback logic is table-driven and testable without HTTP.

## Risks / Trade-offs

- [Karlsruhe API may ignore `modifiedSince` silently (no error, unfiltered result)] → Detection via result-set probe: compare the first page's item count against a known unfiltered count captured on the previous full fetch; when in doubt, fall back to full fetch (correctness over speed).
- [Filter validation itself costs a request per collection] → Negligible: one extra first-page request per collection per run, versus thousands of full-resource fetches today.
- [Import phase can take long on first sync after a big baseline jump] → The sync entry point reports phase progress; crawl and import remain individually re-runnable.
- [`full_fetches` column on `oparlUpdateRuns`] → Additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `ensure_tables`; NULL means "all filtered".

## Migration Plan

1. Implement filter/fallback logic + recorder marker (unit tests with stubbed HTTP).
2. Implement `syncIncremental.py` with the two-phase baseline guarantee (unit tests with mocked phases).
3. Integration test with rollback-only writes (recorder + fallback marker).
4. Real verification: one incremental run against the live API with the tracked baseline (2026-02-19) — expected minutes, not hours; **only after user confirmation**, since it performs real fetches.
5. Delete the superseded `openspec/changes/incremental-postgres-update` change.

Rollback: revert the commit — the crawler's previous full-fetch behaviour is the built-in fallback; DB schema addition (`full_fetches` column) is harmless if left in place.

## Open Questions

- Does the Karlsruhe OParl API actually honour `modifiedSince` (and on which collections)? To be answered by the first real run (task 4.x) — the fallback ensures correctness either way.
