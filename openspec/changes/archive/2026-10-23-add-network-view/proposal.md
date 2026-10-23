# Proposal: add-network-view

## Why

The web app (`app/`) currently presents query results as a flat, time-grouped
card list (`TimeLine.vue`). This hides the relational structure of the answer
set: files, agenda items, papers, meetings, consultations, organizations and
persons are all connected via OParl association tables, but no view exposes
these relationships. A graph view lets users *explore* an answer set instead
of reading it: see the process structure, spot bridges (e.g. a paper that
influenced later decisions), and drill into entities of interest.

A working prototype exists in `utils/risualization/pgView1.ipynb`
(networkx/pyvis), but it works around the flattened JSON by *inferring* edges
(file–paper attachment is guessed from time-bucket co-occurrence). The real
edges are known at traversal time in `src/pgTimeline.py::find_related_objects`
and must be serialized instead of inferred.

## What Changes

- **Backend**: `pgTimeline` output gains a `graph` section
  (`nodes` + typed `edges`) produced during the existing association-table
  traversal — no second traversal, no edge inference.
- **Backend (follow-up, after data-layer work)**: optional API layer
  (`/search`, `/expand`) enabling incremental graph growth in an interactive
  session; v1 ships with the serialized graph from static query results.
- **Frontend**: new `NetworkView.vue` component (ECharts):
  - v1: 2D `graph-force` renderer with force-atlas-style layout
  - v2 (optional toggle): 3D `graphGL` renderer, time as z-axis
    (newer = front, older = back)
  - side pane (desktop) / bottom panel (mobile ≤768px) showing the
    description of clicked elements: type, name, date, OParl deep-link,
    PDF download, related entities
  - dynamic data updates supported via watch-driven merge-by-id
    (`setOption`), so new search results and later incremental expansions
    update the graph without full re-render

## Capabilities

### New Capabilities
- `graph-serialization`: pgTimeline search results SHALL include a graph
  section with nodes and typed edges derived from the OParl association
  tables traversed while building the timeline.
- `network-view`: The web app SHALL provide an interactive graph view of the
  answer set with element selection, a description pane, and support for
  dynamic data updates.

### Modified Capabilities
- *none* (Timeline and SummaryCard components remain unchanged; the network
  view is an additional component)

## Impact

- **Code**: `src/pgTimeline.py` (serialize edges during traversal),
  `app/src/components/NetworkView.vue` (new), `app/src/components/DetailPanel.vue`
  (new), `app/src/App.vue` (mount the new component), `app/package.json`
  (add `echarts`, later `echarts-gl`).
- **Dependencies on other work**:
  - *Categorization & indexing change (planned)*: node attributes
    (papertype/category tags, district, submitter) and additional edge types
    (semantic similarity, Person/Membership) enrich the graph, but the
    `graph` contract below is designed so these arrive as additive node
    attributes / new edge `relation` values — the network view renders them
    without contract changes.
  - *incremental-oparl-sync change (in flight)*: dynamic updates will
    eventually be fed by sync events; the merge-by-id update mechanism is a
    prerequisite, not a blocker.
- **Renderers**: 2D first is deliberate — 3D graphGL adds a large dependency
  and the ForceAtlas2 simulation has no "pin z-axis" option, so time-as-z
  smears unless layers are bucketed; decide after 2D UX settles.

## Future Work (descoped during this change)

- **Tag-scheme node attributes** — enrich node `attrs` with the full
  canonical tag set (topic/district/submitter schemes from the
  categorization-indexing tag tables) beyond the document-type attrs
  already carried; filter chips for them.
- **Person/Membership nodes and edges** — traversal extension via the
  Membership junction (collapsed to typed edges); blocked in practice by
  unpopulated OParl originator fields (see categorization-indexing spike).
- **Semantic-similarity edges** — pairwise cosine over `contentEmbeddings`
  within the answer set, thresholded, as `relation: "semanticSimilarity"`
  with distance attrs; render as dashed "mesh" edges.
- **graphGL 3D renderer** — time as z-axis/color behind a renderer toggle;
  revisit only if the 2D view proves insufficient (it has not so far).
