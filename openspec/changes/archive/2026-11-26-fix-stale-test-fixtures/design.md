# Design: fix-stale-test-fixtures

## Context

10 suite-wide failures verified as pre-existing/test-drift (baseline identical). Product code is correct on all counts — the tests encode yesterday's data or schema shapes:

1. kg stubs: `related_by_tags` resolves display names with a 5-tuple SELECT (`teaser` since change `unify-file-content-in-chunks`); the `_Eng`/`_Ctx` mock rows still transport 4-tuples → IndexError in the fixture, not the code.
2. location candidates: tests freeze absolute corpus sizes for specific locations ("no truncation note below cap") against the LIVE DB — the import keeps adding files, so assertions rot by design.
3. loader/content-chunking: expectations encode pipeline states superseded by the unified `File_chunks` store.

## Goals / Non-Goals

- Goal: every failing test either passes with a CURRENT schema/data contract or is reframed to assert time-stable properties (relations, not sizes).
- Non-Goal: changing product code, imperative test-framework additions (the frontend still has none), extra seeds/snapshots beyond what exists.

## Decisions

1. **Stub shape = code shape**: kg stub rows get the 5 elements; the year/teaser assertions extend accordingly (also assert `downloadurl` path form).
2. **Corpus-relative assertions**: location tests assert —
   - truncation note present when the returned cap equals `TOP_K_LOCATION_MAX`
   - absence of truncation when `total_files <= cap`
   computed from the queries themselves (total_files is in the payload) instead of frozen location-specific file counts.
3. **Loader re-baseline**: assert current provenance fields with the smallest live corpus query; skip-with-reason if the seeded docs are absent (data drift is a deployment issue, not a test failure).
4. Policy note in the test file docstrings (next session's author reads why tests must code counts relatively).

## Risks / Trade-offs

- [Greening tests could mask real raggedness] → assertions stay strict on everything except the deliberately count-relative cases; the drift cause remains visible in the payload.

## Migration Plan

Test-only edits + one run of the full suite; no deployment impact.

## Open Questions

None.
