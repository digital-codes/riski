# Proposal: fix-stale-test-fixtures

## Why

The full test suite shows 10 failures of which NONE trace to product code — verified against the git baseline (identical failing set before the current search changes). Three groups drift, each for a known reason: (a) kg stubs carry the OLD 4-tuple `File` row shape while the code correctly reads the CURRENT 5-tuple (teaser included, change `unify-file-content-in-chunks`); (b) the `integration_location` association-candidate tests assert absolute corpus sizes against the LIVE database, and Karlsruhe's imports keep growing the corpus (truncation thresholds now trip on locations the test assumed to be small); (c) loader/content-chunking integration tests are baselined against a pipeline state that has since moved (pure test debt from earlier changes).

A suite full of known-failing tests has degraded into a binary beacon: real regressions cannot be told apart by red/green (the current search work would have been much harder to validate otherwise).

## What Changes

- Update the kg `related_by_tags` stub fixtures (`_Eng`/`_Ctx` rows) to the current 5-tuple File shape (oparlKey, name, filename, date, teaser), asserting teaser/name/year resolution properly.
- Make `integration_location::TestAssociationCandidates` corpus-size robust: select a verification location whose footprint is deterministic (e.g. assert membership of a known seeded file and truncation behaviour relative to a configurable small cap), or run against a dedicated seeded subset instead of the live corpus absolute counts.
- Re-baseline the loader/content-chunking integration tests against the current unified-content pipeline (`File_chunks` single text store): assert today's provenance contract (contentKind provenance / chunk-0 small docs / per-chunk loading), removing references to the retired dual-store behaviour.
- NO product-code changes; test files only (`src/tests/*`).
- Document the drift policy: tests that assert LIVE corpus sizes must be made count-relative or seeded — never absolute.

## Capabilities

- **New Capabilities**: none (test-quality change; spec-free)
- **Modified Capabilities**: none

## Impact

- Files: `src/tests/test_unit_kg_queries.py`, `src/tests/test_integration_location.py`, `src/tests/test_integration_pgAddLoaders.py`, `src/tests/test_integration_contentChunks.py`.
- No runtime code touched → no behaviour risk; suite returns to a green baseline (except the genuinely broken `test_unit_oparlUpdate::first_run`, which belongs to the audit-log flake tracked separately).
