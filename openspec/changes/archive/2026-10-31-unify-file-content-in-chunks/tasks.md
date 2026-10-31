# Tasks: unify-file-content-in-chunks

## 1. Safety snapshot

- [x] 1.1 `pg_dump -Fc` of riski_agentic to `/mnt_ai/data/riski/snapshots/riski_agentic_$(date +%F)-pre-content-unification.dump`; verify with `pg_restore --list` (table count) and record the pre-flight DB stats (files per contentKind, chunk count, embedding count)

## 2. Text accessor + chunk semantics

- [x] 2.1 `pgChunks.py`: `chunk_text()` resolves chunk_index 0 (only `None` means "no chunk"); new `document_text(conn, oparl_key)` helper — join all chunk texts in index order (single-chunk files yield the complete text)
- [x] 2.2 Unit tests: chunk_text(0) returns the single chunk; document_text joins 1..n in order; missing file → None

## 3. Consumer migration (fallback-safe ordering)

- [x] 3.1 `pgResultSummarizer._file_text`: content fallback → `document_text` (teaser pass and refine pass)
- [x] 3.2 Reranker fallbacks: `pgTimeline` (chat + model paths) and `pgLocationSearch._rerank_file` read chunk text instead of `File.content`
- [x] 3.3 `pgTeasers`: source selection by chunk existence; non-chunked path reads the single chunk; ingestion target stays teaser column
- [x] 3.4 Geo path: `geoGate` row loader, `pgAddFileGeoRefs`, `pgGeoGateCleanup` read chunk text
- [x] 3.5 `block_expand_top_files.text_provider`: chunks only (drop the content union)
- [x] 3.6 `pgCoverage`: content coverage metric counts chunk coverage
- [x] 3.7 Ingestion writers write chunks: `pgGen` import, `pgAddSummaries` (fulltext/summary paths), `pgChunks.fix_small_contents` (contentKind writers/CLI removed — column dropped)
- [x] 3.8 Unit tests for the migrated consumers (FakeSession with chunk rows where needed)

## 4. Migration + verification

- [x] 4.1 `scripts/migrate_content_to_chunks.py`: pre-flight report, idempotent backfill (chunk 0 = File.content text for fulltext/summary files without chunk rows, ON CONFLICT DO NOTHING), integrity checks (every content-embedding key has a chunk row; text equality sample)
- [x] 4.2 `scripts/verify_content_unification.py`: fixed query set → per-file results dump (oparlKey order, distances, match signals), compare mode; single-chunk and multi-chunk files verified separately
- [x] 4.3 Pre-migration results dump captured
- [x] 4.4 Run the migration backfill; integrity checks pass
- [x] 4.5 Post-migration verification: retrieval results identical to the pre dump (both file classes); reranker input for sampled singles byte-identical
- [x] 4.6 Retire the dual source: migration run with `--retire-content` (File.content = NULL for ALL non-null rows — chunked files' content duplicates chunk 1 and is dropped as well; contentKind column + idx_file_contentkind index dropped); re-run verification
- [x] 4.7 Grep sweep: no remaining `File.content` reads/writes in src/ (excluding contentKind handling and this change's docs)

## 5. Documentation

- [x] 5.1 README: data update workflow steps 2b/4 (chunks as the text store; pgAddSummaries/pgGen write chunks), storage description, teaser/refine notes aligned
- [x] 5.2 openspec sync: content-chunking spec delta applied to the main spec at archive time
