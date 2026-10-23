# Tasks: add-network-view

> Ordering note: tasks 1.x (contract + serialization) can start immediately.
> Frontend tasks (3.x) can start in parallel against mock data. Enrichment
> tasks (4.x) depend on the categorization & indexing change.

## 1. Backend: graph serialization

- [x] 1.1 Define the adjacency map (association tables + direct FKs) as a declarative constant in `src/pgTimeline.py` (or a new `src/graphModel.py`), derived from `references/postgres/riski-struct.sql`
- [x] 1.2 Extend `find_related_objects` to log typed edges (`source`, `target`, `relation`) during the existing traversal, including direct FKs (`File__paper`, `File__meeting`, `AgendaItem.meetingSid/consultationSid`)
- [x] 1.3 Implement `graph` serialization ({nodes, edges} per contract in design.md) into the `search_and_build_timeline` result
- [x] 1.4 Add unit tests: graph nodes cover all traversed objects, edge relations match association tables, node ids are stable (`{Type}_{oparlKey}`)
- [x] 1.5 Regenerate `app/src/assets/sampleData.json` including the `graph` section  *(regenerated with graph + facets + matched_entities; offline fallback asset)*

## 2. Frontend: component scaffolding

- [x] 2.1 Add `echarts` dependency to `app/package.json`; confirm tree-shaken import of `GraphChart` only
- [x] 2.2 Create `NetworkView.vue`: card wrapper consistent with existing cards, reactive `{nodes, edges}` state, ECharts init/dispose on mount/unmount, ResizeObserver
- [x] 2.3 Map contract to ECharts: categories per node type (legend + colors), node label = name (truncated), tooltip fallback
- [x] 2.4 Force layout tuning: repulsion, edge length, gravity — must be readable at ~50–300 nodes

## 3. Frontend: interaction

- [x] 3.1 Click handling: select node → emit to parent → DetailPanel shows type, name, date, OParl deep-link, PDF download (File/AuxFile), related entities list
- [x] 3.2 Create `DetailPanel.vue`: side pane on desktop (right), bottom sheet on mobile (≤768px), closable, consistent with `isMobile` pattern in `TimeLine.vue`
- [x] 3.3 Edge/relation filter UI: checkboxes per `relation` type, applied as graph display filter (data stays intact)
- [x] 3.4 Node-type filter + date-color gradient with time-range filter
- [x] 3.5 Dynamic updates: watch-driven merge-by-id diff → `setOption` update (not replace); existing node positions preserved when data grows  *(App.vue merges /expand responses by id; NetworkView deep-watch re-renders)*

## 4. Enrichment (depends on categorization & indexing change)

- [x] 4.1 Include category/papertype/district tags as node `attrs`; use for filter facets and node styling  *(paperType/reference/number/result/role/classification attrs live; full tag-scheme attrs tracked as future work)*
- [x] 4.2 Extend traversal to Person/Membership (originator*, membership) as new node/edge types  *(DESCOPED — see proposal.md future work; harvest spike showed originator fields unpopulated)*
- [x] 4.3 Semantic-similarity edges within the answer set (contentEmbeddings pairwise cosine below threshold) as `relation: "semanticSimilarity"` with `attrs.distance`  *(DESCOPED — see proposal.md future work)*
- [x] 4.4 graphGL 3D renderer behind a toggle (time as z / color), only if 2D UX proves insufficient  *(DESCOPED — 2D UX validated in practice)*
- [x] 4.5 API server (`/search`, `/expand`) with merge-friendly expand responses  *(delivered by the api-search-expand change, archived 2026-10-23)*
