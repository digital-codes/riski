# Spec Delta

## Purpose

Define the one-command update pipeline that keeps the database current:
phase-based execution (snapshot → sync → enrich → report) with per-phase
criticality, pre-run backup snapshots with verification, per-File stage
tracking with retry-on-next-run semantics, cron-safe operation, and a
machine- and human-readable run report.

## ADDED Requirements

### Requirement: One-command update with criticality classes

The system SHALL provide a single entry point that, by default, executes the
update pipeline in order: snapshot, sync (incremental crawl + import),
enrichment (OCR, summaries, content, teasers, geo references, tags), and
report. Each phase SHALL reuse the existing pipeline components and their
idempotency guarantees (re-runs never duplicate rows and skip completed
work). Phases SHALL declare a criticality class: `critical` (snapshot, sync)
and `best-effort` (all enrichment phases). A critical phase failure SHALL
stop the run; a best-effort phase failure SHALL be recorded and the
remaining phases SHALL still run.

#### Scenario: Default run executes all phases in order
- **WHEN** the entry point is invoked without phase arguments
- **THEN** snapshot, sync, enrich and report phases run in that order, each
  starting only after the previous phase has finished (successfully, or —
  for a best-effort phase — with recorded failures)

#### Scenario: Phase selection
- **WHEN** the entry point is invoked with a phase selection (e.g. only
  `sync`, or `snapshot` + `sync`)
- **THEN** exactly the selected phases run, in pipeline order, and the report
  states which phases were skipped

#### Scenario: Best-effort phase failure does not block the pipeline
- **WHEN** an enrichment phase fails (partially or entirely), e.g. the OCR
  backend is down
- **THEN** the failure is recorded with its error details, the remaining
  phases still run, and the run exits with the partial-success code

#### Scenario: Critical phase failure stops the run
- **WHEN** the sync phase fails
- **THEN** the run stops, the failure is reported, the tracked baseline
  remains unchanged so the next run re-fetches the same window, and the
  run exits with the critical-failure code

### Requirement: Snapshot as manual recovery point

Before any phase that writes to the database, the system SHALL create a
custom-format database dump in the configured snapshot directory, named with
the date (and time when needed to avoid collisions), and SHALL verify the
dump is readable (e.g. list its table-of-contents) before continuing. If the
snapshot cannot be created or verified, the run SHALL abort before writing.
Restore tooling SHALL be provided for the operator (restore into a verified
fresh target before the live database is replaced), but the pipeline SHALL
NOT automatically restore or replace the live database — recovery from
failure is retry-on-next-run via idempotent phases.

#### Scenario: Snapshot precedes all writes
- **WHEN** an update run starts with the snapshot phase
- **THEN** a verified dump exists in the snapshot directory before the sync
  or enrich phases touch the database

#### Scenario: Unusable snapshot aborts the run
- **WHEN** the dump cannot be created or fails verification
- **THEN** the run exits non-zero without modifying the database and the
  report records the snapshot failure

#### Scenario: Operator-initiated restore
- **WHEN** the operator invokes the restore helper with a snapshot
- **THEN** the snapshot is restored into a fresh, verified database before
  the current one is renamed aside, and the replaced database is kept (not
  dropped)

### Requirement: Run report

At the end of every run — success or failure — the system SHALL write a
markdown report to the snapshot directory and print its path to stdout. The
report SHALL be re-rendered after every phase so an interrupted run still
leaves a usable report.

#### Scenario: Report survives an interrupted run
- **WHEN** a run is killed during a long phase
- **THEN** a report exists that reflects all phases completed so far

### Requirement: Run report content

The report SHALL contain: phases executed with duration, criticality and
status; sync phase counts (new/modified per element type, errors, baseline,
end state); enrichment counters per stage (files OCR'd, summaries written,
contents updated, embeddings added, teasers generated, geo links added, tags
added) split into succeeded/failed/empty; per-stage failure details with
error reasons; items whose stage has failed on `attempts >= 3` consecutive
runs (poison items, listed explicitly); database row-count deltas for the
main tables; and the exit-code semantics.

#### Scenario: Successful run report
- **WHEN** a run completes all selected phases
- **THEN** the report lists every phase with duration and status and the
  per-step counters and row-count deltas

#### Scenario: Failed run report
- **WHEN** a phase fails
- **THEN** the report names the failing phase, its criticality, the error,
  the item-level failures, and the phases not executed

#### Scenario: Repeat offenders are visible
- **WHEN** a stage failure has been recorded on three or more consecutive
  runs for the same item
- **THEN** the report lists the item under a poison-items section with its
  error history so the operator can intervene

### Requirement: Cron-safe operation

The entry point SHALL be safe for unattended scheduled execution: an
exclusive-run lock SHALL prevent overlapping invocations (a second
invocation SHALL exit immediately with a log line, without starting work);
each phase SHALL enforce a configurable timeout so a hung phase cannot block
future runs; and the process SHALL exit with distinct codes (0 = all stages
done, 1 = critical failure, 2 = partial success with recorded stage
failures) so schedulers and mail(1) can act on them.

#### Scenario: Overlapping invocation exits immediately
- **WHEN** the entry point is invoked while another run holds the lock
- **THEN** the second invocation logs the conflict and exits without
  touching the database

#### Scenario: Hung phase is bounded
- **WHEN** a phase exceeds its configured timeout (e.g. a stuck LLM call)
- **THEN** the phase is recorded as failed (timeout), remaining best-effort
  phases still run, and the failed items retry on the next run

#### Scenario: Exit codes distinguish outcomes
- **WHEN** a run finishes
- **THEN** the exit code is 0 when every executed stage is done or empty,
  2 when stage failures were recorded but the run completed, and 1 when a
  critical phase failed

### Requirement: Module layout for pipeline, database and search

The codebase SHALL separate pipeline/update modules, database utilities and
search/analysis modules into distinct packages, with the previous top-level
module paths preserved as re-export shims so existing command lines and tests
continue to work.

#### Scenario: Old entry points keep working
- **WHEN** an existing command line (e.g. `python src/pgOcr.py --help`) or
  test import (`from src.pgOcr import run`) is used after the restructure
- **THEN** it behaves identically via the re-export shim
