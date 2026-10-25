# Spec Delta

## MODIFIED Requirements

### Requirement: Search Endpoint

The API SHALL expose `POST /search` accepting a query, structured filters,
candidate limits, per-signal toggles, and a summarize flag; it SHALL return
the full search-result contract (top_files, timeline, graph,
matched_entities, facets, applied_filters) plus a sessionId. The default
for the summarize flag SHALL be `false`: the LLM summary SHALL be produced
by the `POST /summarize` follow-up (sessions), while callers MAY pass
`summarize=true` to request the summary inline. Per-request database
fan-out SHALL be bounded so a single search cannot exhaust the connection
pool; when the pool or the fan-out budget is saturated, the endpoint SHALL
respond 503 with a `Retry-After` header rather than an unhandled error.

#### Scenario: Search returns full contract
- **WHEN** a search request with a query is posted
- **THEN** the response contains graph nodes and edges, matched_entities,
  facets, and an echoed applied_filters list

#### Scenario: Invalid filters are rejected
- **WHEN** a structurally invalid filter is posted
- **THEN** the API responds 422 with the validation message

#### Scenario: Summary is opt-in by default
- **WHEN** a search request omits the summarize flag
- **THEN** the response contains the search contract without `summary`, and
  a subsequent `/summarize` call with the returned sessionId produces it

#### Scenario: Pool saturation degrades gracefully
- **WHEN** concurrent searches exceed the bounded fan-out budget within the
  pool timeout
- **THEN** excess requests respond 503 with `Retry-After` instead of an
  unhandled 500

## ADDED Requirements

### Requirement: Session Store

The API SHALL maintain in-memory search sessions (sessionId → query,
filters, result) for the session-backed endpoints. Sessions SHALL be
evicted on a time-to-live basis and the store SHALL be capped in size
(oldest evicted first); eviction SHALL happen on session creation without a
background thread. A session id from before a process restart MAY be
unknown — clients SHALL treat unknown sessions as expired (404) and re-run
the search.

#### Scenario: Old sessions expire
- **WHEN** a session is older than the configured TTL and any new session is
  created
- **THEN** the expired session is evicted and its endpoints respond 404

#### Scenario: Store size is bounded
- **WHEN** the number of live sessions exceeds the configured maximum
- **THEN** the oldest sessions are evicted to bring the store back to the
  cap
