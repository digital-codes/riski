# Proposal: query-guided-summary

## Why

The result summarizer (`src/pgResultSummarizer.py`) has two weaknesses that
make its output a poor answer for interactive search:

1. **Truncated context**: it summarizes only the first 5 top files, even
   though the search step fetched more (`top_k`, default 10). Documents
   ranked 6–10 are invisible to the summary — with hybrid recall these
   often carry distinct evidence (different signal combinations, entity
   types).
2. **Query-blind**: the prompt asks for a generic German document
   summary. It ignores the user's question entirely, so the "summary"
   does not answer what was asked — it just condenses the corpus slice.
   The search result already carries `result["query"]`; the summarizer
   simply never uses it.

## What Changes

- `ResultSummarizer` summarizes **all** files in `result["top_files"]`
  (no 5-file truncation); the `top` parameter is removed.
- The LLM prompt becomes **query-guided**: the user's question is part of
  the prompt and the instruction is to condense the document teasers
  *with respect to the question* (German) — not a neutral corpus summary.
- Teaser-layer context stays (per-file ~1k chars; 10–100 files scale by
  growing input tokens — per-file truncation cap stays as guard).
- Callers unchanged: `search_and_summarize` (wrapper) and the `/summarize`
  API endpoint pass the whole result, which already contains `query`.

## Capabilities

### New Capabilities
- `result-summarizer`: The summarizer SHALL produce a query-guided German
  summary over ALL files fetched by the search step, using the teaser
  layer with content fallback.

### Modified Capabilities
- *none* (the summarizer class is new territory for the main specs; the
  semantic-search "timeline CLI" requirement's optional-summarize behavior
  is unaffected — only the summary's content quality changes)

## Impact

- **Code**: `src/pgResultSummarizer.py` (prompt + context assembly),
  `src/tests/test_unit_pgResultSummarizer.py` (prompt/content assertions).
- **No API/contract changes**: `/summarize`, `search_and_summarize`, and
  the frontend summary card work unchanged — only the summary text gets
  better.
- **Cost note**: more input tokens per call (all teasers ≈ 1k chars each);
  still an order of magnitude below the content-based approach.
