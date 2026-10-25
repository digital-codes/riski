# Spec Delta

## ADDED Requirements

### Requirement: LLM gate for geo references

Every street/district ↔ file and street/district ↔ agenda-item geo link
SHALL be classified by an LLM gate (the summary model, one batched call
per document) into `content` (mention belongs to the document's main
body), `boilerplate` (mention only in header/footer address blocks,
contact/signature blocks, venue boilerplate or similar metadata), or
`unsure`. The verdict, a short reason, the timestamp and the model SHALL
be stored on the association row. A gate failure SHALL never fail the
matching pipeline: affected rows SHALL be left ungated (`gate_status`
NULL) and remain visible until the cleanup pass gates them.

#### Scenario: Sender address is not a content reference
- **WHEN** a document's only mention of a street is in the Briefkopf
  sender/recipient address block
- **THEN** the gate classifies the link `boilerplate` with a reason, and
  the link is excluded from map output

#### Scenario: Address plus genuine content mention
- **WHEN** a street appears in the address block AND in the main body
- **THEN** the gate classifies the link `content` and the link stays
  visible

#### Scenario: Gate failure does not block matching
- **WHEN** the LLM endpoint is unreachable while new geo links are written
- **THEN** the links are written ungated and remain visible

### Requirement: Resumable gate cleanup pass

A cleanup entry point SHALL gate existing ungated association rows in
batches, resumable by construction (the ungated query is the cursor), with
a dry-run mode reporting the verdict distribution before any write, an
option to re-gate `unsure` rows, and an optional purge of `boilerplate`
rows. Existing links SHALL be marked, not deleted, by default.

#### Scenario: Interrupted cleanup continues
- **WHEN** the cleanup pass is interrupted and re-run
- **THEN** it continues with the remaining ungated rows without
  re-processing gated ones

#### Scenario: Dry run before cleanup
- **WHEN** the cleanup runs with dry-run enabled
- **THEN** no rows are written and the verdict distribution is reported

## MODIFIED Requirements

(none — gate storage and pipeline behaviour are new; the map-facing
changes below modify `map-view`)

### map-view: user exclusion and gate filtering

The georeference collection SHALL exclude references from documents the
user has excluded in the summary document list (`summary_excluded`) in
addition to the summarizer-refused documents, so the map reflects exactly
the enabled document set and updates as the user changes it. The GeoJSON
endpoint SHALL omit references whose gate status is `boilerplate` while
showing `content`, `unsure`, and ungated rows.

#### Scenario: Disabled document removed from the map
- **WHEN** the user disables a document in the summary list and the client
  re-fetches `/geo`
- **THEN** streets/districts referenced only by that document no longer
  appear in the FeatureCollection

#### Scenario: Re-enabling restores map items
- **WHEN** the user re-enables a previously excluded document and `/geo`
  is re-fetched
- **THEN** its geo references reappear

#### Scenario: Boilerplate links are hidden
- **WHEN** a street↔file link is gated `boilerplate`
- **THEN** `/geo` does not return that reference even though the row
  exists in the association table
