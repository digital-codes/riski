# Spec Delta

## Purpose

Define the one-command update pipeline that keeps the database current:
phase-based execution (snapshot → sync → enrich → report), pre-run backup
snapshots with verification, automatic snapshot restore on failure, and a
machine- and human-readable run report.

## ADDED Requirements

### Requirement: One-command update

The system SHALL provide a single entry point that, by default, executes the
update pipeline in order: snapshot, sync (incremental crawl + import),
enrichment (OCR, summaries, content, teasers, geo references, tags), and
report. Each phase SHALL reuse the existing pipeline components and their
idempotency guarantees (re-runs never duplicate rows and skip completed work).

#### Scenario: Default run executes all phases in order
- **WHEN** the entry point is invoked without phase arguments
- **THEN** snapshot, sync, enrich and report phases run in that order, each
  starting only after the previous phase exited successfully

#### Scenario: Phase selection
- **WHEN** the entry point is invoked with a phase selection (e.g. only
  `sync`, or `snapshot` + `sync`)
- **THEN** exactly the selected phases run, in pipeline order, and the report
  states which phases were skipped

### Requirement: Pre-run snapshot with verification

Before any phase that writes to the database, the system SHALL create a
custom-format database dump in the configured snapshot directory, named with
the date (and time when needed to avoid collisions), and SHALL verify the
dump is readable (e.g. list its table-of-contents) before continuing. If the
snapshot cannot be created or verified, the run SHALL abort before writing.

#### Scenario: Snapshot precedes all writes
- **WHEN** an update run starts with the snapshot phase
- **THEN** a verified dump exists in the snapshot directory before the sync
  or enrich phases touch the database

#### Scenario: Unusable snapshot aborts the run
- **WHEN** the dump cannot be created or fails verification
- **THEN** the run exits non-zero without modifying the database and the
  report records the snapshot failure

### Requirement: Restore from snapshot on failure

When a phase fails in a way that leaves the database in an unusable or
partially updated state, the system SHALL be able to restore the pre-run
snapshot: the restore target SHALL be created and verified before the current
database is replaced. The decision whether to restore automatically or defer
to the operator SHALL be explicit (opt-in auto-restore flag; without it the
run reports the failure and the restore command).

#### Scenario: Auto-restore on phase failure
- **WHEN** a phase fails while auto-restore is enabled
- **THEN** the pre-run snapshot is restored into a verified target that then
  replaces the current database, and the report documents the rollback

#### Scenario: No auto-restore by default
- **WHEN** a phase fails without the auto-restore flag
- **THEN** the database is left untouched after the failing phase, and the
  report contains the failure details and the exact restore command

### Requirement: Run report

At the end of every run — success or failure — the system SHALL write a
markdown report to the snapshot directory and print its path to stdout. The
report SHALL be re-rendered after every phase so an interrupted run still
leaves a usable report.

#### Scenario: Report survives an interrupted run
- **WHEN** a run is killed during a long phase
- **THEN** a report exists that reflects all phases completed so far

### Requirement: Run report content

The report SHALL contain: phases executed with duration and exit status;
sync phase counts (new/modified per element type, errors, baseline, end
state); enrichment counters (files OCR'd, summaries written, contents
updated, embeddings added, teasers generated, geo links added, tags added);
database row-count deltas for the main tables; and errors with their phase.

#### Scenario: Successful run report
- **WHEN** a run completes all selected phases
- **THEN** the report lists every phase with duration and status and the
  per-step counters and row-count deltas

#### Scenario: Failed run report
- **WHEN** a phase fails
- **THEN** the report names the failing phase, the error, the phases not
  executed, and — unless auto-restore ran — the restore command

### Requirement: Module layout for pipeline, database and search

The codebase SHALL separate pipeline/update modules, database utilities and
search/analysis modules into distinct packages, with the previous top-level
module paths preserved as re-export shims so existing command lines and tests
continue to work.

#### Scenario: Old entry points keep working
- **WHEN** an existing command line (e.g. `python src/pgOcr.py --help`) or
  test import (`from src.pgOcr import run`) is used after the restructure
- **THEN** it behaves identically via the re-export shim
