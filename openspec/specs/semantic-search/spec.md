# semantic-search Specification

## Purpose

Covers the read/query paths over the imported data: structural graph queries about files and their relations, pgvector-based semantic search, and the interactive semantic search/timeline CLI — all using read-only database access. Recall signal fan-out is concurrent, and facet/query-embedding results are cached.

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
per-table candidate count. Every lexical candidate SHALL carry its trigram
similarity in the candidate provenance so downstream stages (fusion
weighting, rerank override, output `match` block) can use it. A candidate
whose only signal is a lexical hit SHALL NOT be excluded from the final
`top_files` list solely because its rerank score is below the acceptance
cutoff; such candidates SHALL be ranked by the combined fusion/rerank
score and remain eligible for the summary stage.

#### Scenario: Exact name fragment is recalled
- **WHEN** a query contains a name fragment (e.g. committee or paper title substring) whose embedding distance is mediocre
- **THEN** the matching entities enter the candidate set via the lexical signal

#### Scenario: Lexical-only File is not rerank-dropped
- **WHEN** a File matches the query with trigram similarity above the lexical threshold but scores below the rerank cutoff
- **THEN** the File stays in `top_files` (ranked by the combined score) and is available to the summary stage

#### Scenario: Lexical similarity in provenance
- **WHEN** a File or entity is recalled via the lexical signal
- **THEN** its `match` provenance includes `lexical_sim` with the similarity value

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

### Requirement: Signal fusion
Hybrid recall SHALL fuse per-signal ranked lists with weighted fusion
using signal-type weights, applied to the default fusion in the API
search path: the lexical signal SHALL receive the highest weight, the
name-vector signal a medium weight, and the content-vector signal the
base weight (defaults 1.5 / 0.8 / 1.2, configurable). Fusion SHALL
support two modes — normalized per-signal score blending (default,
with configurable calibration anchors) and rank-only reciprocal-rank
fusion — and SHALL NOT change the result-contract shapes. All fusion
weights SHALL be deployment-configurable via the instance config
`search` section (env → config file → code defaults); reverting to
unweighted RRF SHALL be possible per instance via the config kill
switch. Each signal SHALL be individually disableable. Any listwise
chat rerank or cross-encoder reranker, when configured, SHALL act as the
final reordering step over the fused candidates; when reranking is
dropped, fused ordering SHALL stand.

#### Scenario: Weighted fusion ranks lexical hits above weak vector hits
- **WHEN** a File has a direct lexical hit and other files rank higher only by content-vector proximity
- **THEN** the lexically-matching File outranks the vector-only files in `file_candidates`

#### Scenario: Score blending preserves within-signal strength
- **WHEN** two candidates match the same signal with clearly different raw scores (e.g. cosine distance 0.35 vs 0.47)
- **THEN** the score-blend fusion ranks the stronger match above the weaker one

#### Scenario: Weights tuned per instance
- **WHEN** an instance config (or `RISKI_SEARCH__FUSION_WEIGHTS__LEX` env override) sets custom fusion weights
- **THEN** fusion uses those weights and the code defaults are untouched

#### Scenario: Kill switch restores unweighted behaviour
- **WHEN** `search.weighted_fusion: false` is set for the instance (or `search.fusion_mode: "rrf"` selects rank-only fusion)
- **THEN** fusion uses plain unweighted RRF as before and no other stage changes

#### Scenario: Fusion completes with partial signals
- **WHEN** one signal returns no candidates
- **THEN** fusion completes with the remaining signals

### Requirement: Recall depth and rerank window
Search SHALL produce `per_signal` candidates per signal (instance-config
`search.per_signal`, default 100) and expose up to `max(top_k,
per_signal)` fused file candidates to the rerank stage. The rerank gate
SHALL run over the first `search.rerank_max_candidates` (default 60)
candidates by fused score *before* the final `top_k` cut; candidates
beyond that window SHALL receive the fallback score `fusion × rerank_cutoff`
(at or below every reranked file). The final `top_files` list SHALL be
sorted by kept score and cut to `top_k` after the gate. When no
cross-encoder reranker is configured, a listwise chat rerank (single
`SUMMARY_MDL` call, `search.listwise_window` default 50, strict-JSON
verdict) MAY rank the fused-first candidates; model-relevant candidates
SHALL keep decaying scores floored at the cutoff, non-relevant ones a
weak score (gate-rejected unless lexically overridden), and any failure
SHALL degrade silently to fused order.

#### Scenario: Deep content match survives default top_k
- **WHEN** a relevant document's best chunk ranks inside the per-signal candidate set but its fused rank is beyond top_k, and the reranker scores it well
- **THEN** the document appears in `top_files` for the default API `top_k`

#### Scenario: Candidates beyond the rerank window keep a clamped score
- **WHEN** a candidate's fused rank is beyond `rerank_max_candidates`
- **THEN** it keeps score `fusion × rerank_cutoff` and cannot outrank an accepted file

#### Scenario: Listwise rerank degrades gracefully
- **WHEN** the listwise chat call fails or returns unparseable output
- **THEN** ordering falls back to the fused order and the search completes

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

### Requirement: Concurrent recall signals
Hybrid recall SHALL execute the independent per-table, per-signal candidate
queries (lexical, name-vector, content-vector across Paper, File,
AgendaItem, Meeting) concurrently instead of sequentially. The fused result
for a given query, filters, and signal configuration MUST be identical to
the sequential execution, and a failure of one signal query MUST degrade to
that signal returning no candidates rather than failing the whole search.

#### Scenario: Result parity with sequential execution
- **WHEN** the same query, filters, and signal toggles run through the
  concurrent implementation and a recorded sequential baseline
- **THEN** the fused candidate ordering and scores are identical

#### Scenario: Concurrent execution
- **WHEN** hybrid recall runs with timing instrumentation enabled
- **THEN** the per-signal queries overlap in time (total wall time is
  below the sum of individual signal durations for multi-signal searches)

#### Scenario: Single signal failure degrades
- **WHEN** one signal query raises an exception
- **THEN** that signal contributes no candidates and the other signals
  still produce a fused result

### Requirement: Facet listing cache
The facet listing SHALL be cached in-process with a time-to-live (default
10 minutes) so repeated requests do not recompute the aggregates. Cached
facets SHALL be invalidated when the data pipeline writes new data. A
cache-miss MUST produce exactly the same listing as an uncached call.

#### Scenario: Repeated requests served from cache
- **WHEN** `/facets` or the per-search facet block is requested twice
  within the TTL
- **THEN** the second request does not recompute the aggregates and
  returns the same content

#### Scenario: Cache invalidated after sync
- **WHEN** a data update writes new OParl entities
- **THEN** the next facet request reflects the new data within the same
  process

### Requirement: Query embedding cache
Query embeddings SHALL be cached in-process with a bounded size (LRU,
default 256 entries) keyed by model and text, so repeated queries skip the
remote embedding call. Document-content embeddings SHALL NOT be cached
(their volume makes the cache pointless).

#### Scenario: Repeated query skips the remote call
- **WHEN** the same query text is embedded twice within the cache size
- **THEN** the remote embedding endpoint is called only once and both
  callers receive the same vector

#### Scenario: Different texts still reach the remote client
- **WHEN** distinct query texts are embedded
- **THEN** each is fetched from the remote endpoint normally
