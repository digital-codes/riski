# Spec Delta

## Purpose

risi topics (the 23-tag ris-ki set) and their grounded qualifiers integrate
into the provenance-stamped tag tables riski already maintains, so
search/facet consumers read them through the standard tag paths while the
vocabulary itself evolves as data (new tags/qualifiers = inserts, with an
optional re-classification pass) — no schema growth for later additions.

## ADDED Requirements

### Requirement: Provenance-stamped topic tags in existing tag tables
kg topic assignments SHALL be written to the existing `File_tags`/`File_tags_assoc` tables under a dedicated scheme value (`kg-topic`) with per-row `source` (extraction method, e.g. `sysone`) and numeric `confidence`, keyed on the existing `oparl_key` string identifier; existing tag schemes remain untouched.

#### Scenario: Topic tag visible to existing consumers
- **WHEN** the kg tag migration runs on a document that carries system-e tags
- **THEN** the document's `oparl_key` shows in `File_tags_assoc` rows carrying scheme `kg-topic` with the confidence value, joinable via the same view existing consumers use

#### Scenario: Existing schemes unaffected
- **WHEN** kg tags are written for documents that also carry `document-type` scheme tags
- **THEN** no `document-type` association row is modified or removed

### Requirement: Vocabulary evolution stays data-only
New tags and qualifiers SHALL enter through the vocabulary file single source of truth and land as rows on the next sync run; later vocabulary changes SHALL NOT require database DDL, and an optional re-classification pass SHALL remove kg-scheme associations before the extractor re-tags the affected documents.

#### Scenario: New tag without DDL
- **WHEN** a new tag is added to the vocabulary file and the sync runs
- **THEN** the tag appears as a `File_tags`/`kg_tags` row and subsequent documents can carry it, while existing rows stay untouched

#### Scenario: Re-classification after vocabulary change
- **WHEN** the vocabulary changes and an explicit re-classification pass is invoked
- **THEN** associations under the kg scheme for the affected documents are removed first and re-created by the extractor, so discontinued tags do not linger

## REMOVED Requirements

(none)
