# Proposal

## Why

Incremental OParl updates exist but are only partially effective: `createdSince` is applied to just one collection, so every run re-validates the entire graph and takes hours; entities *modified* after creation can be missed entirely; and there is no endpoint-capability fallback. The superseded change `incremental-postgres-update` described these gaps but targeted an outdated design (file-based cursor, separate `postgres-fetch` script). This change completes the incremental sync based on the current architecture (`oparlUpdate` + `pgGen` + DB-backed run tracking).

## What Changes

- **`createdSince`/`modifiedSince` for all collections**: `oparlUpdate` applies timestamp filters to every crawled collection (papers, agendaItems, meetings, people, consultations), not just `bodies/0001`, so runs fetch only what actually changed. Because OParl's `createdSince` misses entities modified after creation, the filter uses `modifiedSince` where the endpoint supports it.
- **Endpoint-capability detection with fallback**: when an endpoint ignores or rejects a timestamp filter, the crawler detects this (unchanged result set / HTTP error) and falls back to fetching that collection in full with a warning — matching the behaviour planned as task 3.1 of the superseded change. The capability decision is remembered per collection type for the run.
- **Run-log awareness**: collections fetched via fallback are recorded in the run tracking tables (`oparlUpdateRunTypeCounts` already distinguishes types; fallback full-fetches are visible in the run row via a `full_fetches` marker) so operators can see which collections are still fully scanned.
- **One-command incremental synchronisation** (optional, small): a thin entry point that runs the incremental crawl followed by `pgGen`'s import step against the new JSON files, closing the two-phase gap (crawler → files → manual import).
- **BREAKING — none**: crawl output format and DB schema are unchanged; the tracking tables already exist.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `oparl-import`: the "Incremental update" requirement is extended — timestamp filtering applies to **all** collections (using `modifiedSince` where supported), unsupported endpoints fall back to full fetch with a warning, and fallback usage is visible in the run record; a new "One-command synchronisation" requirement covers the combined crawl+import entry point.

## Impact

- **Code**: `src/oparlUpdate.py` (filters for all collections, fallback detection, recorder marker), `src/pgGen.py` (no change expected — existing upsert import is reused), new small CLI wrapper (e.g. `src/syncIncremental.py`), tests in `src/tests/`.
- **Database**: no schema changes (tracking tables exist); crawl duration drops from hours to minutes for typical incremental runs.
- **Risk**: if `modifiedSince` is not honoured by some endpoints, the fallback full-fetch keeps correctness at the cost of runtime; detection must be conservative (only mark a filter "unsupported" when provably ignored).
- **Supersede**: `openspec/changes/incremental-postgres-update` is deleted — its implemented parts are already documented in the README's "Incremental update — implementation status" section.
