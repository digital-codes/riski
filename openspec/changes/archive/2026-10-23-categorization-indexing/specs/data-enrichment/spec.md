# data-enrichment Delta

## MODIFIED Requirements

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

### Requirement: Content and summary loading
The content loaders SHALL map local markdown summary files to `File` rows
and update `File.content`, optionally computing content embeddings into the
embeddings tables with upsert semantics keyed by `oparlKey`. A one-shot
loader SHALL be able to rebuild the embeddings table from a local vector
file. Files without a matching summary SHALL be reported and left unchanged.
Loaders SHALL maintain a `contentKind` provenance marker on `File`
distinguishing stored fulltext from LLM summaries, and the derivation
pipeline order (content → teaser → tags → embeddings) SHALL be documented
and enforced on partial reruns.

#### Scenario: Load summaries updates content
- **WHEN** the summary loader runs against a directory of summary files
  matching `File` rows
- **THEN** matched `File` rows have their content updated with
  `contentKind = 'summary'`, and unmatched files are reported

#### Scenario: Optional embeddings upsert
- **WHEN** embedding computation is enabled during loading
- **THEN** embedding rows exist for the loaded files keyed by `oparlKey`,
  and re-running replaces rather than duplicates them

#### Scenario: Fulltext loading marks provenance
- **WHEN** a file's full text (under the length cutoff) is loaded
- **THEN** the row's `contentKind` is set to `fulltext`

## ADDED Requirements

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
