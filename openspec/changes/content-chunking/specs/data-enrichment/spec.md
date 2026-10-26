# Spec Delta

## MODIFIED Requirements

### Requirement: Content and summary loading
The content loaders SHALL map local markdown files to `File` rows and
update `File.content`. For documents at or below the size cutoff, the
loader SHALL store the document text directly (unchanged behavior,
`contentKind = 'fulltext'`). For documents above the cutoff, the loader
SHALL delegate to the chunker instead of producing an LLM summary: chunks
are stored in the chunk table and embedded per chunk, and `File.content`
SHALL carry the document head (first chunk) with `contentKind = 'chunked'`
for backward compatibility. Files without a matching markdown SHALL be
reported and left unchanged. The derivation pipeline order (content →
teaser → tags → embeddings) SHALL be documented and enforced on partial
reruns; LLM summary generation for oversized documents SHALL be retired
from the retrieval pipeline.

#### Scenario: Load summaries updates content
- **WHEN** the loader runs against a directory of markdown files matching
  `File` rows
- **THEN** matched `File` rows have their content updated with the
  appropriate `contentKind` (`fulltext` or `chunked`), and unmatched files
  are reported

#### Scenario: Oversized document chunks instead of summarizing

- **WHEN** a document above the size cutoff is loaded
- **THEN** its chunks are stored and embedded without any LLM call, and
  `File.content` holds the document head marked `contentKind = 'chunked'`

#### Scenario: Optional embeddings upsert
- **WHEN** embedding computation is enabled during loading
- **THEN** embedding rows exist for the loaded files (per chunk for chunked
  documents) keyed by file and chunk index, and re-running replaces rather
  than duplicates them

#### Scenario: Fulltext loading marks provenance
- **WHEN** a file's full text (under the length cutoff) is loaded
- **THEN** the row's `contentKind` is set to `fulltext`
