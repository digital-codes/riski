# Design: rework-search-result-cards

## Context

`WorkPage.vue` composes the `search_topic` result view from async stage cards
whose mount points are ordered: NetworkView → (TopicList | SummaryCard with
embedded kg-section + FollowupChips + RelatedDocsList) → GeoMap → TimeLine
(files-list section + timeline). The goal is the card order summary → related
hints → overview → timeline → network­graph and the extraction/drops listed in
the proposal.

Server side: the topical condition is computed in
`topic_focus_for_query(query)` (kgQueries, threshold 0.30) inside
`_prepare_thread_turn`, but is currently not exposed to the client. The
followups/chips path (`_kg_enrich` → `result.clarification`,
`related_documents`, kg topic boosts) stays untouched.

## Goals / Non-Goals

**Goals**
- Card order contract implementation for `search_topic` only.
- Drop top-10-files card and the unstyled related-docs paragraph.
- Extract chips + related documents into one styled card, displayed only
  without topic focus.
- Prepare the flag plumbing for the later context/history change.

**Non-Goals**
- No changes to `ask_*`, gremium, location views (follow-up change).
- No rework of the thread/context/history logic ("not properly working at the
  moment" — user explicitly deferred).
- No API contract change beyond an additive boolean.

## Decisions

1. **`topical_summary` flag from the /search stage-1 payload**
   `_prepare_thread_turn`/`_kg_enrich`-untouched: `/search` sets
   `result["topical_summary"] = topic_focus_for_query(query) is not None`
   (reuses the existing call context; threshold stays in kgQueries). The UI
   reads `result.topical_summary` (default false) into a
   `topicalSummary` ref. Additive key — backwards compatible.
   *Alternative*: let the UI call a new endpoint — rejected; the decision is
   cheap and already available in the /search context.

2. **New component `RelatedHintsCard.vue`** hosting the former
   SummaryCard kg-section (chips + related docs) with its own card styling.
   SummaryCard loses the kg props/events entirely; WorkPage passes the kg
   chips/related to the new card. `FollowupChips` (generated follow-up
   questions) stay associated with the summary flow — rendered under the
   related hints card, outside it; moving them in this change would blur the
   context/history rework boundary.
   *Alternative*: keep chips inside SummaryCard and only restyle — rejected;
   the card must be an independent, clearly separated interaction surface.

3. **Drops via WorkPage only**: the top-10-files card disappears by not
   passing the files rendering into the TimeLine card — keep `TimeLine.vue`'s
   `files`/`filesLoading` props (other views e.g. location may still use
   them) and instead render the TimeLine card with a new `files-card-off`
   flag? Simpler: add a `showFiles` prop (default true) in TimeLine.vue so
   `search_topic` turns the files-section off, other intents keep the
   behaviour. The unstyled tags/related-docs paragraph is simply unmounted
   (wrapper `RelatedDocsList` without card removed from WorkPage).

4. **Card order**: HTML order in WorkPage becomes SummaryCard(+RelatedHints)
   wrapper → GeoMap wrapper → TimeLine wrapper → NetworkView wrapper. TopicList
   (ask_gremium-style view) keeps its current branch (topics replace summary,
   not part of `search_topic`). Progressive rendering stays: wrappers show
   loading cards until stages arrive.

## Risks / Trade-offs

- [The related-hints card changes interaction flow for queries without topic
  focus — picking a chip for refinement now happens below the summary instead
  of inside it] → behaviour (issued query) unchanged; only location/styling
  changes; chip pick events keep their handlers.
- [`showFiles` prop leaves dead code path] → default-on keeps other intents
  identical; removal later needs a separate decision.

## Migration Plan

Pure frontend change plus an additive backend flag — no migration. Rollback =
revert the commit (no data/DB changes).

## Open Questions

None. (Follow-up change planned: context/history rework — chips/thread logic.)
