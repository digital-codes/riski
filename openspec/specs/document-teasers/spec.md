# document-teasers Specification

## Purpose

One true, document-wide teaser per file: generated from the complete
document text (all chunks for chunked documents) via an aggressive
summarisation stage, capped at the teaser word budget. The teaser is
consumed as summarizer context, so it must describe the whole document
rather than only its head chunk, and its stored length must stay bounded.

## Requirements

### Requirement: One true teaser per document

Each document SHALL have at most one teaser (stored per file, not per
chunk). The teaser SHALL be generated from the COMPLETE document text: for
chunked documents all stored chunks SHALL contribute, via an aggressive
summarisation stage (per-chunk pre-summaries reduced into the final teaser)
that keeps the teaser within its word budget regardless of document length.
The teaser SHALL NOT be built from the truncated head chunk alone when the
document has further chunks.

#### Scenario: Chunked document teaser covers the whole document

- **WHEN** a teaser is generated for a document stored as multiple chunks
- **THEN** every chunk contributes to the teaser (pre-summaries reduced into
  one result) and the result stays within the teaser word budget

#### Scenario: Non-chunked document teaser unchanged

- **WHEN** a teaser is generated for a document whose text is stored whole
- **THEN** the teaser is generated from that text exactly as before

#### Scenario: Single teaser per document

- **WHEN** a document consists of many chunks
- **THEN** exactly one teaser is stored for the document — never one per
  chunk

#### Scenario: Head-only teaser regenerated

- **WHEN** the backfill runs over chunked documents whose existing teaser
  was generated from the head chunk only
- **THEN** the teaser is regenerated from all chunks and overwrites the
  head-only teaser

### Requirement: Teaser length ceiling

Because the teaser is consumed as summarizer context, its stored length
SHALL NOT exceed the maximum chunk size by more than 20% (≈9.600 characters
for the current 8.000-char chunk limit). Every path that stores a teaser —
the summary result as well as fallback truncations of document text — SHALL
respect this ceiling.

#### Scenario: Teaser length ceiling respected

- **WHEN** a teaser is stored (summary result or fallback truncation of
  document text)
- **THEN** its length stays within 120% of the maximum chunk size — no
  fallback path stores a longer teaser
