# network-view Specification

## Purpose

Provides the interactive graph view of an answer set in the web app: the
`graph` section of search results (nodes + typed edges derived from the
OParl association tables, no inference) rendered as a force-directed
ECharts network with element selection, a description pane (side pane on
desktop, bottom sheet on mobile), relation/type filtering, calendar and
download deep-links, and merge-by-id dynamic updates fed by the search
API. Node expansion is controlled per node type by the graph model
(organisation nodes are currently not expandable), accumulated
meeting-centric graphs stop at organisation nodes, and the graph is
available in a `documents` (default) and `full` scope.

Implemented by `app/src/components/NetworkView.vue` +
`app/src/components/DetailPanel.vue`; the graph contract is defined in
`src/graphModel.py`.

## Requirements

### Requirement: Graph Serialization in Search Results

The timeline search pipeline SHALL include a `graph` section in its result
containing `nodes` and typed `edges` derived from the OParl association
tables and direct foreign keys traversed while building the timeline. Edges
SHALL NOT be inferred from time co-occurrence.

#### Scenario: Edges reflect association tables
- **WHEN** a search returns files whose papers have consultations and
  organizations
- **THEN** the `graph` section contains nodes for each related object and
  edges whose `relation` values correspond to the junction tables /
  foreign keys that produced them (e.g. `auxiliaryFile`, `consultation`,
  `underDirectionOf`)

#### Scenario: Stable node identity
- **WHEN** the same OParl object appears in two consecutive searches
- **THEN** its graph node id is identical (`{Type}_{oparlKey}`), enabling
  merge-by-id updates on the client

### Requirement: Interactive Network View Component

The web app SHALL provide a network view component that renders the graph of
an answer set as a force-directed layout, as an additional component next to
the existing timeline and summary components.

#### Scenario: Render answer-set graph
- **WHEN** search results containing a `graph` section are loaded
- **THEN** the network view displays all nodes grouped/colored by type with
  a legend, and edges styled by relation

### Requirement: Element Description Pane

The network view SHALL provide a description pane (side pane on desktop,
bottom panel on mobile viewports) that displays the details of a clicked
element: type, name, date, OParl deep-link, and — for files — a PDF
download link.

#### Scenario: Click a paper node
- **WHEN** the user clicks a Paper node in the graph
- **THEN** the description pane shows the paper's name, type, date, a link
  to its OParl URL, and the list of connected entities

### Requirement: Dynamic Data Updates

The network view SHALL support dynamic data updates: new or changed graph
data (new search results, later incremental expansions) SHALL be merged
into the current graph by node id without discarding existing nodes or
re-running the layout from scratch for unaffected nodes.

#### Scenario: New search results arrive
- **WHEN** the underlying search data is replaced or extended while the
  view is mounted
- **THEN** nodes with unchanged ids keep their identity (and, where the
  renderer supports it, their position), new nodes appear, and removed
  nodes disappear

### Requirement: Relation Filtering

The network view SHALL allow filtering displayed edges by relation type,
without mutating the underlying graph data.

#### Scenario: Hide file attachments
- **WHEN** the user disables the `auxiliaryFile` relation filter
- **THEN** edges of that relation are hidden while all other relations
  remain visible

### Requirement: Answer-list marking in the network view

The network view SHALL visually distinguish the nodes that belong to the
answer list from the surrounding traversal nodes: documents of the
summary list that are currently enabled SHALL carry a highlight ring;
agenda items of the meeting-view topic list SHALL carry the same
highlight ring. Nodes of documents that are disabled by the user or
refused by the summarizer SHALL be rendered dimmed with a dashed red
border (rejection state) and remain visible in the graph. The marking
SHALL update live when the user toggles documents in the list.

#### Scenario: Enabled documents are distinguishable
- **WHEN** a topical search returns a document list and the network view
  renders
- **THEN** the File nodes of the enabled documents carry the highlight
  ring while traversal-only nodes do not

#### Scenario: Rejected documents are distinguishable
- **WHEN** the user disables a document in the list (or the summarizer
  refused it)
- **THEN** its File node is dimmed with a dashed red border and its
  tooltip states the rejection, while the node stays in the graph

#### Scenario: Marking updates live
- **WHEN** the user toggles a document in the summary list
- **THEN** the corresponding node's marking changes without a new search

#### Scenario: Meeting-view topics are marked
- **WHEN** a meeting-centric answer (list_topics) renders its network
  view
- **THEN** the AgendaItem nodes of the listed topics carry the highlight
  ring

### Requirement: Fast-settling force layout

The force layout SHALL settle quickly for large graphs: stronger gravity
and added damping than the small-graph defaults, node-count-scaled
repulsion, and synchronous layout computation above a node-count
threshold (no long animated wobbling on initial render).

#### Scenario: Large meeting graph settles promptly
- **WHEN** a meeting-centric answer renders a graph with several hundred
  nodes
- **THEN** the layout is computed synchronously (no prolonged animated
  settling) and the initial view is readable without manual
  re-arrangement

### Requirement: Node expansion control

Node expansion SHALL be controlled per node type by the graph model: every
node type with adjacency relations SHALL be expandable, and types without
adjacency or explicitly marked not-expandable SHALL NOT be. Organisation
nodes SHALL be not-expandable for now, while the expansion capability for
the type SHALL remain in place (flag-controlled) so a future change can
enable it or introduce selective per-node expansion.

The API SHALL treat expansion of a not-expandable node type as a defined
outcome (graceful structured response), not a server error. The graph
payload SHALL carry which node types are expandable, as the single source
of truth for the client's expansion controls.

#### Scenario: Organisation expansion disabled

- **WHEN** the user opens the detail pane of an Organisation node
- **THEN** the "Nachbarn laden" control is disabled (with a hint) instead
  of offering an expansion that cannot succeed

#### Scenario: Not-expandable expansion request handled gracefully

- **WHEN** an expansion request arrives for a not-expandable node type
- **THEN** the API responds with a defined not-expandable outcome (no
  server error) and the network view shows an explanatory hint instead of
  a failure message

#### Scenario: Expandable types unchanged

- **WHEN** the user expands a File, AgendaItem, Paper, Meeting, or
  Consultation node
- **THEN** the neighbourhood loads as before and merges into the graph

#### Scenario: Graph payload carries expandability

- **WHEN** a graph payload is delivered to the client
- **THEN** it states which node types are expandable, and the client
  derives the expansion control state from it

### Requirement: No organisation hub in accumulated graphs

The meeting-centric answer's graph accumulation SHALL stop at Organisation:
the expansion rounds SHALL NOT add Organisation nodes or edges — a session
whose consultations all reference the same organisation SHALL NOT produce a
high-degree Organisation hub. The skip SHALL be flag-controlled (disabled,
not removed) so the behaviour can be re-enabled or made selective later.
Single-step user expansion of a Consultation MAY still show its
Organisation as a leaf node.

#### Scenario: Meeting-centric graph without hub

- **WHEN** a meeting-centric answer accumulates its graph over all agenda
  items, consultations and papers of a session
- **THEN** the accumulated graph contains no Organisation nodes and no
  edges to them (for the default query: 436 nodes / 560 edges instead of
  447 / 736, eliminating the 149-edge "Gemeinderat" hub)

#### Scenario: Single consultation expansion keeps its leaf

- **WHEN** the user manually expands a single Consultation node
- **THEN** the response may include the consultation's Organisation as a
  leaf node with its single edge

#### Scenario: Skip is flag-controlled

- **WHEN** the graph model's expansion-skip registry is changed to include
  or exclude Organisation
- **THEN** the accumulation behaviour follows the registry without code
  changes elsewhere

### Requirement: Graph scope selection

The graph stage SHALL compute two scopes per session: `documents` — the
traversal seeded by the top_k answer documents only — and `full` — the
complete result-list traversal including agenda-item name-seed blocks and
their consultation/paper chains. The graph API SHALL accept a scope
parameter with `documents` as the DEFAULT. The network view SHALL offer a
control to switch between the scopes; the default view SHALL be
`documents`. Switching scopes SHALL reuse the existing merge-by-id update
semantics (user accumulations reset to the selected scope's base).

#### Scenario: Default scope is documents

- **WHEN** the network view loads for a search answer
- **THEN** it shows the `documents` scope graph (for the default query:
  ~64 nodes / ~72 edges) without requiring user action

#### Scenario: Toggle to the full result list

- **WHEN** the user activates the scope toggle (e.g. "gesamtes Ergebnis")
- **THEN** the view switches to the `full` scope graph (for the default
  query with the organisation skip: 436 nodes / 560 edges)

#### Scenario: Toggle back

- **WHEN** the user switches back to the documents scope
- **THEN** the view returns to the documents graph (user expansions made
  in the other scope do not persist into it)

#### Scenario: Both scopes computed once

- **WHEN** the graph stage runs for a session
- **THEN** both scopes are computed in that stage and scope switches are
  served without re-running the DB traversal
