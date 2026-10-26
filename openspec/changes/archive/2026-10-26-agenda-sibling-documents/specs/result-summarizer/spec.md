# Spec Delta

## MODIFIED Requirements

### Requirement: Full answer-set coverage
The summarizer SHALL build its context from ALL files listed in
`result["top_files"]` — it SHALL NOT truncate the context to a fixed
subset (e.g. the first 5). The set comprises the relevance-ordered search
hits (limited by `top_k`) plus the agenda-item sibling documents appended
by the pipeline (change: agenda-answer-expansion); appended documents
carry their agenda-item provenance and are numbered continuously with the
search hits in the document list.

#### Scenario: All fetched files are included
- **WHEN** a search result contains 10 top files
- **THEN** the assembled prompt contains context from all 10 files

#### Scenario: Sibling documents are included

- **WHEN** the pipeline has appended agenda-item sibling documents to
  `top_files` (beyond `top_k`)
- **THEN** the assembled prompt contains context from the appended
  documents as well, and the document list numbers them continuously with
  the search hits

#### Scenario: Files without text are marked
- **WHEN** a file has neither teaser nor content
- **THEN** the prompt notes its absence (e.g. "Not available") but the
  file still counts as included
