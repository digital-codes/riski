# Sync documentation with recent changes

## Why

Three changes archived on 2026-10-30/31 (`fix-result-summarizer`,
`disable-organisation-expansion`,
`sanitize-queries-and-initial-response`) changed user-visible behaviour
that README.md and API.md still describe differently — and one README
claim was already stale before them. A docs audit found:

1. **README "Refine and per-file control"** — says refinement re-runs the
   summarizer with the "full document content". Since `fix-result-summarizer`
   the refinement reads the query-matched CHUNK (selected via the search
   phase's chunk index), with teaser/content fallbacks; teaser generation
   itself is now chunk-aware (one true, document-wide teaser via
   map-reduce, length ceiling 120% of a chunk).
2. **README web-app section** — "Nachbarn laden expands a node's
   depth-1 neighborhood" without the two additions from
   `disable-organisation-expansion`: Organisation nodes are NOT
   expandable (the traversal stops at Organisation), and the network view
   has a graph scope toggle ("Treffer-Dokumente" default vs "gesamtes
   Ergebnis").
3. **README + API.md** — no mention of the query sanitation
   (allowed characters, 250-char cap, HTTP 400 with German messages on
   `/search` and `/ask`) from `sanitize-queries-and-initial-response`.
4. **README usage block (line ~93)** — claims `python src/pgTimeline.py`
   "saves to app/src/assets/sampleData.json". That is stale: the snapshot
   is now written by `scripts/capture_initial_response.py`, and the
   frontend uses it as the canned landing view (no backend retrieval for
   the default query) plus offline fallback.
5. **API.md** — `/graph` is documented without the `scope` parameter
   (`documents` default / `full`) and without `expandable_types` in the
   response; `/expand` without the graceful not-expandable outcome.
6. **README "Recently implemented" list** — ends at 2026-10-27.

## What Changes

- README.md updates for all six points above (web-app section, summaries
  section, usage block, map/expand notes where affected, "Recently
  implemented" list).
- API.md updates: `/search` + `/ask` sanitation note (400), `/graph`
  scope parameter + `expandable_types`, `/expand` graceful outcome,
  `/summarize` refine-context note.
- No code changes; no spec deltas (documentation only, `skip_specs: true`).

## Capabilities

No capabilities created or modified — documentation-only change
(`skip_specs: true` in the change's `.openspec.yaml`).

## Impact

- `README.md`, `API.md` — text only.
- No runtime, API, or test changes.
