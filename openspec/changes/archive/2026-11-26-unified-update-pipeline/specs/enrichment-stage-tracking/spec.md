# Spec Delta

## Purpose

Track the enrichment of every File item per stage (OCR, summary,
content+embeddings, teaser, geo references, tags) so that each stage is
individually satisfied, retried on failure, or terminally marked empty with a
recorded reason. The ledger turns "failed items are repeated in the next
run" from an implicit side effect of idempotency into an explicit, queryable
state machine — and lets a File's enrichment be audited: every document has
reached every stage, or has a documented reason why a stage does not apply.

## ADDED Requirements

### Requirement: Per-File stage ledger

The system SHALL maintain a ledger keyed by (file, stage) that records for
each enrichment stage of each File item a status of `done`, `failed`, or
`empty`, together with a reason, an attempt counter, and the time of the
last update. The ledger table SHALL be created on demand and SHALL NOT
modify any existing pipeline tables.

#### Scenario: Stage outcomes are recorded
- **WHEN** a stage processes a file and succeeds, fails, or produces an
  intentionally empty result
- **THEN** the ledger row for (file, stage) reflects the status, the reason
  (error message or emptiness justification), and an incremented attempt
  count

#### Scenario: Every File is auditable
- **WHEN** the ledger is queried for a File
- **THEN** every defined stage has exactly one row, and a File whose stages
  are all `done` or `empty` is reportable as fully enriched

### Requirement: Retry of failed stages on subsequent runs

A stage with status `failed` SHALL be reprocessed on the next run of that
stage. Failure SHALL never be persisted as completion: no stage may mark an
item `done` (or write a terminal artifact) without the stage's actual success
condition being met. Repeated failures SHALL increment the attempt counter
and keep the status `failed` until the stage succeeds or the item is
explicitly reclassified as `empty` with a reason.

#### Scenario: Failed OCR is retried next run
- **WHEN** OCR fails for a document in run N
- **THEN** no markdown artifact is left that counts as completed, the ledger
  row is `failed`, and run N+1 re-attempts the OCR of that document

#### Scenario: Downstream stages still process available material
- **WHEN** OCR fails for a document but other documents succeeded
- **THEN** the summary, teaser, embedding, geo and tag stages run over the
  successfully OCR'd material in the same run

#### Scenario: Recovery after a backend outage
- **WHEN** the failing backend recovers and the next run executes
- **THEN** previously failed stages succeed and their items advance to
  `done` without any manual intervention

### Requirement: Terminal empty state with reason

A stage MAY mark an item `empty` when the stage genuinely does not apply,
with a machine-readable reason (e.g. document has no extractable text; no
street or district mentioned; document too short for a teaser). An `empty`
status is terminal for that stage: it SHALL be treated as satisfied, SHALL
NOT be retried automatically, and SHALL be distinguishable from `done` and
`failed` in reports and coverage counts.

#### Scenario: Blank scan is not retried forever
- **WHEN** OCR returns no text for a scanned document and the operator (or
  an automatic rule) classifies it as legitimately empty
- **THEN** the ledger row becomes `empty` with the reason, coverage counts
  the File as complete, and no further OCR attempts are scheduled

#### Scenario: Empty is distinguishable from failed
- **WHEN** coverage is reported
- **THEN** `done`, `empty` and `failed` are reported as separate counts per
  stage

### Requirement: Stages consult the ledger

Each enrichment stage SHALL process only files whose ledger row for that
stage is absent or `failed` (plus, for reconciliation, rows whose recorded
status disagrees with the data — e.g. a `failed` row whose artifact already
exists is marked `done` without reprocessing). The ledger SHALL be the
single source of truth for what a run will attempt; coverage queries and
reports SHALL read from it.

#### Scenario: Completed work is skipped
- **WHEN** a stage runs and a file's ledger row for that stage is `done` or
  `empty`
- **THEN** the file is not reprocessed

#### Scenario: Ledger reconciliation prefers reality
- **WHEN** a ledger row says `failed` but the stage's artifact already
  exists and is valid
- **THEN** the row is marked `done` (reason: reconciled) without
  reprocessing the item
