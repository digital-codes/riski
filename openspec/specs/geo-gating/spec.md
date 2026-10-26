# geo-gating Specification

## Purpose

Löst das Straßen-/Stadtteil-Rauschen auf der Karte: ein zweistufiges Gütegate (deterministischer Adresszeilen-Check + LLM-Verdict) markiert reine Adressnennungen als boilerplate, ein resumable Cleanup-Lauf torchiert den Bestand nach.

## Requirements

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
