# Spec Delta

## MODIFIED Requirements

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
