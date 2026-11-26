# staged-results Specification

## Purpose

Delivers search results to interactive clients in stages instead of one
monolithic response: the file list becomes available right after recall, the
timeline after timeline building, and the graph last. Each stage is fetchable
separately by sessionId so the frontend can render progress incrementally.

## Requirements

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

### Requirement: Search result card layout (search_topic)

The interactive client SHALL render the `search_topic` result view with the
following card order: (1) summary card (once the summary stage delivered;
loading state before), (2) map card — only when geo data is available,
(3) timeline card, (4) network graph card (moved from the former first
position to last). The former top-10-files card SHALL be dropped from the
view. The former unstyled tags/related-documents paragraph block SHALL be
dropped from the view. The summary card SHALL no longer embed the related
section; instead a separate styled related-hints card SHALL follow the
summary card.

#### Scenario: Card order matches the contract

- **WHEN** a `search_topic` query returns files, meta, and geo data
- **THEN** the view shows summary card, then related-hints card (when
  allowed), then map, then timeline, then network graph — no top-10-files
  card and no unstyled tags/related-documents paragraph

### Requirement: Related-hints card visibility

The related-hints card SHALL show the refinement chips (kg topic hints the
user can pick to refine the query) and the related documents. It SHALL be
rendered ONLY when the result did NOT find a kg topic with a sufficiently
high score to enable a topical summary (topic focus below the topical
threshold) AND the search delivered NO files ("Verfeinerung & verwandte
Dokumente" is the card for the nebulous case — a real hit list leaves no
room for it). The chips SHALL be presented as interactive options — their
purpose is to give the user hints for refining the search query — not as
document list content.

#### Scenario: Hidden when the search delivered files
- **WHEN** a `search_topic` result carries at least one file in its top-file list (or selected summary files)
- **THEN** no related-hints card is rendered, regardless of related documents

#### Scenario: Hidden when topical summary enabled

- **WHEN** the query matched a kg topic above the topical threshold and the
  summary was generated with topic focus
- **THEN** no related-hints card is rendered (the summary stands alone)

#### Scenario: Shown for unfocused queries

- **WHEN** the query produced no topic focus above the threshold (plain
  search results) and related documents exist
- **THEN** the related-hints card follows the summary card with the
  refinement chips first, related documents second

#### Scenario: Chips are always inside a card
- **WHEN** any chip surface renders (refinement chips, clarification chips, weak-recall chips, follow-up question chips)
- **THEN** the chips are inside a styled card — never naked on the page
- **AND** a new search clears previously displayed chips with the other panes (no stale chips below a newer view)

#### Scenario: Chips refine the query (follow-up, not new search)

- **WHEN** the user picks a chip in the related-hints card
- **THEN** a FOLLOW-UP search is issued: the queries from the history are
  included in the query (amended query: prior query + chip topic/example)
  and the thread state is carried, so the server resolves the refinement in
  context
- **AND** a NEW search (the search button / a user-typed fresh query)
  clears the history — the server-side thread starts fresh

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
