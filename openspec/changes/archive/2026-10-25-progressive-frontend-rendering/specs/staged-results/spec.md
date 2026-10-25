# Spec Delta

## Purpose

Delivers search results to interactive clients in stages instead of one
monolithic response: the file list becomes available right after recall, the
timeline after timeline building, and the graph last. Each stage is fetchable
separately by sessionId so the frontend can render progress incrementally.

## ADDED Requirements

### Requirement: Staged search pipeline

The search pipeline SHALL execute in three stages per query: (1) recall,
producing the top file list, (2) timeline building, producing the timeline,
(3) graph building, producing the graph. Each completed stage's results SHALL
be stored under the session id and SHALL be fetchable independently of the
later stages, so the file list is available before the timeline, and the
timeline before the graph.

#### Scenario: File list ready before timeline

- **WHEN** the first stage (recall) completes for a query
- **THEN** the top file list is stored under the session id and can be
  returned to the client while timeline and graph are not yet built

#### Scenario: Timeline ready before graph

- **WHEN** the second stage (timeline building) completes for a session
- **THEN** the timeline is stored under the session id and can be returned
  while the graph is not yet built

### Requirement: Staged follow-up endpoints

The API SHALL expose follow-up endpoints that accept a sessionId and return a
single stage's results: one returning the timeline and one returning the
graph. Calling a follow-up endpoint for a stage that has not been built yet
SHOULD trigger that stage's computation for the session. Calling them out of
order SHALL be safe: requesting the graph SHALL also make earlier stage
results available for subsequent requests.

#### Scenario: Fetch timeline for a session

- **WHEN** the client requests the timeline for a sessionId whose first stage
  has completed
- **THEN** the response contains the timeline for that session's results

#### Scenario: Fetch graph for a session

- **WHEN** the client requests the graph for a sessionId whose first stage has
  completed
- **THEN** the response contains the graph for that session's results

#### Scenario: Out-of-order request

- **WHEN** the client requests the graph before ever requesting the timeline
- **THEN** the request succeeds and a subsequent timeline request returns the
  timeline for the same session

### Requirement: Per-stage frontend rendering

The frontend SHALL render each result pane as soon as its stage data arrives:
the file list after the first response, the timeline after the timeline
response, and the network view after the graph response. Panes awaiting their
stage SHALL show a loading state instead of remaining empty or hidden until
all data has arrived.

#### Scenario: File list appears first

- **WHEN** a search is started and the first-stage response arrives
- **THEN** the file list pane renders its entries while timeline and network
  view are still in their loading state

#### Scenario: Timeline appears second

- **WHEN** the timeline response for the session arrives
- **THEN** the timeline pane renders its events while the network view is
  still in its loading state

#### Scenario: Network view appears last

- **WHEN** the graph response for the session arrives
- **THEN** the network view renders the graph

#### Scenario: Search failure

- **WHEN** the first-stage request fails
- **THEN** the UI shows the error and does not leave panes in a permanent
  loading state
