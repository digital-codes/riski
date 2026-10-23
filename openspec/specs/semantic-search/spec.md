# semantic-search Specification

## Purpose

Covers the read/query paths over the imported data: structural graph queries about files and their relations, pgvector-based semantic search, and the interactive semantic search/timeline CLI — all using read-only database access.

## Requirements

### Requirement: File relation queries
The query module SHALL report which `File` rows are not referenced by any meeting, paper, or agenda-item association table, and SHALL return the related meeting, agenda-item, and paper identifiers for a given file or agenda item. These read-only queries SHALL use read-only credentials when available.

#### Scenario: Find unreferenced files
- **WHEN** the unreferenced-files query runs on a database where some files have no association rows
- **THEN** exactly those files are returned

#### Scenario: Related ids for a file
- **WHEN** the related-ids query runs for a file linked to meetings, agenda items, and papers
- **THEN** the corresponding identifier sets are returned for each relation kind

### Requirement: Vector search
The vector search module SHALL embed a query text via the shared remote
client (one embedding per query, shared across recall signals), search the
content-embeddings table by cosine similarity, and return the closest files
with their similarity scores, limited by a configurable maximum count and
optional score cutoff.

#### Scenario: Search returns ranked files
- **WHEN** a query is embedded and searched against a populated embeddings
  table
- **THEN** results are files ordered by descending similarity and capped at
  the requested maximum

#### Scenario: Score cutoff filters weak matches
- **WHEN** a minimum similarity is configured
- **THEN** results below that similarity are excluded

### Requirement: Semantic timeline CLI
The timeline CLI SHALL combine vector search with reranking, resolve related meetings/agenda items/papers for the matched files, build a timeline grouped into fixed windows (30 days) around matched files, optionally summarize the top files via the chat client, and save the results as JSON.

#### Scenario: Timeline is grouped and saved
- **WHEN** the CLI runs with a search phrase against a populated database
- **THEN** a JSON result file exists containing matched files with related entities grouped into 30-day windows

#### Scenario: Summarization is optional
- **WHEN** summarization is disabled
- **THEN** the CLI completes without any chat-model calls and still writes the timeline JSON

### Requirement: Lexical name recall
Search SHALL produce lexical candidates using trigram similarity over the
indexed `name` columns of Paper, File, AgendaItem, and Meeting (indexes
already created by pgGen), with a configurable similarity threshold and
per-table candidate count.

#### Scenario: Exact name fragment is recalled
- **WHEN** a query contains a name fragment (e.g. committee or paper title
  substring) whose embedding distance is mediocre
- **THEN** the matching entities enter the candidate set via the lexical
  signal

### Requirement: Name-vector recall
Search SHALL produce vector candidates over `{item}_name_vecs` tables for
Paper, AgendaItem, Meeting, and File, using the shared query embedding.

#### Scenario: Name vectors seed non-file entities
- **WHEN** a query is semantically close to a Paper or AgendaItem name
- **THEN** that entity is returned as a matched entity, not only files —
  enabling graph entry points beyond files

#### Scenario: Missing name-vector table degrades gracefully
- **WHEN** a name-vector table is absent or empty
- **THEN** recall completes with the remaining signals and a coverage note
  is logged

### Requirement: Candidate fusion
Search SHALL fuse lexical, name-vector, and content-vector candidate lists
by reciprocal-rank fusion with configurable k and per-signal top-N; each
signal SHALL be individually disableable. The existing reranker SHALL
remain the final ranking step.

#### Scenario: Fusion completes with partial signals
- **WHEN** one signal returns no candidates
- **THEN** fusion completes with the remaining signals

#### Scenario: Reranker decides final order
- **WHEN** fused candidates are produced
- **THEN** final result ordering is determined by the existing reranker
  over `File.content` for files, with non-file entities ordered by their
  best fused rank

### Requirement: Structured faceted filters
Search SHALL accept a structured filter list applied pre-fusion supporting
at minimum: `paperType` (set), year/date range with selectable basis
(Paper.date, Meeting start, File.date), `AgendaItem.result`,
`Consultation.role` and `authoritative`, tags by scheme and value, and
district.

#### Scenario: Filter to paper type
- **WHEN** a search runs with `paperType in ["Beschlussvorlage"]`
- **THEN** only papers of that type (and their related entities) enter the
  candidate set and rerank

#### Scenario: Filter consultations by year and outcome
- **WHEN** filters restrict to meetings within 2021 and agenda item result
  "beschlossen"
- **THEN** only entities associated with qualifying meetings/results are
  returned

### Requirement: Facet listing in results
Search results SHALL echo applied filters and SHALL include a `facets`
section listing available filter values with counts: distinct paperType and
result values, years present, and per-scheme tag counts.

#### Scenario: Facet listing drives UI dropdowns
- **WHEN** a search result is returned
- **THEN** its `facets` section contains the distinct paperType values,
  result values, present years, and per-scheme tag counts with item counts
