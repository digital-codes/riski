# Proposal: request-thread-facets

## Why

Follow-up semantics are still framed in KG terms ("kg thread"), but a thread
follow-up has NOTHING to do with the knowledge graph: it is the amendment of a
REQUEST. The pipeline starts with a topic (the request's answer selected
documents); a follow-up request relates to that same topic — a different facet
of it — so the original query is AMENDED with the new query text, and the
answer set should be carried forward: keep the best of previously selected
documents and let the new search add to them.

The second half of the concept: OPTIONS are the backend's tool when it cannot
decide what the user is aiming at. Example: "wann war die letzte sitzung" is a
clear ask_gremium_recent request, but the BODY is not determinable — and the
system KNOWS all possible bodies (a small, well-defined search space), so it
presents them as selectable options instead of guessing. Options are the right
tool when the residual search space is well defined and small.

Wording (established rule): REQUEST = user input into intent routing; SEARCH =
the database activity. The thread is the REQUEST CONTEXT (Anfrageverlauf) — the
"kg thread" naming misleads and gets relabelled.

## What Changes

- **Terminology relabel** (docs + user-facing copy; code module names stay):
  "KG thread" → request context / Anfrageverlauf; chips → options; followup →
  follow-up request (facet amendment). `docs/kg-thread-state.md` moves to
  `docs/request-thread.md` with current wording.
- **Facet-amendment carry-over**: on a classified FOLLOW-UP request, the prior
  request's `top_docs` travel in the sealed context (already stored!) and the
  answer set becomes: new search hits (ranked) + previously selected documents
  not displaced by the new search (marked "via: aus Ihrer vorherigen Anfrage").
  The user sees continuity instead of a topic jump.
- **Slot-filling options for underspecified requests**: when intent routing
  decodes a clear intent but a required slot cannot be resolved uniquely, the
  backend answers with a structured OPTIONS payload (facet kind, e.g. gremium
  bodies list; cells: topic label + example) instead of running an unscoped /
  guessed search. The user selects; the selection travels as an `option`
  (machinery exists: `_option_turn`) and fills the slot deterministically → the
  scoped search runs.
- Options decision rule: present options only when the residual space is
  enumerable AND small (bodies ≈ 30; a topic ambiguity with ≤ 5 candidates),
  otherwise the pipeline degrades as today (unscoped search / clarification).

## Capabilities

- **Modified Capabilities**: `intent-routing` — follow-up/facet-amendment
  semantics; slot-filling options payload for under-specification.

## Impact

- Code: `src/apiServer.py` (carry-over in the /ask follow-up branch; options
  payload + option fill for the gremium slot), `src/pgIntentRouter.py`
  (ambiguous-slot detection point), `app/src/components/RelatedHintsCard` /
  `WorkPage.vue` (option selection payload already implemented; labels).
  `docs/kg-thread-state.md` → `docs/request-thread.md` (+README link).
- No DB/schema changes; sealed-state already carries q0/turns/top_docs.
