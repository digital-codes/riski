# Design: request-thread-facets

## Context

The state machinery already exists (sealed q0 + turns + top_docs; `option`
selection transport via `_option_turn`), but its framing is KG-flavoured and
the follow-up semantics stop at query concatenation. The user's model:

- a request thread = Anfrageverlauf around ONE TOPIC; a follow-up request is a
  facet amendment of the first request;
- the answer set persists: best-of prior documents stay, new search adds;
- options exist to resolve UNDER-SPECIFICATION (not generic "did you mean" —
  only when the residual space is small and well defined), e.g. "wann war die
  letzte sitzung" → which body?

## Decisions

1. **Carry-over rule (facet amendment)**: in the /ask follow-up branch, the
   sealed context's `top_docs` are appended to `result["top_files"]` (new hits
   first, then carry-overs not already present, each marked `"via": "aus Ihrer
   vorherigen Anfrage"`); the summarizer already tracks per-file provenance so
   the map/timeline picking stays untouched. Cap: carry at most the top 5
   prior documents; carry-overs rank AFTER the new search hits. On an empty
   new search, the carry-overs alone prevent the "no answer" jump.
2. **Ambiguity options payload**: a new `_slot_options(turn/result)` step; the
   gremium slot's ambiguity sources: (a) no body decoded, (b) >1 body matches
   the gremium term within the ambiguity delta, (c) the generic "letzte
   sitzung" phrasing. Payload: `{"options": {"kind": "slot", "facet":
   "gremium", "options": [{topic: <body name>, example: <latest meeting date>
   }, …]}, "hint": "Wählen Sie das Gremium", "mode": "options"}` — rendered by
   the existing RelatedHintsCard/`_consumeThreadState` machinery, pick travels
   through `runSearch({option})` (already implemented).
3. **Option fill**: `_option_turn` gains slot semantics: for a
   `facet: gremium` option the backend resolves `resolve_gremium(term)` and
   the scoped search runs with `filters=[organization: <body>]` — the payload
   reused from the normal gremium path (documented "kind" switch; the generic
   facet-amendment path remains the default for topic options).
4. **Wording relabel**: `docs/kg-thread-state.md` → `docs/request-thread.md`;
   README/thread docs re-labelled (Request/Anfrageverlauf, options/Facetten);
   code identifiers stay (module `kgFollowups` et al. — cleanups scoped out).
5. **Options guard**: option lists capped at 12 entries (scrollable; primary bodies first); when the body list is
   longer, the payload degrades to the FAQ-style hint (no guessing).

## Risks / Trade-offs

- [Carry-over could keep stale documents relevant-looking] → marked "via" +
  capped at 5, excluded from timeline dedup? no — timeline dedup exists;
  carry-overs are normal answer members.
- [Options when intent confidence is actually low] → options only fire on
  DECISION + UNRESOLVABLE SLOT — never on weak recall (that stays the chips
  flow).

## Migration Plan

Backend payload additive (`mode: "options"`); UI reuses existing selection
machinery — no migration; rollback = revert.

## Open Questions

None for scope 1–3. (NER ingest-level PII remains its own change.)
