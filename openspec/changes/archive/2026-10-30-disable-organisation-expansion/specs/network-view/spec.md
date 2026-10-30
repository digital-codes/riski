# Spec Delta

## ADDED Requirements

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
