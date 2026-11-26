# testing Specification

## Purpose

Suite-quality policy: the test suite stays maintainable over live-data
drift — red runs are attributable (product regression or tracked defect),
corpus-dependent assertions are payload-relative (change:
fix-stale-test-fixtures).

## Requirements

### Requirement: Test suite green baseline and drift policy

The test suite SHALL maintain a GREEN baseline in CI-relevant runs: every
red test MUST be attributable to a product regression or an actively
tracked defect — NOT to stale fixtures (outdated schema/data shapes) or
frozen live-corpus sizes. Tests that assert corpus-dependent values
SHALL formulate assertions relative to payload-derived values (e.g.
`total_files` from the response) or use seeded data; a test MAY be
skipped with a named reason when its seeded data is absent. The config
flag: none — this is a suite-policy behaviour.

#### Scenario: Data drift does not fail the suite

- **WHEN** the live corpus grows in a way that would trip a frozen
  absolute-count assertion
- **THEN** the test remains green (assertions are payload-relative) and
  the drift is visible in the test payload, not as a red run

#### Scenario: Every red test is attributable

- **WHEN** a suite-wide run reports failures
- **THEN** each failure names a product regression or a tracked defect —
  stale-fixture failures are treated as suite defects and fixed with the
  same priority as product regressions
