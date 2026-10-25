# Proposal

## Why

The network view is often visually overloaded, and the connection between
the answer list and the graph is invisible:

- In **topical search**, the documents of the result list (summary pane)
  are graph nodes, but nothing distinguishes them from the traversal's
  surrounding nodes — and when the user disables a document in the list,
  its node looks exactly the same as before (the summarizer's refusals
  are likewise unmarked).
- In the **meeting view** (`list_topics`), the session's agenda items are
  listed as topics, but the network view doesn't mark which TOP nodes
  they are.
- With many nodes the force layout takes very long to settle (repulsion
  320 / gravity 0.12 are tuned for small graphs), so the initial view
  looks chaotic for a long time.

## What Changes

- **Document marking (topical search)** — `NetworkView` receives the
  enabled/excluded/refused document sets from `App.vue` and styles File
  nodes accordingly: enabled documents of the list get a highlight ring;
  excluded or summarizer-refused documents get a dimmed, dashed-red style
  ("rejected"). Tooltips carry the status. The marking updates live as
  the user toggles documents — the props change and the chart re-renders.
- **Topic marking (meeting view)** — the agenda items of the topic list
  are marked in the network with the same highlight ring (the topics'
  `oparlKey`s map directly onto `AgendaItem_<key>` nodes, which the
  meeting-centric graph already contains).
- **Force layout tuning** — gravity 0.12 → 0.25, added friction (0.35)
  for faster damping, node-count-scaled repulsion, and
  `layoutAnimation: false` above a node threshold (large graphs compute
  synchronously instead of wobbling into place for seconds).

## Capabilities

### Modified Capabilities

- `network-view`: node highlighting for answer-list membership and
  rejection state; faster force-layout settling.

## Impact

- **Code**: `app/src/components/NetworkView.vue` (props, node styling,
  force params), `app/src/App.vue` (computed sets passed as props). No
  API/backend changes — all data is already in the result contract
  (`summary_files.excluded`, `summary_refused`, `topics[].oparlKey`,
  `graph.nodes[].attrs.match`).
- **Risk**: pure display logic; the underlying graph data and filters are
  untouched. Mis-marking would only mislead visually, and the worst case
  (stale sets) is bounded by the existing prop reactivity.
- **Tests**: manual verification against the default query (topical) and
  a meeting query (list_topics); no unit-test infra exists for the Vue
  app (verified by build + visual check).
