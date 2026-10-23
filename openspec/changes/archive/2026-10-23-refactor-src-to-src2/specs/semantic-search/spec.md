# Spec Delta

## Purpose

Covers the read/query paths over the imported data: structural graph queries about files and their relations, pgvector-based semantic search, and the interactive semantic search/timeline CLI — all using read-only database access.

## ADDED Requirements

### Requirement: File relation queries
The query module SHALL report which `File` rows are not referenced by any meeting, paper, or agenda-item association table, and SHALL return the related meeting, agenda-item, and paper identifiers for a given file or agenda item. These read-only queries SHALL use read-only credentials when available.

#### Scenario: Find unreferenced files
- **WHEN** the unreferenced-files query runs on a database where some files have no association rows
- **THEN** exactly those files are returned

#### Scenario: Related ids for a file
- **WHEN** the related-ids query runs for a file linked to meetings, agenda items, and papers
- **THEN** the corresponding identifier sets are returned for each relation kind

### Requirement: Vector search
The vector search module SHALL embed a query text via the shared remote client, search the content-embeddings table by cosine similarity, and return the closest files with their similarity scores, limited by a configurable maximum count and optional score cutoff.

#### Scenario: Search returns ranked files
- **WHEN** a query is embedded and searched against a populated embeddings table
- **THEN** results are files ordered by descending similarity and capped at the requested maximum

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
