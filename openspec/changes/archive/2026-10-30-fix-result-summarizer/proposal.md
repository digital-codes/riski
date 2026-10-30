# Fix result summarizer context selection

## Why

Two related defects in the summarizer's context selection (user-reported:
refined summaries read as if only "the document" existed, and refinement
token totals often shrink instead of grow):

1. **Refinement reads the wrong piece of chunked documents.** The refinement
   pass uses `File.content`, which for chunked documents (>8000 chars —
   10.198 files, avg. 29.227 chars of full text across ~5,3 chunks) holds
   only the FIRST chunk. The search phase already determines the
   best-matching chunk per file (`top_files[].match.content_chunk`, change:
   content-chunking) — but the summarizer never reads it, so refinement
   summarises the document head regardless of what actually matched the
   query.
2. **Teasers of chunked documents are head-only.** `pgTeasers` generates the
   teaser from `File.content` (= first chunk, ≤8.000 chars, excerpt cap
   16.000): for chunked documents the teaser describes only the first pages
   instead of the whole document. Structurally there is exactly one teaser
   per document (single `File.teaser` column — verified: no per-chunk
   duplication), but it is not a true document teaser.

## What Changes

- Refinement runs (`use_full_content=True`) select each file's context piece
  by the best-matching chunk index carried from the search phase
  (`match.content_chunk`): the matched chunk's text from `File_chunks`
  replaces the head stored in `File.content`. Files without a chunk index
  (lexical/name/location matches, agenda siblings) keep the current
  fallback (`content` → teaser). The automatic (teaser) pass is unchanged.
- Teaser generation (`pgTeasers`) summarises the COMPLETE document for
  chunked files: per-chunk pre-summaries reduced into the single ~200-word
  teaser (aggressive summarisation stage), so one true teaser per document
  covers the full text, not just the head chunk.
- Backfill: regenerate teasers for chunked files whose existing teaser was
  built from the head chunk only.
- Remove the accidental duplicate `__init__` in `ResultSummarizer` (merge
  artifact, no behaviour change).

## Capabilities

### New Capabilities

- `document-teasers` — one true, document-wide teaser per file: generated
  from the complete document text (all chunks for chunked documents) via an
  aggressive summarisation stage, capped at the teaser word budget.

### Modified Capabilities

- `result-summarizer` — the full-content refinement requirement now
  specifies that the refinement context per file SHALL be the best-matching
  chunk text selected via the chunk index carried from the search phase
  (falling back to content/teaser when no chunk index exists), not the
  head chunk stored in `File.content`.

## Impact

- `src/pgResultSummarizer.py` — `_file_text()` (matched-chunk selection via
  the carried chunk index); duplicate `__init__` removal.
- `src/pgTeasers.py` — chunk-aware teaser generation (map-reduce over
  chunks) for chunked documents.
- `src/tests/test_unit_pgResultSummarizer.py` — new/adjusted unit tests
  (FakeSession serves chunk rows and match metadata).
- Data: one-off teaser regeneration for ~9.100 chunked files (script re-run,
  no schema change). Refinement prompts stay bounded: one ~7k-char chunk per
  file instead of the head — larger than a teaser, far smaller than the full
  document.
