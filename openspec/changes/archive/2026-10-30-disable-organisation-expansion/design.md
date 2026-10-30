# Design: disable-organisation-expansion

## Context

- The default query routes to the meeting-centric gremium answer
  (`meeting_scope_result`, src/pgIntentRouter.py, design D10): it expands
  the resolved Meeting (depth 1), then accumulates rounds over EVERY
  AgendaItem → Consultation → Paper (`expand_neighbors` per node, merged
  via `_merge_graph_partials`).
- `ADJACENCY["Consultation"]` includes `organization` → every Consultation
  expansion adds its Organisation; all consultations of a session share
  the same organisation → the "Gemeinderat" node becomes a hub.
- Measured, default query ("wo liegt die Governance für Digitalisierung
  bei der Stadt Karlsruhe"): **447 nodes / 736 edges** — AgendaItem 170,
  Consultation 169, Meeting 48, AuxFile 32, Organization 11, File 10,
  Paper 7; `Organization_32130` (Gemeinderat) carries **149 edges**
  (169 `organization` + 7 `underDirectionOf` edges total). Excluding
  Organisation nodes/edges: **436 nodes / 560 edges**.
- Plain file-seeded traversal for comparison: 64 nodes / 72 edges (7
  Organisation leaves) — the hub is an accumulation artifact of the
  multi-round flow, not of the adjacency map.
- `ADJACENCY["Organization"] = []` has always been the case: Organisations
  are never expanded FROM. `/expand` on an Organisation raises
  `ValueError` → 404; the detail pane still offers the button.

## Goals / Non-Goals

Goals:

- Stop the meeting-centric accumulation at Organisation: no org nodes and
  no org edges from the expansion rounds — no hub.
- Make "stop at Organisation" explicit and flag-controlled (disabled, not
  dropped): a registry next to `ADJACENCY`, re-enabling = one-line change;
  future selective per-node expansion can build on it.
- Graceful `/expand` outcome for not-expandable types + `expandable_types`
  in graph payloads + frontend button state from the same source.

Non-Goals:

- No removal of the Organisation adjacency concept or of org leaves in
  single-step user expansions (a user expanding one Consultation keeps its
  org leaf).
- No trimming of the other complexity drivers (339 meeting edges, 170
  agenda items) — separate concern.
- No implementation of Organisation adjacency (sub-organisations,
  memberships/Person).

## Decisions

### D1: Skip in the accumulation, driven by a graph-model registry

`meeting_scope_result`'s rounds filter each `expand_neighbors` partial
through a graph-model-owned registry, e.g.
`EXPANSION_SKIP_TYPES: {"Organization"}` in src/graphModel.py: nodes of a
skipped type and all edges touching them are removed before merging.
Re-enabling or making it selective later = registry change only.

- Alternative: filter inside `expand_neighbors` — rejected: the single-step
  user expansion of a Consultation legitimately keeps its org leaf (spec:
  informative, no hub from one node); the hub is an accumulation effect.
- Alternative: hardcode the skip in pgIntentRouter — rejected: the
  traversal vocabulary lives in graphModel; the registry belongs there.

### D2: Expandability registry beside `ADJACENCY`

`expandable_types()` derives from `ADJACENCY` minus
`EXPANSION_DISABLED = {"Organization"}`. `/expand` on a not-expandable type
returns `{"nodes": [], "edges": [], "expandable": False}` instead of
raising (unknown node ids still 404). Graph payloads carry
`"expandable_types": [...]` (additive field).

- Alternative: 422 error for disabled types — rejected: a defined 2xx
  outcome keeps client merge logic uniform.

### D3: Frontend derives button state from the payload

DetailPanel disables "Nachbarn laden" with a hint (e.g. "Organisation wird
nicht weiter expandiert") when the node type is not in the payload's
`expandable_types`; the defensive failure path for unexpected errors
remains.

### D4: Two scopes computed once per session, served by parameter

The graph stage (src/pgTimeline.py `timeline_stage`/`graph_stage`) runs the
traversal twice in one pass: WITHOUT agenda-item name seeds (`documents`
scope: seeds = top_files only) and WITH them (`full` scope) — both stored
in `sess["_stage2"]`. `/graph` gains `scope: "documents" | "full"`
(default `documents`) and serves the stored graph without re-traversal.
The frontend's scope toggle re-requests with the other scope; the existing
merge-by-id update semantics apply (toggle = replace with the selected
scope's base, consistent with the existing "reset" anchor behaviour).

- Alternative: provenance tags on nodes + client-side filtering — rejected:
  "related to top_k documents" is a traversal property, not a node
  attribute (meeting-edge BFS from the files would re-include whole
  sessions); two explicit traversals are simpler and honest.
- Alternative: compute the documents scope on demand — rejected: it is
  cheap, and precomputing keeps scope switches instant.
- The organisation skip (D1) applies to the FULL scope's accumulation and
  the meeting-centric rounds; the documents scope keeps Organisation
  leaves (7 orgs / 15 edges for the default query — genuinely related to
  the top_k documents, no hub at that scale).

### D5: Verification = before/after numbers on the default query

Documented targets: full scope 447/736 → **436/560** (org hub gone);
documents scope (new default) **~64/72**; `Organization_32130` absent from
the accumulated graph. Structural assertions in tests (no org nodes/edges
in accumulated graphs; skip honours the registry; documents scope contains
no seed-block-only nodes) — absolute numbers live in the task result, not
hardcoded in tests (DB content evolves).

## Risks / Trade-offs

- [Org context lost in meeting-centric answers] → org names remain visible
  via meeting/consultation context; the payload field keeps the door open
  for opt-in org display (e.g. node limit or per-user toggle later).
- [Users may expect Organisation expansion] → the disabled control carries
  an explanatory hint; re-enabling is a registry change.
- [Other complexity drivers remain (48 meetings, 339 meeting edges)] →
  explicit non-goal; separate change if still too dense after this fix.

## Migration Plan

Deploy backend + frontend together; the payload field is additive and the
frontend falls back to "expandable" when absent (staggered rollout degrades
to today's behaviour, not to errors). Rollback = revert.

## Open Questions

None.
