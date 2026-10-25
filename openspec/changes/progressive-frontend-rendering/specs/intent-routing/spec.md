# Spec Delta

## MODIFIED Requirements

### Requirement: Ask endpoint

The API SHALL expose `POST /ask` accepting a query, an optional sessionId, and
optional search parameters (top_k, signals); it SHALL run the first pipeline
stage (recall) and return the first-stage result contract (top_files,
matched_entities, facets, applied_filters) plus the decoded intent, resolved
slots, and echoed derived filters. The timeline and graph SHALL NOT be part of
this response; clients retrieve them via the staged follow-up endpoints using
the returned sessionId. The endpoint SHALL fall back to plain unscoped search
when the decision-model endpoint is unreachable.

#### Scenario: Routed question returns decoded intent and result

- **WHEN** "was wurde im letzten ortschaftsrat neureut beschlossen?" is posted
- **THEN** the response contains the gremium-scoped first-stage result
  (top_files, no timeline/graph payload), the decoded intent name, the
  resolved gremium/meeting slots, and the derived filters; timeline and graph
  arrive via the staged follow-up endpoints

#### Scenario: Decision model unreachable degrades to search

- **WHEN** the SystemOne endpoint cannot be reached
- **THEN** `/ask` returns plain first-stage results with intent `search_topic`
  and does not fail

#### Scenario: Session id accepted

- **WHEN** a previously returned sessionId is passed
- **THEN** the request succeeds and the session is reused (v1: context is not
  yet consulted)
