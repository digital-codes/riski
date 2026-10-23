# Spec Delta

## Purpose

Covers enrichment of imported OParl data: tag management with a full query/add/remove API, name-vector embeddings, content/summary loading, street and district loading plus geo reference matching, and tag analytics export.

## ADDED Requirements

### Requirement: Tag management over an item table
The tag manager SHALL manage tags for any item table via `{item}_tags` and `{item}_tags_assoc` tables created on demand. It SHALL validate the item table exists at construction (raising otherwise), and support: adding tags to items (creating unknown tags), listing tags of an item, finding items matching all of a set of tags, finding items matching any tag, and adding/removing tags to/from a tag catalog table. Invalid inputs (empty tag names) SHALL be rejected.

#### Scenario: Add tags creates tag rows and associations
- **WHEN** tags are added to an existing item, including tags not yet present
- **THEN** new tag rows are created and association rows link the item to all given tags

#### Scenario: Query by all tags
- **WHEN** items are searched requiring all of a set of tags
- **THEN** only items associated with every tag in the set are returned

#### Scenario: Query by any tag
- **WHEN** items are searched requiring any of a set of tags
- **THEN** every item associated with at least one tag in the set is returned

#### Scenario: Item tags lookup
- **WHEN** the tags of a specific item are requested
- **THEN** the exact set of tags associated with that item is returned

#### Scenario: Missing item table rejected
- **WHEN** the manager is constructed for a table that does not exist
- **THEN** construction raises an error

### Requirement: Name-vector embeddings
The name-vector module SHALL maintain a pgvector table of embeddings for an item table's name/label column (fixed dimension, cosine distance), supporting upsert per item, removal, and nearest-neighbor search restricted to items of that table. Embeddings SHALL be produced via the shared remote client.

#### Scenario: Upsert and similarity search
- **WHEN** vectors are upserted for several items and a similarity search is run with one item's name
- **THEN** results are ordered by cosine similarity starting with the queried item itself, and can be limited by a count and a maximum distance

#### Scenario: Remove item vector
- **WHEN** an item's vector is removed
- **THEN** it no longer appears in similarity results

### Requirement: Content and summary loading
The content loaders SHALL map local markdown summary files to `File` rows and update `File.content`, optionally computing content embeddings into the embeddings tables with upsert semantics keyed by `oparlKey`. A one-shot loader SHALL be able to rebuild the embeddings table from a local vector file. Files without a matching summary SHALL be reported and left unchanged.

#### Scenario: Load summaries updates content
- **WHEN** the summary loader runs against a directory of summary files matching `File` rows
- **THEN** matched `File` rows have their content updated and unmatched files are reported

#### Scenario: Optional embeddings upsert
- **WHEN** embedding computation is enabled during loading
- **THEN** embedding rows exist for the loaded files keyed by `oparlKey`, and re-running replaces rather than duplicates them

### Requirement: Street and district enrichment
The enrichment layer SHALL load street names and district names (from GeoJSON/local sources) into the `Street` and `District` tables, and create association tables linking streets and districts to agenda items whose names mention them, using boundary-safe literal matching with longest non-overlapping span selection.

#### Scenario: Load streets and districts
- **WHEN** the street and district loaders run with local geo sources
- **THEN** `Street` and `District` rows exist for the source names without duplicates

#### Scenario: Link mentions to agenda items
- **WHEN** the reference builders run after loading
- **THEN** agenda items whose names contain a street or district name are linked via the association tables, and overlapping shorter matches do not shadow the longest match

### Requirement: Tag analytics export
The tag analytics script SHALL export JSON files grouping agenda-item and file names by configurable German keyword categories, plus distinct consultation roles and agenda-item results from the database.

#### Scenario: Export produces category JSON
- **WHEN** the analytics script runs against a populated database
- **THEN** JSON output files exist containing the keyword-grouped names and the distinct role/result values
