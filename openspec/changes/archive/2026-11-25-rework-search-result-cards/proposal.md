# Proposal: rework-search-result-cards

## Why

The `search_topic` result view (WorkPage.vue) renders a confusing, unstyled sequence: network graph → summary card → unstyled tags/related-documents paragraph → map → top-10-files+timeline card → timeline. Users get duplicate content (files twice: inside the timeline card and again as related docs), context visually detached, and the refinement hints (kg chips) are buried inside the summary card where they look like document list content instead of the interaction options they are.

## What Changes

- **Result card order for `search_topic`** becomes: summary card → map (if geo present) → timeline card → network graph (moved from first position).
- **Drop** the top-10-files card (the file list section inside the TimeLine card / its files-only rendering).
- **Drop** the unstyled tags + related-documents paragraph block (`RelatedDocsList` as a bare wrapper section).
- **Extract** the summary card's inner "related" section (kg chips + related documents) into a **separate, styled card** that follows the summary card.
- **Conditional display rule**: the separate related-hints card is shown ONLY when the result did NOT find a kg topic with a sufficiently high score to enable a topical summary (`topic_focus_for_query` below its threshold). It contains the refinement chips (user hint options to refine the query) and the related documents — prep work for the context/history feature (tracked as a follow-up change).
- Other intents (ask_*, gremium, location) are out of scope; their views are handled in a follow-up change.

## Capabilities

- **New Capabilities**: none
- **Modified Capabilities**:
  - `staged-results` — search_topic stage-1 view contract: new card order, dropped file-card, extracted related-hints card with topical-summary condition.

## Impact




- Code: `app/src/components/WorkPage.vue` (card order, drops), `app/src/components/RelatedDocsList.vue` + new `RelatedHintsCard.vue` (or restructure SummaryCard's kg-section out), `app/src/components/SummaryCard.vue` (remove inner kg chips/related sections).
- Frontend store/logic: `WorkPage.vue` needs the topic-focus flag to decide chip-card visibility (comes from the intent router/result snapshot — code-side: pass `topical_summary` boolean with the stage-1 payload or derive from the summary request).
- No API shape changes; `topical_summary` flag may be added to the session/summary state (additive).
- Follow-up change (explicitly out of scope here): context/history feature for thread Tenor + chip-refinement ("context/history is not properly working at the moment").
