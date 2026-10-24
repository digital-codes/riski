# semantic-search Delta

## ADDED Requirements

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