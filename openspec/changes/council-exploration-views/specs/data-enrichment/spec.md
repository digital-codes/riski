# Spec Delta

## ADDED Requirements

### Requirement: Submitter detection

The system SHALL detect the submitting body (Einbringer) of papers and
their files, rule-based on document labels and titles, without LLM calls.
Joint submissions SHALL be detected as multiple submitters. The submitter
SHALL be stored as a paper enrichment, resumable over the existing corpus,
and SHALL be surfaced on search/browse results. Papers whose labels name no
recognizable submitter SHALL have no submitter value rather than a guessed
one.

#### Scenario: Fraction application detected

- **WHEN** a paper/file is labeled "Antrag CDU_014 — …"
- **THEN** the detected submitter is "CDU"

#### Scenario: Joint submission

- **WHEN** a label names two groups (e.g. "Antrag KAL/Die Partei, DIE LINKE …")
- **THEN** both groups are stored as submitters

#### Scenario: Administrative document has no submitter

- **WHEN** a paper label carries no fraction/group pattern (e.g. a
  Beschlussvorlage from the administration)
- **THEN** no submitter value is stored

#### Scenario: Backfill is resumable

- **WHEN** the submitter backfill is interrupted and re-run
- **THEN** already-processed papers are skipped and no duplicates are created

### Requirement: Decision status normalization

The system SHALL normalize the free-text `AgendaItem.result` field into a
controlled decision status vocabulary (approved/decided, rejected, noted,
withdrawn, deferred, other) and expose the normalized status on agenda-item
results (graph, search/browse results). Items without a result value SHALL
have no decision status rather than a guessed one.

#### Scenario: Unanimous approval normalized

- **WHEN** an agenda item's result reads "einstimmig beschlossen"
- **THEN** the normalized status is approved/decided

#### Scenario: Majority rejection normalized

- **WHEN** an agenda item's result reads "mehrheitlich abgelehnt"
- **THEN** the normalized status is rejected

#### Scenario: Missing result stays empty

- **WHEN** an agenda item has no result value
- **THEN** no decision status is exposed for it
