# search-api Specification

## Purpose

Exposes the RISKI search pipeline to interactive clients: hybrid search
with structured filters and full result contract (timeline, graph,
matched_entities, facets), depth-1 graph expansion for client-side
merge-by-id exploration, and facet listings for filter UIs.

Implemented by `src/apiServer.py` (FastAPI); the expand engine lives in
`src/graphModel.py` (declarative `ADJACENCY` map, canonical edge
directions).

## Requirements

### Requirement: Search Endpoint

The API SHALL expose `POST /search` accepting a query, structured filters,
candidate limits, per-signal toggles, and a summarize flag. It SHALL run the
first pipeline stage (recall) and return the first-stage result contract
(top_files, matched_entities, facets, applied_filters) plus a sessionId. The
timeline and graph SHALL NOT be part of this response; clients retrieve them
via the staged follow-up endpoints using the returned sessionId.

#### Scenario: Search returns full contract

- **WHEN** a search request with a query is posted
- **THEN** the response contains top_files, matched_entities, facets, and an
  echoed applied_filters list, plus a sessionId; timeline and graph arrive
  via the staged follow-up endpoints, not in this response

#### Scenario: Invalid filters are rejected

- **WHEN** a structurally invalid filter is posted
- **THEN** the API responds 422 with the validation message

#### Scenario: Timeline and graph retrievable via session

- **WHEN** the client calls the staged follow-up endpoints with the returned
  sessionId
- **THEN** the timeline and graph for the search are returned

### Requirement: Expand Endpoint
The API SHALL expose `POST /expand` accepting a node id and returning the
depth-1 neighborhood as additive graph nodes and typed edges, with edges in
canonical direction so client-side merge-by-id never duplicates.

#### Scenario: Expanding a file yields its papers
- **WHEN** `/expand` is called for a File node that belongs to a paper
- **THEN** the response contains the paper node and an edge
  `Paper --auxiliaryFile--> File`

#### Scenario: Unknown node
- **WHEN** `/expand` is called with an unknown or malformed node id
- **THEN** the API responds 404

### Requirement: Facets Endpoint
The API SHALL expose `GET /facets` returning the facet listing (paperType,
years, result, organization, tag counts per scheme).

#### Scenario: Facets drive filter UIs
- **WHEN** `/facets` is fetched
- **THEN** paperType values, result values, years, and per-scheme tag
  counts are present
