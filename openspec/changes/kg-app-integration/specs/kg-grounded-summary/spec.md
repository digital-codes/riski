# Spec Delta

## Purpose

Ground the answer summarizer in extracted kg statements: facts (topic,
requested action, outcome, cost, dates, author) from paper+response
pairs travel with the documents into the summarizer prompt; flagged
fields are excluded.

## ADDED Requirements

### Requirement: Statement-grounded summary prompt
The result summarizer SHALL, per document with a kg pair, extract the
pair's request and response statements (`kg_statements` via
`kg_pairs.paper_sid`) and include a German grounding block in the
prompt ("Für dieses Dokument liegen extrahierte Fakten vor: …"),
instructing the model to prefer these facts and cite them; documents
without a pair/summary fall back to teaser-only grounding (previous
behaviour).

#### Scenario: Outcome sentence grounded
- **WHEN** a document's response statement holds outcome
  "einstimmig zugestimmt" and the summary without grounding would say
  "wird geprüft"
- **THEN** the generated summary states the decision outcome correctly

#### Scenario: No statements fall back
- **WHEN** a document has no kg pair (few documents lack one — the
  59-textless skipped set)
- **THEN** the summarizer behaves exactly as before (teaser layer)

### Requirement: Flagged fields are not groundable
Statement fields carrying failure flags (`_flags`/`_flagged` blocks in
`fields_json` — kgFlagFailures) SHALL be stripped from the grounding
block: the flagged value stays in the `_flagged` note (available for
the model only as conspicuous doubt, not as fact) or is omitted
entirely; the plain (blanked) field may not be groundable.

#### Scenario: Hallucinated cost never grounds
- **WHEN** a statement's `involved_cost` was flagged
  `cost-misattribution` and blanked with a note
- **THEN** the grounding block for that document contains no cost
  statement, or the flagged note explicitly marked as unsicher (when
  configured) — never a plain number

### Requirement: Grounding provenance statement
The summarizer SHALL declare the grounding source in its provenance
footer when statements were used (grounding = "kg-StatementLayer v1"
plus pair count), so an operator can tell grounded answers from plain
ones.

#### Scenario: Provenance footer extended
- **WHEN** the summary used statements for 3 of 5 documents
- **THEN** the footer states grounding coverage 3/5 and the kg-layer
  provenance marker, displayed in the PDF export together with the
  footer's existing fields

## REMOVED Requirements

(none)
