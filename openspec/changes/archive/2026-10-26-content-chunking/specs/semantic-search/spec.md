# Spec Delta

## MODIFIED Requirements

### Requirement: Vector search
The vector search module SHALL embed a query text via the shared remote
client (one embedding per query, shared across recall signals), search the
content-embeddings table by cosine similarity at chunk granularity, and
return the closest files with their similarity scores, limited by a
configurable maximum count and optional score cutoff. Files SHALL be
represented by their best-matching chunk (lowest distance per file); the
matched chunk SHALL be available as provenance for reranking and citation.

#### Scenario: Search returns ranked files
- **WHEN** a query is embedded and searched against a populated embeddings
  table
- **THEN** results are files ordered by descending similarity of their best
  chunk and capped at the requested maximum

#### Scenario: Score cutoff filters weak matches
- **WHEN** a minimum similarity is configured
- **THEN** results below that similarity are excluded

#### Scenario: Matched chunk provenance

- **WHEN** a file is recalled via a specific chunk
- **THEN** the result exposes that chunk's index (and/or character range)
  for downstream use
