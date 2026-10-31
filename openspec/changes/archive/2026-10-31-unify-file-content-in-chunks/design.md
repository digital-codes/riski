# Design: unify-file-content-in-chunks

## Context

Live DB state (2026-10-31):

| contentKind | files | empty content | has File_chunks | vectors |
|---|---|---|---|---|
| `fulltext` | 40,785 | 28 | 0 | single vector @ chunk_index 0: 40,785 |
| `chunked` | 10,198 | 0 | 10,198 (1..n) | chunk vectors 1..n |
| `summary` | 833 | 0 | 0 | single vector @ chunk_index 0: 833 |
| NULL | 1,274 | 1,274 | 0 | none |

- `File.content` consumers (~10 sites): summarizer fallback
  (`pgResultSummarizer._file_text`), reranker fallbacks (`pgTimeline`
  ×2, `pgLocationSearch._rerank_file`), teaser source (`pgTeasers`),
  geo gate (`geoGate`), geo backfill/cleanup (`pgAddFileGeoRefs`,
  `pgGeoGateCleanup`), block-expansion text_provider, coverage metric,
  ingestion writers (`pgGen` import, `pgAddSummaries`,
  `pgChunks.fix_small_contents`).
- `pgChunks.chunk_text()` treats `chunk_index <= 0` as "not chunked" and
  returns None — 0 must become a first-class chunk.
- Vectors: `contentEmbeddings` keyed `("oparlKey", chunk_index)`; every
  single-vector file matches its `File.content` text at index 0.
- `File_chunks` DDL: PK (file_sid, chunk_index), char_start/char_end,
  text.

## Goals / Non-Goals

Goals:

- One text store: `File_chunks` for every file with text; `File.content`
  retired (NULL after verification).
- Zero re-embedding; zero retrieval behaviour change (verified).
- Idempotent, snapshot-guarded migration.

Non-Goals:

- No re-chunking of oversized documents (their 1..n chunks stay).
- No schema change (no column drop in this change — `File.content` is
  NULLed; dropping the column later, after a soak period, is a separate
  decision).
- No teaser regeneration or re-gating (their inputs are byte-identical).

## Decisions

### D1: Singles become chunk_index = 0 rows (vector keys untouched)

`File.content` text is written as one `File_chunks` row at
`chunk_index = 0`. The existing embedding for `(oparlKey, 0)` keeps
matching — no re-key, no re-embed. The "0 = single chunk" meaning replaces
the legacy "0 = not chunked".

- Alternative (chunk_index = 1 + vector re-key): rejected — renumbering
  embeddings touches the recall tables for 41k files and breaks the
  `chunk_index = 0` convention spread across `pgHybridSearch` and the
  ingestion code for zero functional gain.

### D2: Migration as an idempotent script with pre/post verification

`scripts/migrate_content_to_chunks.py`:
1. pre-flight counts (files, chunks, embeddings) → JSON report,
2. backfill `INSERT ... ON CONFLICT DO NOTHING` for content-bearing files
   without chunk rows (chunk 0, char range 0..length),
3. post-counts + integrity checks (every content-embedding key has a
   chunk row; sample checksum: `File.content` text == chunk-0 text),
4. `--retire-content` flag (separate run, AFTER verification passes)
   sets `File.content = NULL` for migrated rows.

Snapshot task runs BEFORE the first migration run
(`pg_dump -Fc` → `/mnt_ai/data/riski/snapshots/`).

### D3: Consumer migration — one accessor, all call sites

Add a single text-resolution helper in `pgChunks.py`
(`document_text(conn, oparl_key, prefer="all"|"single")`: join chunk
texts in index order, capped as the caller needs). Migrate every
`File.content` read to it:

- summarizer fallback (`_file_text` full=False/True),
- reranker fallbacks (`pgTimeline` chat + model paths,
  `pgLocationSearch._rerank_file`) — for singles this now resolves chunk 0
  (= the old `File.content` text; identical reranker input),
- teaser source (`pgTeasers`: select files by chunk existence, read the
  single chunk),
- geo gate/backfill/cleanup,
- block-expansion `text_provider` (drop the content union),
- coverage metric (chunk coverage instead of content coverage),
- ingestion writers: `pgGen` import, `pgAddSummaries`,
  `fix_small_contents` write chunk rows (kind tag stays on
  `contentKind`).

`chunk_text()` semantic fix: `chunk_index is None` → None; `0` resolves.

### D4: Retrieval-equality verification, split by file class

`scripts/verify_content_unification.py` (or the same script in verify
mode): run a fixed query set through `search_and_build_timeline` (hybrid
recall + rerank) and dump per-file results; compare pre/post dumps for
equality (oparlKey order, distances, match signals). The query set is
chosen so both classes appear in top results: single-chunk-heavy queries
("Digitalstrategie", "Ortschaftsrat Mühlburg") and chunk-heavy queries
("2. Rheinbrücke", "Terrainkurweg Radweg"). Also direct assertions:
reranker input text for a sample of singles is byte-identical pre/post.

## Risks / Trade-offs

- [Large backfill (~41.6k rows, ~120 MB)] → single INSERT..SELECT batch,
  idempotent; snapshot taken first.
- [Missed File.content consumer] → verified by grep + a temporary
  assertion log (warn on any `File.content` read during a smoke run);
  the column stays in the schema so nothing crashes, only the report
  would flag it.
- [Boilerplate-gated geo reads change path] → same text, gate logic
  untouched.
- [Rollback] → snapshot restore; or, since vectors are untouched,
  re-populating `File.content` from chunk 0 is a trivial reverse script.

## Migration Plan

1. Snapshot (task with verification of the dump).
2. Run pre-verification query dump (pre-migration results JSON).
3. Run the migration backfill; run integrity checks.
4. Deploy the consumer updates (code) — actually code first in one
   commit, then migrate: the new consumers prefer chunks and fall back to
   content, so they work pre- and post-migration (ordering-safe).
5. Run post-verification (equality vs the pre dump).
6. Run the migration with `--retire-content` (NULL the column).
7. Re-run post-verification once more.
8. Docs update (README workflow steps 2b/4, schema notes).

Rollback: snapshot restore, or reverse-populate `File.content` from
chunk 0 and revert the commit.

## Open Questions

None.
