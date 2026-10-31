# Tasks: docs-sync-recent-changes

## 1. README.md

- [x] 1.1 Usage block: replace the stale "python src/pgTimeline.py … saves to app/src/assets/sampleData.json" claim — the snapshot for the frontend's canned landing view is written by `scripts/capture_initial_response.py` (re-run when the default query or the pipeline contract changes)
- [x] 1.2 Web-app section ("Interactive search"): describe the network view additions — Organisation nodes are leaf nodes (no "Nachbarn laden"; the graph stops at Organisation) and the scope toggle (default: nodes around the top_k answer documents; opt-in: full result list)
- [x] 1.3 Web-app section: note the query sanitation (letters incl. umlauts, digits, punctuation; max 250 chars; 400 with German message on /search and /ask) and the canned landing view for the default query (snapshot file, no backend retrieval; offline fallback)
- [x] 1.4 "Refine and per-file control": refinement reads the query-matched chunk per file (chunk index from the search phase; teaser/content fallback) instead of the full content; mention the chunk-aware map-reduce teaser (one document-wide teaser, ≤120% of a chunk) where teasers are described
- [x] 1.5 "Recently implemented": add a 2026-10-30/31 entry summarizing the three archived changes (fix-result-summarizer, disable-organisation-expansion, sanitize-queries-and-initial-response)

## 2. API.md

- [x] 2.1 `/search` + `/ask`: document the sanitation (400 + German message; examples of rejected input)
- [x] 2.2 `/graph`: document `scope: "documents" | "full"` (default documents) and `expandable_types` in the response
- [x] 2.3 `/expand`: document the graceful `{"expandable": false}` outcome for not-expandable node types
- [x] 2.4 `/summarize`: one-line note that `refine: true` reads the query-matched chunk per file

## 3. Verification

- [x] 3.1 Cross-check every edited claim against the code (grep the referenced constants/fields: MAX_QUERY_CHARS, EXPANSION_DISABLED, scope default in /graph, filter_skip_types usage, sampleData.json fields)
- [x] 3.2 Spell/consistency pass over the edited sections (English prose, German UI terms in quotes)
