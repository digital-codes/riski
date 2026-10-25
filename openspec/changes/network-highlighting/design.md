# Design

## Context

`App.vue` holds all the state needed for marking: `summaryFiles` (the
document list, each with `excluded` flag), `summaryExclude` (the
authoritative exclusion set), the raw result's `summary_refused`, and
`topics` (each with `id` = `AgendaItem_<oparlKey>` and `oparlKey`). The
graph File nodes from `top_files` already carry `attrs.match` (used only
to keep them visible under relation filters). `NetworkView.vue` renders
ECharts graph series from `visibleNodes`; node styling happens per node
in `toOption()`.

## Goals / Non-Goals

**Goals:**
- Answer-list membership and rejection state visible directly in the
  graph, updating live with the user's toggles.
- Meeting-view topics marked in the graph.
- Fast-settling force layout for large graphs.

**Non-Goals:**
- No graph-data changes (server contract untouched).
- No new interaction (the marking is display-only; filtering stays the
  existing type/relation chips).
- No CSS-framework/refactor of NetworkView.

## Decisions

**D1 — Props over graph-data mutation.** `NetworkView` receives three
plain props (`activeFileKeys`, `rejectedFileKeys`, `activeItemKeys`;
arrays of oparlKeys) and derives sets internally. Rationale: the graph
object is merge-by-id state (kept across /expand); decorating it with
session state would need cleanup on every re-render and duplicates state
that already lives in `App.vue`. Props keep the graph contract untouched
and make the marking reactive for free (the `watch(() => props.graph)`
already re-renders; prop changes re-trigger via the same deep watch plus
Vue's reactivity on computed sets).

**D2 — Visual language.**
- *Enabled list documents / listed topics*: 2.5 px highlight ring
  (`itemStyle.borderColor: #667eea`, `borderWidth: 2.5`) + a tooltip
  prefix. One accent color for "this is part of the answer list" — the
  existing primary (`#667eea`), no new palette entries.
- *Rejected documents (excluded or refused)*: `opacity: 0.22` +
  dashed `#dc2626` border + tooltip suffix "— deaktiviert"/"— nicht
  relevant". Dimming (not hiding) preserves the graph topology context
  while making the rejection unmistakable. Hiding rejected nodes was
  rejected: the user asked for *distinguishable*, not filtered (and the
  type/relation chips already provide filtering).
- *Everything else*: unchanged.

**D3 — Force layout tuning (empirical, node-count aware).**
- `gravity: 0.25` (was 0.12) — stronger pull to the viewport center.
- `friction: 0.35` — ECharts' damping factor; larger values settle the
  simulation markedly faster.
- `repulsion: 320` for small graphs, scaled up mildly with node count
  (`320 + min(400, n * 2)`) so denser graphs don't clump, without the
  explosive spread of a fixed large value.
- `layoutAnimation: false` above 120 nodes — large graphs compute the
  layout synchronously (a short block instead of seconds of visible
  wobbling); below the threshold the animation stays for small,
  self-explanatory graphs.

**D4 — Sets derived from existing state in `App.vue`.**
- `activeFileKeys = summaryFiles where !excluded → oparlKey`
- `rejectedFileKeys = summaryExclude ∪ summary_refused.oparlKey`
- `activeItemKeys = topics.map(t => t.oparlKey)`
- Meeting view: `summaryFiles` is empty by design — only the topic marking
  applies (D2's ring on AgendaItem nodes).

## Risks / Trade-offs

- [Regex... none] — display-only change.
- [Marking can go stale if the user excludes before the first summary
  arrives] → the sets are computed from live refs; the summary round-trip
  updates them when it lands (existing behavior).
- [friction/gravity values are empirical] → verified visually against the
  default query (≈100 nodes) and a full-meeting query (≈200+ nodes);
  single constants, easy to retune.

## Migration Plan

1. `NetworkView.vue`: props + node styling in `toOption()` + force params.
2. `App.vue`: computed sets passed to NetworkView.
3. `npm run build` + visual verification (topical + meeting query).

Rollback: revert the commit.

## Open Questions

(none)
