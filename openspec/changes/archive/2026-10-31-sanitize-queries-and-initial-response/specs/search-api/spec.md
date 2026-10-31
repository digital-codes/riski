# Spec Delta

## MODIFIED Requirements

### Requirement: Search Endpoint

The API SHALL expose `POST /search` accepting a query, structured filters,
candidate limits, per-signal toggles, and a summarize flag. The query SHALL
be sanitized before execution: only letters (German alphabet including
umlauts and ß), digits, whitespace, and common punctuation are allowed; the
query SHALL be at most 250 characters and non-empty after trimming; a query
violating these rules SHALL be rejected with HTTP 400 and a clear,
user-readable German error message — not 422 and not a server error — and
no pipeline stage SHALL run. The endpoint SHALL run the first pipeline
stage (recall) and return the first-stage result contract (top_files,
matched_entities, facets, applied_filters) plus a sessionId. The timeline
and graph SHALL NOT be part of this response; clients retrieve them via the
staged follow-up endpoints using the returned sessionId.

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

#### Scenario: Disallowed characters rejected

- **WHEN** a query contains control characters, HTML/script markup, or
  other characters outside the allowed classes
- **THEN** the endpoint responds 400 with a German message naming the
  problem and no pipeline stage runs

#### Scenario: Over-length query rejected

- **WHEN** a query exceeds 250 characters (after trimming)
- **THEN** the endpoint responds 400 with a message asking to shorten the
  query

#### Scenario: Empty query rejected

- **WHEN** a query is empty or consists only of whitespace
- **THEN** the endpoint responds 400
