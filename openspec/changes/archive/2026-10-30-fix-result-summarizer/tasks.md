# Tasks: fix-result-summarizer

## 1. Matched-chunk context on refinement

- [x] 1.1 Extend the unit-test `FakeSession` (src/tests/test_unit_pgResultSummarizer.py) to serve `"File_chunks"` rows (oparlKey → chunk_index → text) so matched-chunk selection is testable
- [x] 1.2 Implement matched-chunk selection in `ResultSummarizer._file_text`: accept the `top_files` entry, read `match.content_chunk` on `full=True`, fetch that chunk's text from `File_chunks`, cap with the full-content budget; keep the fallback ladder `chunk → content[:budget] → teaser → None`; teaser pass (`full=False`) unchanged
- [x] 1.3 Remove the duplicated `__init__` in `ResultSummarizer` (merge artifact, no behaviour change)

## 2. Summarizer tests

- [x] 2.1 Unit test: refinement on a file whose match carries `content_chunk = n` puts chunk n's text into the prompt — not the head chunk stored in `content`
- [x] 2.2 Unit test: refinement on a file without a chunk index in match metadata keeps using `content` (current behaviour)
- [x] 2.3 Unit test: missing chunk row for the carried index falls back to `content`/teaser (no regression)
- [x] 2.4 Unit test: the automatic teaser pass never queries chunks and still prefers the teaser layer
- [x] 2.5 Unit test: assembled matched-chunk text respects the full-content budget

## 3. Chunk-aware teaser generation

- [x] 3.1 `pgTeasers`: chunk-scoped selector — select chunked files (join `File_chunks`) and pass all chunk texts (in `chunk_index` order) to the generation step
- [x] 3.2 `pgTeasers`: map-reduce summarisation for chunked files — per-chunk pre-summaries (~40 words) reduced into the final ≤200-word teaser; non-chunked files keep the single-call path
- [x] 3.3 `pgTeasers`: teaser length ceiling — every storage path (summary result, short-document fallback, API-failure text truncation) caps the teaser at 120% of the max chunk size (~9.600 chars); replace the 16.000-char excerpt fallback
- [x] 3.4 Unit tests for the teaser reduction: multi-chunk document yields ONE teaser within the word budget and the character ceiling, built from all chunks; non-chunked path unchanged; API failure of one chunk pre-summary degrades gracefully (document still gets a teaser); no stored teaser exceeds the ceiling

## 4. Verification and backfill

- [x] 4.1 Run `python3 -m pytest src/tests/test_unit_pgResultSummarizer.py src/tests/test_integration_summaryRefine.py -q` — all pass
- [x] 4.2 Live check: build a refine prompt for a query whose top file is chunked with `match.content_chunk > 1` and confirm the prompt contains that chunk's text (not the head)
- [x] 4.3 Teaser backfill: regenerate teasers for chunked files built from the head only (dry-run count first, then full run); spot-check a multi-chunk document's teaser covers content from a later chunk
