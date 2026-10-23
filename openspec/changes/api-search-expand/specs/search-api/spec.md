# search-api Change Spec

## ADDED Requirements

### Requirement: Search Endpoint
The API SHALL expose `POST /search` accepting a query, structured filters,
candidate limits, per-signal toggles, and a summarize flag; it SHALL return
the full search-result contract (top_files, timeline, graph,
matched_entities, facets, applied_filters) plus a sessionId.

#### Scenario: Search returns full contract
- **WHEN** a search request with a query is posted
- **THEN** the response contains graph nodes and edges, matched_entities,
  facets, and an echoed applied_filters list

#### Scenario: Invalid filters are rejected
- **WHEN** a structurally invalid filter is posted
- **THEN** the API responds 422 with the validation message

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
