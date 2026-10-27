# data-enrichment Specification

## Purpose

Covers enrichment of imported OParl data: tag management with a full query/add/remove API, name-vector embeddings, content/summary loading, street and district loading plus geo reference matching, organization classification enrichment, and tag analytics export.

## Requirements

### Requirement: Tag management over an item table
The tag manager SHALL manage tags for any item table via `{item}_tags` and
`{item}_tags_assoc` tables created on demand. It SHALL validate the item
table exists at construction (raising otherwise), and support: adding tags
to items (creating unknown tags), listing tags of an item, finding items
matching all of a set of tags, finding items matching any tag, and
adding/removing tags to/from a tag catalog table. Invalid inputs (empty tag
names) SHALL be rejected. Association rows SHALL additionally carry a facet
`scheme`, a `source` provenance, and a `confidence` value; legacy
associations without metadata SHALL default to scheme-less, confidence 1.0.
Tag queries SHALL support filtering by scheme.

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

#### Scenario: Add tags with scheme and provenance
- **WHEN** tags are added with scheme `document-type`, source `papertype`,
  and confidence 1.0
- **THEN** the association rows store scheme, source, and confidence, and
  the item is listed under that scheme

#### Scenario: Query by scheme
- **WHEN** items are searched for a tag restricted to scheme `document-type`
- **THEN** associations of the same tag name under other schemes are ignored

#### Scenario: Legacy associations remain valid
- **WHEN** pre-existing association rows without scheme/source are queried
- **THEN** they are returned with defaults and no data is lost

### Requirement: Name-vector embeddings
The name-vector module SHALL maintain a pgvector table of embeddings for an item table's name/label column (fixed dimension, cosine distance), supporting upsert per item, removal, and nearest-neighbor search restricted to items of that table. Embeddings SHALL be produced via the shared remote client.

#### Scenario: Upsert and similarity search
- **WHEN** vectors are upserted for several items and a similarity search is run with one item's name
- **THEN** results are ordered by cosine similarity starting with the queried item itself, and can be limited by a count and a maximum distance

#### Scenario: Remove item vector
- **WHEN** an item's vector is removed
- **THEN** it no longer appears in similarity results

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

### Requirement: Category derivation and backfill
A derivation pipeline SHALL populate tags in precedence order:
`Paper.paperType` first (source=papertype), then `keyword[]` from raw OParl
JSON if populated (source=oparl-keyword), then regex matching over name
columns reusing the pgAddTags vocabularies (source=name-regex), then batch
LLM classification over `File.teaser` where deterministic passes found
nothing (source=llm).

#### Scenario: paperType takes precedence
- **WHEN** a paper's paperType maps to a document-type tag and a regex rule
  would produce a conflicting one
- **THEN** the papertype-sourced association wins per the documented
  precedence and both remain queryable by source

#### Scenario: Teaser-first LLM escalation
- **WHEN** a file's name matches no regex pattern
- **THEN** its teaser (not its full content) is sent to the LLM for
  classification, bounding the cost

#### Scenario: Backfill is idempotent
- **WHEN** the derivation pipeline runs twice over the same data
- **THEN** no duplicate associations are created

### Requirement: Derivation coverage reporting
The derivation pipeline SHALL report coverage after each run: percentage of
tagged items per item table and per scheme, and counts per tag source.

#### Scenario: Coverage report after backfill
- **WHEN** the backfill completes
- **THEN** a report states, per table and scheme, what fraction of items
  carries at least one tag and how many came from each source

### Requirement: Provided-field harvest
The harvest step SHALL probe the raw OParl JSON in `data` columns for
`keyword[]`, `originatorPerson`/`originatorOrganization`, and `mainFile` on
Paper rows, persisting populated fields with their provenance recorded.

#### Scenario: Populated keywords are harvested
- **WHEN** Paper `data.keyword` arrays are populated for a subset of papers
- **THEN** those keywords exist as topic-scheme tags with source
  oparl-keyword for exactly that subset

#### Scenario: Unpopulated fields are recorded
- **WHEN** a probed field is empty across the corpus
- **THEN** the spike report documents it as not populated and no
  association rows are created

### Requirement: Organization classification backfill
An enrichment pass SHALL derive and store `Organization.classification` for
organizations where it is NULL, using name-regex rules (Ortschaftsrat,
Ausschuss, Beirat, Eigenbetrieb, Amt, Fraktion, ...) in the same additive,
idempotent, re-runnable style as the document-type categorisation pass. The
pass SHALL NOT overwrite non-NULL classifications and SHALL trim surrounding
whitespace from stored organization names.

#### Scenario: NULL classifications derived
- **WHEN** the pass runs on an organization named "Ortschaftsrat Neureut"
  with NULL classification
- **THEN** a gremium-type classification is written and the row is never
  rewritten on re-runs

#### Scenario: Existing classifications preserved
- **WHEN** the pass runs where classification is already set
- **THEN** the value is left untouched

#### Scenario: Whitespace normalised
- **WHEN** an organization name carries leading or trailing whitespace
- **THEN** the stored name is trimmed (e.g. " CDU-Fraktion" → "CDU-Fraktion")

### Requirement: City-specific enrichment rules from instance configuration
The deterministic address-block boilerplate heuristic (house number +
postal code + city name), the venue-noise patterns, the document-type
canonicalization rules and the organization classification name-regex
rules SHALL be sourced from the instance configuration with the current
Karlsruhe rules as defaults (see the `instance-config` capability), so
geo gating, file georeferencing and categorisation run unmodified against
another city's corpus.

#### Scenario: Gating regex follows the configured city
- **WHEN** the geo gate runs against a corpus whose address blocks end in
  the configured city name
- **THEN** pure address mentions are classified boilerplate by the
  deterministic heuristic exactly as they are today for Karlsruhe

#### Scenario: Categorisation without Karlsruhe conventions
- **WHEN** the categorisation pass runs with empty configured
  document-type canonicalization rules
- **THEN** document types pass through verbatim and name-regex/LLM
  classification uses the configured vocabulary
