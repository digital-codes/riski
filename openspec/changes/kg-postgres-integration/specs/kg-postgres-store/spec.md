# Spec Delta

## Purpose

The typed `kg_*` layer in `riski_agentic` — pair records with verified
outcomes, role-tagged document attachments, item history chains,
statements (JSONB field bags), cross-check verdicts — plus the
ingestion contract that keeps it current: an idempotent migrator with
verification gates, a per-stage run cursor, and upsert-merge priority
rules so new documents and better evidence refresh the layer without
destructive writes.

## ADDED Requirements

### Requirement: Typed kg schema integration
The system SHALL store kg pair data in dedicated `kg_*` PostgreSQL tables keyed on PostgreSQL-native identifiers (`File.sid`/`Paper.sid`/`Meeting.sid` FKs) with oparlId columns retained for cross-checking, such that document tags link to the existing `File.sid` key space and `pair_documents` roles (request/modification/response/attachment) with verification notes are preserved per pair.

#### Scenario: Pair row with resolved identifiers
- **WHEN** the migrator imports a SQLite pair whose key is `<paper_oparlId>|<meeting_oparlId>` and both ids resolve to existing `Paper`/`Meeting` rows
- **THEN** one `kg_pairs` row exists with the resolved sids, unique per (paper_sid, meeting_sid), and its `kg_pair_documents` rows carry the resolved `file_sid` per document plus role and verify_note

#### Scenario: Existing association tables stay unmodified
- **WHEN** the migration runs
- **THEN** no existing riski association table (e.g. `File__paper__Paper`, `Paper__consultation__Consultation`) is repurposed or altered; the kg role matrix lives in `kg_pair_documents`

### Requirement: Idempotent migrator with verification gates
The migrator (`kgMigrate.py`) SHALL run dry-run by default, apply only on explicit flag, upsert every row (ON CONFLICT semantics), resolve sids before writing, abort on pair-parent resolution misses in apply mode, and verify per-table row counts against the SQLite source after import.

#### Scenario: Dry run lists without writing
- **WHEN** kgMigrate runs without the apply flag against a fresh database
- **THEN** it reports planned inserts per table and row-resolution misses, and no `kg_*` table gains rows

#### Scenario: Verification mismatch aborts apply
- **WHEN** a post-import row-count check finds a table where PostgreSQL rows differ from source rows
- **THEN** the migration reports the mismatch table and does not report success

### Requirement: Incremental ingestion contract
The kg layer SHALL remain current as new documents arrive through the regular update workflow: each stage records its progress in a per-stage cursor (`kg_ingestion_runs` with `last_synced_at`, `last_status`, `last_count`), re-runs merge via upserts, new pairs start at `identified`, outcomes upgrade only by evidence-signal priority, refreshes peg on OParl `modified` timestamps, and source deletions map to `status='retired'` without deleting statement/evidence rows.

#### Scenario: New documents join on the next run
- **WHEN** `syncIncremental` adds new papers/consultations and a kg pipeline run follows
- **THEN** kgIdentify creates new `kg_pairs` rows for the new documents without duplicating existing rows, and the cursor table records the stage's completion

#### Scenario: Better evidence upgrades the outcome
- **WHEN** a pair's outcome was derived from partial signals (`db-partial`) and a later run attaches a verified protocol (signal `protocol`)
- **THEN** the outcome and signal upgrade to the stronger evidence and the earlier weaker value is not restored by subsequent weaker runs

#### Scenario: Source deletion retires rather than deletes
- **WHEN** a paper or meeting is flagged deleted at the source
- **THEN** the pair's `status` becomes `retired` and its statements/crosscheck rows remain in place

## REMOVED Requirements

(none)
