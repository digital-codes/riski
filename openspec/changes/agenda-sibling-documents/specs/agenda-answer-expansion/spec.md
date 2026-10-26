# Spec Delta

## Purpose

Erweitert die Antwortmenge um alle Dokumente betroffener
Tagesordnungspunkte: Dokumente, die über die Suche gefunden wurden, ziehen
ihre TOP-Geschwister nach — auch über `top_k` hinaus — und per Namenssuche
getroffene TOPs tragen ihre gesamten Dokumente in die Antwortmenge.

## ADDED Requirements

### Requirement: Agenda-item sibling documents in the answer set

The pipeline SHALL collect, for every agenda item connected to a search
result file or matched by name search, all documents linked to that agenda
item and SHALL append the ones not already present to the answer set
(`top_files`) after the relevance-ordered search hits, marked with a
provenance reference to their agenda item. The expansion SHALL be
deduplicated and SHALL NOT traverse further relations of the appended
documents.

#### Scenario: Sibling documents of a subitem

- **WHEN** a search hit is a document of agenda item "13.2" and the agenda
  item links three documents, one of which is the search hit
- **THEN** the answer set contains all three documents, the two siblings
  appended after the search hits and marked with the agenda item reference

#### Scenario: Agenda item matched by name

- **WHEN** the search matches an agenda item by name (lexical or
  name-vector signal) without any of its documents being search hits
- **THEN** the agenda item's node and all its documents enter the answer
  set and the graph

#### Scenario: Deduplication and provenance

- **WHEN** a sibling document is already a search hit
- **THEN** it is not duplicated in the answer set

### Requirement: No cap on the expanded answer set

The `top_k` limit SHALL apply to the search hits only; appended
agenda-item sibling documents SHALL NOT be cut off to keep the answer set
at `top_k` documents.

#### Scenario: Expanded set exceeds top_k

- **WHEN** the search returns 10 hits whose agenda items link 6 further
  documents
- **THEN** the answer set contains 16 documents
