# Unify file content in chunks

## Why

`File` stores document text in TWO places: `File.content` (the full text
for 41,618 smaller/summarized files — contentKind `fulltext`/`summary`) and
`File_chunks` (heading-aware chunks for the 10,198 oversized,
contentKind `chunked` files — where `File.content` holds only the head
chunk). Every text consumer therefore carries a dual path
(content column + chunk fallback), which has already produced two
verification findings (head-chunk-only teasers, head-chunk-only
refinement context). The storage should be unified: `File_chunks` becomes
the single source of document text.

Feasibility (verified against the live DB): the content vectors are keyed
`("oparlKey", chunk_index)` independently of the text columns, and every
single-vector file's existing vector sits at `chunk_index = 0` — exactly
the text stored in `File.content`. Writing that text as a `File_chunks`
row at `chunk_index = 0` preserves ALL existing vectors with **no
re-embedding**.

## What Changes

- **Migration (idempotent script)**: for every file with non-empty
  `File.content` and no chunk rows (contentKind `fulltext`/`summary`,
  ~41.6k files), write the content as a single `File_chunks` row at
  `chunk_index = 0` (char range 0..len). Existing `chunk_index = 0`
  embeddings keep matching the new rows — no vector is recomputed or lost.
- **Safety snapshot** before migration: `pg_dump -Fc` to
  `/mnt_ai/data/riski/snapshots/`.
- **Semantics update**: `chunk_index = 0` becomes a first-class chunk
  (the single chunk of a non-oversized document) instead of "not chunked";
  `chunk_text()` returns it; consumers read text exclusively from
  `File_chunks`.
- **Consumer migration** (~10 sites): summarizer fallback, reranker
  fallbacks (pgTimeline ×2, pgLocationSearch), teaser source selection,
  geo gate + geo backfill/cleanup reads, block-expansion text provider,
  coverage metric, ingestion writers (pgGen import, pgAddSummaries,
  `fix_small_contents`) write chunks instead of `File.content`.
- **After verification**: `File.content` is set to NULL for ALL rows —
  for the migrated single-chunk files it is the retired source, for
  chunked files it merely duplicates chunk 1. The `contentKind` column
  (storage-mode provenance: fulltext/summary/chunked — no remaining
  consumer except the geo gate's cosmetic prompt field) is dropped
  together with its index.
- **Verification**: retrieval equality pre/post — for a set of queries,
  hybrid-search results (top_files order, distances, match signals) must
  be identical, checked separately for single-chunk and multi-chunk files.

## Capabilities

### Modified Capabilities

- `content-chunking` — `File_chunks` becomes the single store of document
  text for ALL files (chunk 0 = the whole small document, 1..n = chunks of
  oversized ones); `File.content` is retired (NULL after migration);
  `chunk_text()` resolves chunk 0.

## Impact

- `src/pgChunks.py` — migration backfill script (or a dedicated
  `scripts/migrate_content_to_chunks.py`), `chunk_text` semantics.
- Consumers: `src/pgResultSummarizer.py`, `src/pgTimeline.py`,
  `src/pgLocationSearch.py`, `src/pgTeasers.py`, `src/geoGate.py`,
  `src/pgAddFileGeoRefs.py`, `src/pgGeoGateCleanup.py`, `src/pgCoverage.py`,
  ingestion writers (`pgGen`, `pgAddSummaries`).
- Data: ~41.6k new chunk-0 rows (~120 MB), `File.content` NULLed afterwards
  (frees ~250 MB); vectors untouched.
- Docs: README schema/workflow notes (steps 2b/4), content-chunking spec
  sync.
