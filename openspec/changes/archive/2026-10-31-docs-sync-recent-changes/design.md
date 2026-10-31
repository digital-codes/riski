# Design: docs-sync-recent-changes

## Context

The docs audit (see proposal) compared README.md and API.md against the
three changes archived 2026-10-30/31 plus the code state
(`src/pgResultSummarizer.py`, `src/graphModel.py`, `src/apiServer.py`,
`src/pgTeasers.py`, `scripts/capture_initial_response.py`,
`app/src/components/WorkPage.vue`, `app/src/components/NetworkView.vue`).

## Goals / Non-Goals

Goals:

- README.md and API.md describe the CURRENT behaviour of the three
  archived changes; remove the one stale usage claim.
- Keep the docs' existing structure, tone (English technical prose,
  German UI terms) and change-reference style ("change: …").

Non-Goals:

- No rewriting of the README's architecture, setup, or workflow sections
  beyond the audited points.
- No new documentation files (the openspec specs remain the behavioural
  source of truth; docs/ is untouched).
- No translation of the docs to German.

## Decisions

### D1: Edit in place, minimal diff

Update the affected paragraphs/sentences only; keep section order. The
"Recently implemented" list gains ONE new entry (2026-10-30/31) summarizing
the three archived changes instead of three separate entries.

### D2: Refine wording — "matched chunk", not "full content"

The refine section says the summarizer re-runs with the query-matched
chunk per file (selected via the search phase's chunk index; teaser/
content fallback for files without a chunk signal), keeping the prompt
fast and relevant. The teaser paragraph gains one sentence on the
chunk-aware map-reduce teaser (one teaser per document, ≤120% of a
chunk).

### D3: Network view wording — scope toggle + organisation boundary

The web-app paragraph states: "Nachbarn laden" works for File, AgendaItem,
Paper, Meeting and Consultation; Organisation nodes are leaf nodes (the
graph stops at Organisation); the toggle switches between the
documents scope (default — nodes around the top_k answer documents) and
the full result-list traversal.

### D4: API.md — contract-accurate endpoint docs

`/search` + `/ask`: note the sanitation and the 400 response.
`/graph`: document `scope` (default `documents`) and `expandable_types`.
`/expand`: document the `{"expandable": false}` outcome for disabled
types. `/summarize`: one-line note that refine reads the matched chunk.

## Risks / Trade-offs

- [Docs drift again after future changes] → mitigated by the openspec
  workflow itself (specs are the source of truth); the README points to
  `openspec/specs/` for intended behaviour.

## Migration Plan

Pure documentation: commit after review; nothing to deploy (the built
frontend bundles its own docs-free assets).

## Open Questions

None.
