# Disable organisation expansion

## Why

The network view for the default query ("wo liegt die Governance für
Digitalisierung bei der Stadt Karlsruhe") is far too complex: **447 nodes /
736 edges**. The query routes to the meeting-centric gremium answer
(`meeting_scope_result`, design D10), which accumulates its graph in
expansion rounds over every AgendaItem → Consultation → Paper. Expanding a
Consultation pulls in its Organisation — and all consultations of a session
share the same organisation, so the "Gemeinderat" node accumulates a
**149-edge hub** (11 Organisation nodes, 176 org edges in total). The
intended design stops at Organisation: traverse from File, AgendaItem,
Paper or Meeting; an Organisation is at most a leaf, never expanded
further, and certainly not a hub that drags the whole session graph into
one point of the force layout.

## What Changes

- The meeting-centric/multi-round graph accumulation SHALL stop at
  Organisation: no Organisation nodes and edges are added from expansion
  rounds (flag-controlled, so the capability is disabled — not dropped; a
  future change can enable it or add selective per-node expansion options).
  Expected default-query full graph: **436 nodes / 560 edges** (11 org
  nodes + 176 org edges removed), no hub.
- **Graph scope selection**: the graph stage SHALL compute two scopes per
  session — `documents` (the traversal seeded by the top_k answer
  documents only: ~64 nodes / ~72 edges for the default query) and `full`
  (the complete result-list traversal incl. agenda-item name-seed blocks).
  `/graph` accepts a `scope` parameter, **defaulting to `documents`**, and
  the network view gets a toggle ("nur Treffer-Dokumente" vs "gesamtes
  Ergebnis") — default documents-only, matching the user's top_k mental
  model.
- Node expandability becomes an explicit, per-type, backend-owned property
  derived from the graph model: Organisation is marked NOT expandable
  (disabled), keeping the capability in place.
- `/expand` on a not-expandable node type returns a clear structured
  response (not a 404 crash path).
- The graph payload carries the expandable node types so the frontend
  derives button state from the same source of truth (no drift).
- The network view's detail pane disables the "Nachbarn laden" button
  for not-expandable types (with a hint) instead of offering an action
  that fails.
- Verification: the default-query graph is compared before/after —
  447/736 → 436/560, hub gone; single-step `/expand` of a Consultation
  keeps its Organisation leaf (a user action on one node is informative,
  the hub only arises from accumulating many consultations).

## Capabilities

### Modified Capabilities

- `network-view` — two new/changed requirements: (1) expansion control —
  the accumulated graph SHALL stop at Organisation (no org nodes/edges
  from expansion rounds, flag-controlled); expansion of a not-expandable
  node type SHALL be a graceful defined outcome; expandability SHALL be
  carried with the graph payload as a single source of truth.
  (2) graph scope selection — the graph SHALL be available in a
  `documents` scope (top_k answer documents only, the default) and a
  `full` scope (complete result-list traversal), selectable via API
  parameter and a UI toggle.

## Impact

- `src/pgIntentRouter.py` — `meeting_scope_result` expansion rounds skip
  Organisation nodes/edges (flag from the graph model).
- `src/pgTimeline.py` — graph/timeline stage computes both scopes (plain
  file-seeded traversal + full seed-block traversal) once per session.
- `src/graphModel.py` — explicit expandability registry next to
  `ADJACENCY`; `expand_neighbors` returns a graceful not-expandable
  response instead of raising.
- `src/apiServer.py` — `/graph` accepts `scope` (default `documents`) and
  graph payloads gain `expandable_types`; `/expand` contract for
  not-expandable nodes.
- `app/src/components/NetworkView.vue` (+ `WorkPage.vue` wiring) — scope
  toggle (default: Treffer-Dokumente); DetailPanel disables the
  "Nachbarn laden" control for not-expandable types.
- `src/tests/` — unit tests (scope computation, skip + graceful response +
  payload field); the default-query comparison as an integration check.
