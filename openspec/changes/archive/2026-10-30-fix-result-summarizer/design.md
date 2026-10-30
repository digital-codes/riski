# Design: fix-result-summarizer

## Context

- The search phase already computes the best-matching chunk per file:
  `pgHybridSearch` records `signals.content_chunk` (the `chunk_index` of the
  content-embedding hit with the smallest cosine distance,
  pgHybridSearch.py:790-794), and `pgTimeline` carries it through to
  `top_files[].match.content_chunk` (pgTimeline.py:1313, 1433). It is
  currently consumed only as reranker input (`pgChunks.chunk_text`).
- Chunk sizes already respect the embedding input limit (remote.embed caps
  at 8.100 chars; `CHUNK_HARD` = 8.000) — no chunk-side change needed.
- `ResultSummarizer._file_text(oparl_key, full)` reads one `"File"` row
  (`teaser`, `content`, `downloadurl`); refinement uses
  `content[:full_content_chars]`. For chunked files `content` is the FIRST
  chunk (pgChunks.py:348-352) — the wrong piece when a later chunk matched.
- `pgTeasers` generates teasers from `File.content` (head chunk for chunked
  files), excerpt-capped at 16.000 chars — so a ~29.000-char chunked
  document gets a teaser describing only its first ~8.000 chars.
- The `FakeSession` test double mirrors the `File` row shape only.

## Goals / Non-Goals

Goals:

- Refinement context per file = the matched chunk's text (via the carried
  chunk index), falling back to `content` → teaser.
- Teasers of chunked documents summarise the COMPLETE document (map-reduce),
  still one teaser per document within the word budget.
- Automatic (teaser) pass and non-chunked files stay byte-identical.

Non-Goals:

- No change to chunking, embeddings, or what the search phase stores.
- No full-document context on refinement (the matched piece is the point —
  full assembly would blow up prompts without adding relevance).
- No API/frontend changes; the summarizer's document list and prompts keep
  their shape.

## Decisions

### D1: Read the chunk index from the file entry the summarizer already has

`_file_text` receives the `top_files` entry (it is called per file in the
prompt loop); the matched chunk index is
`file.get("match", {}).get("content_chunk")`. No new plumbing from the
search phase is needed — the index is already in the session result.

- Alternative: pass `hybrid_chunks` alongside `top_files` — rejected: a
  second parallel structure to keep in sync; the match metadata is the
  established carrier (frontend provenance uses it too).

### D2: Matched chunk replaces `content` only on refinement runs

`_file_text(full=True)`: when a chunk index exists and the chunk row exists,
use its text (budget-capped); otherwise the existing
`content[:budget] → teaser → None` ladder applies unchanged. The teaser pass
never queries chunks.

- `chunk_index == 0` (legacy single-vector files) is not carried in match
  metadata — those files take the fallback ladder, which is exactly today's
  behaviour.

### D3: Budget stays at 20.000 chars per file

A chunk is ≤8.000 chars, so the budget never truncates a matched chunk —
the cap only guards degenerate rows. Worst-case refine prompt: ~(top_k +
siblings) × 8.000 chars ≈ well within the model's context window. Larger
than the teaser pass (≈1.000 chars/file) but far smaller than full-document
assembly (≈29.000 chars/file) — this also explains the user-observed token
anomaly disappearing: refinement will now carry MORE text than the teaser
pass for matched chunks, while the earlier "often smaller" totals came from
head chunks ≈ teaser size.

### D4: Teaser map-reduce for chunked documents

`pgTeasers` gains a chunk-aware path: when `File_chunks` rows exist for the
file, summarize each chunk to a ~40-word pre-summary (batched, temperature
unchanged), then reduce all pre-summaries into the final ≤200-word teaser
with the existing prompt/retry logic. Non-chunked files keep the current
single-call path. `File.content` remains the input for non-chunked files.

The teaser output is bounded by a character CEILING of 1,2 × the maximum
chunk size (≈9.600 chars), not just the word budget: teasers are punted
into the summarizer as context, so a teaser much larger than a chunk adds
prompt weight without proportionate value. Today's fallback paths violate
this — a short document's whole text and the API-failure fallback
(`text[:16000]`, 2× chunk size) both exceed it — and are brought under the
ceiling.

- Alternative: raise `TEXT_EXCERPT_MAXLEN` to cover whole documents —
  rejected: 29.000+ chars exceed practical context windows for the teaser
  model and still truncates the longest documents; map-reduce scales.
- Alternative: reduce over chunk texts directly in one call — rejected:
  unbounded input; the two-stage reduction keeps every call small.
- Alternative: cap the teaser at the summarizer's prompt budget
  (5.000 chars) — rejected as the teaser cap: the teaser also serves other
  consumers; 120% of chunk size is the agreed upper bound, and the
  ~200-word budget keeps typical teasers far below it anyway.

### D5: Teaser backfill is a targeted re-run

Regenerate teasers only for chunked files (existing `--force` + a
chunk-scoped selector), ~9.100 files × ~6 LLM calls. Batch pipeline, resumable
(existing teaser skip logic), no schema change. Run outside the API server
as today.

### D6: Prompt layer label stays "Volltext"

The refinement layer is "the content layer (vs Teaser)" and the refine
system prompt already says "Lies alle bereitgestellten Inhalte" — no
frontend or prompt-text churn for a label nuance.

## Risks / Trade-offs

- [Matched chunk ≠ enough context for a document-overview summary] → the
  chunk is the query-relevant piece; the document list still names every
  file. Teaser regeneration (D4) improves the initial pass independently.
- [Files matched without the content signal have no chunk index] → D2
  fallback keeps them exactly as today.
- [Teaser backfill cost (~55k LLM calls)] → batch script with existing
  retry/rate-limit handling; resumable; runs offline.
- [Chunk rows missing while match metadata points at one] → D2 ladder falls
  back to `content` (the head) — never worse than today.

## Migration Plan

1. Deploy summarizer + teaser changes (restart API server; teaser script is
   batch).
2. Run the teaser backfill for chunked files (D5).
3. Rollback: revert commits — the summarizer change is read-path only; the
   regenerated teasers remain valid (they are true document teasers either
   way).

## Open Questions

None.
