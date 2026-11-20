# Spec Delta

## Purpose

Find thematically related documents using the kg-topic tag layer: the
top search documents carry their kg-topic tags; documents sharing
enough topics with them are surfaced as related without any model call.

## ADDED Requirements

### Requirement: Related documents via shared topic tags
The system SHALL annotate search responses with related documents
computed from the kg-topic scheme (`File_tags_assoc`, scheme
`kg-topic`): a document is related when it shares at least two distinct
tags with the top-ranked search documents, scored by the number of
shared tags weighted by tag confidence; the response carries at most 10
related documents with name, download link and shared-tag list. No LLM
call SHALL be involved in computing relatedness.

#### Scenario: Related through shared topics
- **WHEN** a search returns a document tagged `Mobility` (0.9) and
  `Building Construction` (0.8) and another document exists with the
  same two tags
- **THEN** the second document appears in `related_documents` with the
  shared tag names, ranked by shared-tag volume × confidence

#### Scenario: No related documents
- **WHEN** the top documents carry tags that no other document shares
  (two-tag threshold not met)
- **THEN** `related_documents` is empty and the frontend omits the pane

#### Scenario: Flagged sources weighted lower
- **WHEN** a related document's kg-topic assignments carry an
  `updated` timestamp older than its statement's last
  failure-flagging pass (i.e. the tags predate the latest quality
  repair)
- **THEN** the document's relatedness weight is halved; it still appears

## REMOVED Requirements

(none)
