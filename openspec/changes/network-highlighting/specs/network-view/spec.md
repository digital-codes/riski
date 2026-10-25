# Spec Delta (network-view)

## ADDED Requirements

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
