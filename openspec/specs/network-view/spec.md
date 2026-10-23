# network-view Specification

## Purpose

Provides the interactive graph view of an answer set in the web app: the
`graph` section of search results (nodes + typed edges derived from the
OParl association tables, no inference) rendered as a force-directed
ECharts network with element selection, a description pane (side pane on
desktop, bottom sheet on mobile), relation/type filtering, calendar and
download deep-links, and merge-by-id dynamic updates fed by the search
API.

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
