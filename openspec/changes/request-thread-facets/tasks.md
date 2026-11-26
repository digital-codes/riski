# Tasks: request-thread-facets

## 1. Wording relabel

- [x] 1.1 `docs/kg-thread-state.md` → `docs/request-thread.md` (current wording: request context/Anfrageverlauf, follow-up = facet amendment, options = slot filling; KG references only where the KG is genuinely involved) + README link update
- [x] 1.2 User-facing copy: hint texts "Verfeinerung" phrasing checks (RelatedHintsCard/FollowupChips wording consistent with request/options terms)

## 2. Facet-amendment carry-over

- [x] 2.1 `/ask` follow-up branch: append the sealed context's `top_docs` (≤ 5, `via: "aus Ihrer vorherigen Anfrage"`) after the new search hits, dedup by oparlKey
- [x] 2.2 Empty-new-search case: carry-overs alone remain the answer set
- [x] 2.3 Unit tests: carry-over ordering + via marker + dedup; empty-new-search behaviour

## 3. Slot-filling options

- [x] 3.1 Ambiguity detection: ask_gremium_recent with no/ambiguous body → options payload `{mode: "options", options: {facet: "gremium", entries: [{topic, example}]}}` (≤ 8 bodies)
- [x] 3.2 `_option_turn` slot path: a `facet: gremium` option selection → resolve_gremium(term) → scoped request with the organization filter (no query concat)
- [x] 3.3 UI: options payload renders via RelatedHintsCard (existing machinery); selection populates runSearch({option}) — llint check/does not regress
- [x] 3.4 Unit/integration tests: "wann war die letzte sitzung" yields options (bodies list); selecting one scopes to the body's latest held meeting

## 4. Docs (mandatory)

- [x] 4.1 README: request-thread/facet/options section updated (wording + carry-over + options rule)
- [x] 4.2 `docs/request-thread.md`: current behaviour incl. the option machinery sequence

## Workflow follow-up

- `/opsx-verify` then `/opsx-archive` after apply.
