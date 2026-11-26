# Tasks: rework-search-result-cards

## 1. Backend: topical flag

- [x] 1.1 `/search` stage-1 payload: set `result["topical_summary"] = topic_focus_for_query(query) is not None` (additive key; /ask keeps its own flow)
- [x] 1.2 Unit test: /search response contract carries the flag (true above the topic threshold, false absent/weak)

## 2. Frontend: card architecture

- [x] 2.1 New `app/src/components/RelatedHintsCard.vue`: styled card hosting the kg chips (refinement options) and related documents (markup lifted from SummaryCard.vue events untouched)
- [x] 2.2 `SummaryCard.vue`: remove the embedded kg-selection/kg-related sections and the `kgChips`/`kgRelated` props; keep refine/refusal flows
- [x] 2.3 `TimeLine.vue`: add `showFiles` prop (default true); hide the `files-card` section when false
- [x] 2.4 `WorkPage.vue` (`search_topic` view): new card order — SummaryCard → RelatedHintsCard (only when `!topicalSummary && (kgChips || relatedDocs)`) → GeoMap → TimeLine (`show-files=false`) → NetworkView; remove the bare RelatedDocsList wrapper; wire `topicalSummary` from `result.topical_summary` (reset on new search)

## 3. Verification

 - [x] 3.1 Frontend test/build: `npm run build` green; visual check query "Bürgerbeteiligungsplattform" (no topic focus → related-hints card with chips) and a topical query (e.g. "Beteiligungsportal der Stadt Karlsruhe" focus → no related-hints card)
- [x] 3.2 Component verification: the app has no frontend test framework (no vitest/test-utils in package.json); adding one for a single component test is out of scope — verified via `vite build` compile + template/prop binding review instead; adjust if a vitest setup lands later
 - [x] 3.3 API doc sync: README search API section documents the additive `topical_summary` key; design/specs consistent

## Workflow follow-up

- After implementation, run `/opsx-verify` then archive with `/opsx-archive`.
- Follow-up change (separate proposal): context/history rework for thread + chip refinement ("not properly working at the moment"), remaining intents/locations view fixes.
