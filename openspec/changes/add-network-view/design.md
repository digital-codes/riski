# Design: add-network-view

## Context

`pgTimeline.search_and_build_timeline()` traverses 7+ association tables
(`find_related_objects`) to collect related OParl objects, then flattens them
into a timeline (`build_timeline`, `group_timeline_events`). The traversal
knows every edge (srcSid/tgtSid + junction table); the flattened output
discards them. The prototype in `utils/risualization/pgView1.ipynb` rebuilds
a graph from the flattened JSON, but must *infer* file→paper edges from
time-bucket co-occurrence (false positives) and cannot see AgendaItem,
Meeting, Consultation, Organization relations at all.

The DB also stores each object's raw OParl JSON in a `data` longtext column,
so additional relations (mainFile, originator*, keyword) are recoverable
without re-crawling — tracked separately in the categorization/indexing work.

## Goals / Non-Goals

**Goals:**
- Serialize the *true* association graph alongside the timeline (no
  inference).
- A Vue component rendering the graph with ECharts, click-to-inspect, and
  merge-by-id dynamic updates.
- A data contract stable enough that frontend and backend can evolve
  independently (mock data for frontend work).

**Non-Goals:**
- API server / session management (follow-up change after data layer).
- Semantic-similarity edges, Person/Membership traversal, category
  attributes (categorization & indexing change; additive to this contract).
- Time-as-z 3D rendering (v2; renderer choice independent of contract).

## Decisions

### 1. Graph JSON contract (frozen early)

```json
"graph": {
  "nodes": [
    { "id": "Paper_46236",           // "{Type}_{oparlKey}" — stable across searches/expansions
      "type": "Paper",               // Paper | File | AuxFile | AgendaItem | Meeting | Consultation | Organization
      "name": "Digitalstrategie …",
      "date": "2021-12-27",
      "oparlId": "https://…/papers/vo/46236",
      "attrs": { }                   // additive: papertype, categories, district, distance, …
    }
  ],
  "edges": [
    { "source": "File_635289", "target": "Paper_46236",
      "relation": "auxiliaryFile",   // one value per association table / FK, e.g.
                                     // auxiliaryFile | mainFile | meetingFile | agendaItem |
                                     // consultation | organization | underDirectionOf |
                                     // subordinatedPaper | superordinatedPaper
      "attrs": { } }
  ]
}
```

- Node id embeds the type to stay globally unique (oparlKeys collide across
  tables; the pgView1 prototype already converged on `Type_key` ids).
- `relation` values mirror the junction-table/FK names — the adjacency map
  (below) is the single source of truth.
- Unknown future relations/attributes must degrade gracefully (frontend
  renders unstyled rather than failing).

### 2. Serialization at traversal time (no second query pass)

`find_related_objects` gains an edge log: each SELECT that produces objects
also records `(srcType_srcKey, relation, tgtType_tgtKey)`. Direct FKs
(`File__paper`, `File__meeting`, `AgendaItem.meetingSid/consultationSid`)
are captured the same way. Serialization helper emits the `graph` block;
`build_timeline`/`group_timeline_events` stay untouched.

### 3. Declarative adjacency map generalizes traversal

Replaces the hard-coded steps in `find_related_objects` with a table map
(one row per association/FK, derived from `references/postgres/riski-struct.sql`):

```
ADJACENCY = {
  "Paper":       [("auxiliaryFile","File","Paper__auxiliaryFile__File"),
                  ("consultation","Consultation","Paper__consultation__Consultation"),
                  ("underDirectionOf","Organization","Paper__underDirectionOf__Organization"),
                  ("subordinated","Paper","Paper__subordinatedPaper__Paper")],
  "File":        [("mainPaper","Paper","File__paper__Paper"),
                  ("meeting","Meeting","File__meeting__Meeting")],
  "Meeting":     [("agendaItem","AgendaItem","Meeting__agendaItem__AgendaItem"),
                  ("auxiliaryFile","File","Meeting__auxiliaryFile__File"),
                  ("organization","Organization","Meeting__organization__Organization")],
  "AgendaItem":  [("auxiliaryFile","File","AgendaItem__auxiliaryFile__File")],
  "Consultation":[("organization","Organization","Consultation__organization__Organization")],
  # later: Person/Organization via Membership; originator* from data JSON
}
```

One code path then powers initial search (depth-1 from seed files) *and*
later `/expand` (depth-1 from any node). New relation types = new map rows.

### 4. Frontend: 2D `graph-force` first

- ECharts `graph` series, `layout: 'force'`, categories = node types
  (color legend), node size by degree.
- Merge-by-id updates: component owns `{nodes, edges}` in reactive state;
  `watch(props)` diffs and calls `setOption` (update, not replace). For
  force layout, previously laid-out positions are fed back so existing
  nodes don't jump when data grows.
- DetailPanel: shared component; right side pane on desktop, bottom sheet on
  ≤768px (matches the existing `isMobile` breakpoint pattern in
  `TimeLine.vue`).
- Time encoding in 2D: node color gradient by date + time-range filter
  toggle; optionally syncs with existing `TimeLine.vue` groups later.
- graphGL (3D, time as z) deferred: echarts-gl is a large dependency and
  ForceAtlas2 pulls on all axes (no pin-z), so z-as-time needs bucketing
  hacks; revisit after 2D UX settles. Renderer stays a toggle — the
  contract is renderer-agnostic.

### 5. Synthetic prototype nodes are dropped

pgView1's `category` and `Timeline` nodes were workarounds for the missing
graph. Real categories arrive as node `attrs` (categorization change); the
legend replaces category hubs. A synthetic time-ribbon can be a later
experiment, not v1.

## Risks / Trade-offs

- **Traversal fan-out**: TOP_K=100 seed files can pull in hundreds of nodes.
  Mitigation: node cap in stats, per-relation limits if needed.
- **Consultation nodes are abstract** (no date, no name) — rendering them
  adds clutter without content. Mitigation: collapsible via relation filter,
  or edge-through (Paper→Organization direct with consultation semantics as
  edge attr). Decide during frontend work with real data.
- **ECharts bundle size**: import only used charts; NetworkView is lazy.

## Contract Deltas from categorization-indexing (task 5.1 handoff)

The search-result JSON now carries additive sections that map directly
onto this change's node attributes and UI facets:

- **`matched_entities`**: fused candidate entities across Paper, File,
  AgendaItem, Meeting (`{id: "{Type}_{oparlKey}", type, oparlKey, name,
  score}`) — same `{Type}_{oparlKey}` id convention as the graph contract;
  renderable as pre-seeded graph nodes / graph entry points.
- **`facets`**: available filter values with counts (`paperType`, `years`,
  `result`, `tags` per scheme) → facet dropdowns in the network view UI.
- **`applied_filters`**: normalized filter list; when the network view
  renders node `attrs`, facet values (tags by scheme, paperType, dates)
  arrive per node and support client-side graph filtering.
- **Search entry point changed**: results may seed from Papers/AgendaItems
  (name vectors / lexical), not only Files — the graph's seed set follows
  `matched_entities`, expanding around whichever entity type matched.
- **Filters at query time**: `search_and_build_timeline(..., filters=[...])`
  — the API layer must accept the same filter model verbatim.
- **Name-vector tables** (`{item}_name_vecs`) and LLM tag backfill are
  pending operator runs (categorization-indexing tasks 3.5-LLM, 4.1);
  contracts already tolerate their absence (graceful degradation).

## Migration Plan

1. Backend: adjacency map + edge log + `graph` serialization + unit tests
   (extend `src/tests/test_unit_pgTimeline.py`).
2. Update `sampleData.json` with a real `graph` section (run against DB).
3. Frontend: NetworkView + DetailPanel on mock/sample data; App.vue mounts it.
4. Later: API + `/expand`, graphGL toggle, Person/semantic edges
   (additive).
