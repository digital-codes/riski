# Spec Delta

## Purpose

Erweitert die Antwortmenge um alle Dokumente betroffener
Tagesordnungspunkte: Dokumente, die über die Suche gefunden wurden, ziehen
ihre TOP-Geschwister nach — auch über `top_k` hinaus — und per Namenssuche
getroffene TOPs tragen ihre gesamten Dokumente in die Antwortmenge.

## ADDED Requirements

### Requirement: Agenda-item block documents in the answer set

For every agenda item connected to a search result file or matched by name
search, the pipeline SHALL collect the documents of the entire agenda-item
block: all agenda items of the same meeting whose number shares the same
integer prefix. Their linked documents SHALL be appended to the answer set
(`top_files`) after the search hits, marked with a block provenance
reference. The expansion SHALL be deduplicated.

#### Scenario: Sibling subitems of a block

- **WHEN** a search hit is a document of agenda item "13.2" and the meeting
  also has agenda items "13.1" (two documents) and "13.3" (one document)
- **THEN** the answer set additionally contains those three documents,
  appended after the search hits and marked with the block reference

#### Scenario: Other agenda items of the meeting stay excluded

- **WHEN** the same meeting has agenda items "5" and "11" (different
  number prefix) with linked documents
- **THEN** those documents do NOT enter the answer set

#### Scenario: Agenda item matched by name

- **WHEN** the search matches an agenda item by name (lexical or
  name-vector signal) without any of its documents being search hits
- **THEN** the agenda item's block documents enter the answer set and the
  item's node enters the graph

#### Scenario: Deduplication and provenance

- **WHEN** a block document is already a search hit
- **THEN** it is not duplicated in the answer set

### Requirement: No cap on the expanded answer set

The `top_k` limit SHALL apply to the search hits only; appended
agenda-item sibling documents SHALL NOT be cut off to keep the answer set
at `top_k` documents.

#### Scenario: Expanded set exceeds top_k

- **WHEN** the search returns 10 hits whose agenda items link 6 further
  documents
- **THEN** the answer set contains 16 documents
