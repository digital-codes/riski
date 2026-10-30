# Tasks: disable-organisation-expansion

## 1. Graph model: registries

- [x] 1.1 Add `EXPANSION_SKIP_TYPES = {"Organization"}` and `EXPANSION_DISABLED = {"Organization"}` plus `expandable_types()` next to `ADJACENCY` (src/graphModel.py) — the single source of truth for accumulation skip and UI/API expandability
- [x] 1.2 Add a partial-graph filter helper (drop nodes of skipped types and all edges touching them) used by the accumulation path

## 2. Meeting-centric accumulation stops at Organisation

- [x] 2.1 `meeting_scope_result` (src/pgIntentRouter.py): filter every `expand_neighbors` partial through the skip helper before merging (initial meeting expansion and all AgendaItem/Consultation/Paper rounds)
- [x] 2.2 Unit test: accumulated meeting-centric graph contains no Organisation nodes and no edges touching them; consultations' other neighbours (meeting/paper/agenda item) survive; flipping the registry re-includes orgs

## 3. API contract

- [x] 3.1 `expand_neighbors`: return `{"nodes": [], "edges": [], "expandable": False}` for a not-expandable node type instead of raising; unknown node ids keep raising (404)
- [x] 3.2 Graph payloads (search/ask graph stage, /graph, meeting-centric result): include `expandable_types` from the registry
- [x] 3.3 Unit tests: `/expand` on an Organisation id returns the graceful not-expandable outcome; `/expand` on Meeting/Consultation unchanged; graph payloads carry `expandable_types`

## 4. Frontend

- [x] 4.1 DetailPanel: disable the "Nachbarn laden" button for node types not in `expandable_types`, with a hint (e.g. "Organisation wird nicht weiter expandiert"); WorkPage wires the flag through; keep the defensive failure path

## 5. Graph scope selection

- [x] 5.1 Graph stage (src/pgTimeline.py): compute both scopes once per session — `documents` (traversal without agenda-item name seeds) and `full` (current behaviour) — and store both in the session stage
- [x] 5.2 `/graph` (src/apiServer.py): accept `scope: "documents" | "full"` (default `documents`), serve the stored scope without re-traversal
- [x] 5.3 WorkPage/NetworkView: scope toggle ("Treffer-Dokumente" default / "Gesamtes Ergebnis"), re-fetch with the selected scope, existing merge/reset semantics on switch
- [x] 5.4 Unit tests: `/graph` default scope is documents; both scopes served from one stage run; documents scope contains no seed-block-only nodes (e.g. agenda items of meetings not touched by top_k files)

## 6. Verification

- [x] 6.1 Run the graph test modules: `python3 -m pytest src/tests/test_pgGraph.py src/tests/test_unit_graphModel.py -q` (or existing equivalents) — all pass
- [x] 6.2 Default-query comparison (baselines in proposal.md): full scope 436 nodes / 560 edges (was 447/736), no Organisation nodes/edges, "Gemeinderat" hub gone; documents scope (new default) ~64 nodes / ~72 edges; plain traversal baseline unchanged; single-step expand behaviour unchanged — document the numbers in the task result
- [x] 6.3 Frontend build check (`npm run build` in app/) passes
