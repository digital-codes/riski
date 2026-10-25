# Tasks

## 1. NetworkView marking + physics

- [x] 1.1 Props `activeFileKeys`/`rejectedFileKeys`/`activeItemKeys` (arrays, default []), internal Set derivation; File nodes in `activeFileKeys` get the highlight ring (#667eea, 2.5 px) + tooltip prefix "Trefferliste"; AgendaItem nodes in `activeItemKeys` the same ring + tooltip prefix "Themenliste".
- [x] 1.2 File nodes in `rejectedFileKeys` get dimmed dashed-red style (opacity 0.22, borderType dashed, #dc2626) + tooltip suffix "— deaktiviert" (excluded) / "— nicht relevant" (refused); rejection precedence over active marking.
- [x] 1.3 Force layout: gravity 0.25, friction 0.35, node-count-scaled repulsion (320 + min(400, n*2)), `layoutAnimation: false` above 120 nodes.

## 2. App.vue wiring

- [x] 2.1 Computed sets: `activeFileKeys` (summaryFiles minus excluded), `rejectedFileKeys` (summaryExclude ∪ result.summary_refused), `activeItemKeys` (topics.oparlKey); passed as props.
- [x] 2.2 Filter-chip review (ops): the type chip row was **dead UI** (`enabledTypes` was never applied to the node list) and duplicated the ECharts canvas legend (which natively toggles category visibility with the same palette) → removed. Relation ("Kanten") chips kept — they genuinely filter `visibleEdges` and ECharts has no native edge-type legend. Colors single-sourced via `categories`.

## 3. Verification

- [x] 3.1 `npm run build` green; visual check: default topical query (enabled vs disabled vs refused docs in the network), a meeting query (topics marked, large graph settles fast).
- [x] 3.2 `openspec validate --changes` passes.
